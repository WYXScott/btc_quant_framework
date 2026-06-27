from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os
import sqlite3
import time
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from crypto_quant.data.storage import load_parquet, merge_ohlcv, save_parquet
from crypto_quant.utils.logger import get_logger

logger = get_logger(__name__)

OKX_PUBLIC_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
OKX_BUSINESS_WS_URL = "wss://ws.okx.com:8443/ws/v5/business"
TRANSIENT_NETWORK_ERROR_CODES = {10053, 10054, 10060, 10061}


@dataclass(frozen=True)
class RealtimeKline:
    exchange: str
    inst_id: str
    channel: str
    timeframe: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    vol_contracts: float | None
    vol_ccy: float | None
    vol_quote: float | None
    confirm: bool
    source: str
    received_at: str
    raw_json: str


def utc_now_iso() -> str:
    return pd.Timestamp.now(tz='UTC').isoformat()


def okx_channel_to_timeframe(channel: str) -> str:
    suffix = str(channel or "").replace("candle", "", 1)
    if not suffix:
        return ""
    if suffix.endswith("H"):
        return suffix[:-1] + "h"
    if suffix.endswith("D"):
        return suffix[:-1] + "d"
    return suffix


def okx_ws_url_for_channels(channels: list[str]) -> str:
    if any(str(channel).startswith("candle") for channel in channels):
        return OKX_BUSINESS_WS_URL
    return OKX_PUBLIC_WS_URL


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _bool_confirm(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _iso_from_ms(value: Any) -> str:
    return pd.to_datetime(int(value), unit="ms", utc=True).isoformat()


def _extract_error_code(error: Any) -> int | None:
    for attr in ("winerror", "errno"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    for arg in getattr(error, "args", ()):
        if isinstance(arg, int):
            return arg
        if isinstance(arg, OSError):
            nested = _extract_error_code(arg)
            if nested is not None:
                return nested
        if isinstance(arg, (tuple, list)):
            for item in arg:
                if isinstance(item, int):
                    return item
    text = repr(error)
    for code in TRANSIENT_NETWORK_ERROR_CODES:
        if str(code) in text:
            return code
    return None


def classify_realtime_error(error: Any) -> dict[str, Any]:
    """Return a compact, UI-friendly classification for WebSocket/network errors."""
    code = _extract_error_code(error)
    text = repr(error)
    message = str(error)
    lower = f"{text} {message}".lower()
    category = "network_error"
    if code == 10054 or "forcibly closed" in lower or "connection reset" in lower:
        category = "connection_reset"
    elif "timed out" in lower or "timeout" in lower:
        category = "timeout"
    elif "proxy" in lower:
        category = "proxy_error"
    elif "ssl" in lower or "tls" in lower:
        category = "tls_error"
    retryable = category in {"connection_reset", "timeout", "proxy_error", "tls_error", "network_error"}
    if code is not None:
        retryable = retryable or code in TRANSIENT_NETWORK_ERROR_CODES
    if category == "connection_reset" and code == 10054:
        summary = "connection_reset_10054: remote host forcibly closed the connection; safe to retry."
    else:
        summary = f"{category}: {message or text}"
    return {
        "category": category,
        "code": code,
        "retryable": bool(retryable),
        "type": type(error).__name__,
        "message": message,
        "repr": text,
        "summary": summary,
    }


def parse_okx_candle_message(
    message: str | bytes | dict[str, Any],
    *,
    prefer_base_volume: bool = True,
    received_at: str | None = None,
) -> list[RealtimeKline]:
    """Parse OKX WebSocket candle data messages into normalized klines."""
    received_at = received_at or utc_now_iso()
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    if isinstance(message, str):
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return []
    else:
        payload = message
    if not isinstance(payload, dict):
        return []
    arg = payload.get("arg") or {}
    channel = str(arg.get("channel") or "")
    inst_id = str(arg.get("instId") or "")
    if not channel.startswith("candle") or not inst_id:
        return []
    rows = payload.get("data") or []
    out: list[RealtimeKline] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 5:
            continue
        padded = list(row) + [None] * max(0, 9 - len(row))
        vol_contracts = _float_or_none(padded[5])
        vol_ccy = _float_or_none(padded[6])
        vol_quote = _float_or_none(padded[7])
        volume = vol_ccy if prefer_base_volume and vol_ccy is not None else vol_contracts
        if volume is None:
            volume = 0.0
        try:
            kline = RealtimeKline(
                exchange="okx",
                inst_id=inst_id,
                channel=channel,
                timeframe=okx_channel_to_timeframe(channel),
                timestamp=_iso_from_ms(padded[0]),
                open=float(padded[1]),
                high=float(padded[2]),
                low=float(padded[3]),
                close=float(padded[4]),
                volume=float(volume),
                vol_contracts=vol_contracts,
                vol_ccy=vol_ccy,
                vol_quote=vol_quote,
                confirm=_bool_confirm(padded[8]),
                source="okx_ws",
                received_at=received_at,
                raw_json=json.dumps(row, ensure_ascii=False, default=str),
            )
        except Exception as exc:
            logger.warning("Skipping malformed OKX candle row: %s row=%r", exc, row)
            continue
        out.append(kline)
    return out


class RealtimeKlineStore:
    """SQLite storage for public realtime market candles."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.create_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS realtime_klines (
                    exchange TEXT NOT NULL,
                    inst_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    vol_contracts REAL,
                    vol_ccy REAL,
                    vol_quote REAL,
                    confirm INTEGER NOT NULL,
                    source TEXT,
                    received_at TEXT NOT NULL,
                    raw_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (exchange, inst_id, channel, timestamp)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS realtime_status (
                    component TEXT PRIMARY KEY,
                    exchange TEXT,
                    inst_id TEXT,
                    channels_json TEXT,
                    status TEXT,
                    last_message_at TEXT,
                    last_kline_at TEXT,
                    last_error TEXT,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    kline_count INTEGER NOT NULL DEFAULT 0,
                    details_json TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_realtime_klines_latest ON realtime_klines (inst_id, channel, timestamp DESC)"
            )
            conn.commit()

    def upsert_kline(self, kline: RealtimeKline) -> None:
        row = asdict(kline)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO realtime_klines (
                    exchange, inst_id, channel, timeframe, timestamp,
                    open, high, low, close, volume,
                    vol_contracts, vol_ccy, vol_quote, confirm,
                    source, received_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, inst_id, channel, timestamp) DO UPDATE SET
                    timeframe=excluded.timeframe,
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    vol_contracts=excluded.vol_contracts,
                    vol_ccy=excluded.vol_ccy,
                    vol_quote=excluded.vol_quote,
                    confirm=excluded.confirm,
                    source=excluded.source,
                    received_at=excluded.received_at,
                    raw_json=excluded.raw_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    row["exchange"],
                    row["inst_id"],
                    row["channel"],
                    row["timeframe"],
                    row["timestamp"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row["vol_contracts"],
                    row["vol_ccy"],
                    row["vol_quote"],
                    int(bool(row["confirm"])),
                    row["source"],
                    row["received_at"],
                    row["raw_json"],
                ),
            )
            conn.commit()

    def upsert_klines(self, klines: list[RealtimeKline]) -> int:
        for kline in klines:
            self.upsert_kline(kline)
        return len(klines)

    def update_status(
        self,
        *,
        component: str = "okx_realtime_ws",
        exchange: str = "okx",
        inst_id: str | None = None,
        channels: list[str] | None = None,
        status: str,
        last_message_at: str | None = None,
        last_kline_at: str | None = None,
        last_error: str | None = None,
        message_count: int | None = None,
        kline_count: int | None = None,
        details: dict[str, Any] | None = None,
        clear_last_error: bool = False,
    ) -> None:
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT message_count, kline_count FROM realtime_status WHERE component = ?",
                (component,),
            ).fetchone()
            prev_message_count = int(existing["message_count"]) if existing is not None else 0
            prev_kline_count = int(existing["kline_count"]) if existing is not None else 0
            conn.execute(
                """
                INSERT INTO realtime_status (
                    component, exchange, inst_id, channels_json, status,
                    last_message_at, last_kline_at, last_error,
                    message_count, kline_count, details_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(component) DO UPDATE SET
                    exchange=excluded.exchange,
                    inst_id=excluded.inst_id,
                    channels_json=excluded.channels_json,
                    status=excluded.status,
                    last_message_at=COALESCE(excluded.last_message_at, realtime_status.last_message_at),
                    last_kline_at=COALESCE(excluded.last_kline_at, realtime_status.last_kline_at),
                    last_error=CASE
                        WHEN ? THEN NULL
                        ELSE COALESCE(excluded.last_error, realtime_status.last_error)
                    END,
                    message_count=excluded.message_count,
                    kline_count=excluded.kline_count,
                    details_json=excluded.details_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    component,
                    exchange,
                    inst_id,
                    json.dumps(channels or [], ensure_ascii=False),
                    status,
                    last_message_at,
                    last_kline_at,
                    last_error,
                    prev_message_count if message_count is None else int(message_count),
                    prev_kline_count if kline_count is None else int(kline_count),
                    json.dumps(details or {}, ensure_ascii=False, default=str),
                    int(bool(clear_last_error)),
                ),
            )
            conn.commit()

    def latest_status(self, component: str = "okx_realtime_ws") -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM realtime_status WHERE component = ?", (component,)).fetchone()
        return None if row is None else dict(row)

    def latest_klines(
        self,
        *,
        inst_id: str | None = None,
        channel: str | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        clauses: list[str] = []
        params: list[Any] = []
        if inst_id:
            clauses.append("inst_id = ?")
            params.append(inst_id)
        if channel:
            clauses.append("channel = ?")
            params.append(channel)
        where = "" if not clauses else "WHERE " + " AND ".join(clauses)
        query = f"""
            SELECT *
            FROM realtime_klines
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(int(limit))
        with self.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def ohlcv_frame(
        self,
        *,
        inst_id: str,
        channel: str,
        confirmed_only: bool = True,
    ) -> pd.DataFrame:
        where_confirm = "AND confirm = 1" if confirmed_only else ""
        query = f"""
            SELECT timestamp, open, high, low, close, volume
            FROM realtime_klines
            WHERE inst_id = ? AND channel = ? {where_confirm}
            ORDER BY timestamp ASC
        """
        with self.connect() as conn:
            df = pd.read_sql_query(query, conn, params=[inst_id, channel])
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp").sort_index()
        return df[["open", "high", "low", "close", "volume"]].astype(float)


def _proxy_kwargs(proxy_url: str | None, *, use_env_proxy: bool = True) -> dict[str, Any]:
    if proxy_url is None and use_env_proxy:
        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if not proxy_url:
        return {}
    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        return {}
    kwargs: dict[str, Any] = {
        "http_proxy_host": parsed.hostname,
        "http_proxy_port": parsed.port,
        "proxy_type": "socks5" if parsed.scheme.startswith("socks") else "http",
    }
    if parsed.username:
        kwargs["http_proxy_auth"] = (parsed.username, parsed.password or "")
    return kwargs


def merge_realtime_ohlcv_file(
    *,
    historical_path: str | Path,
    db_path: str | Path,
    inst_id: str,
    channel: str,
    output_path: str | Path | None = None,
    confirmed_only: bool = True,
    validate_timeframe: str | None = None,
    quality_config: dict[str, Any] | None = None,
    quality_output_dir: str | Path | None = None,
    require_quality_pass: bool = False,
) -> pd.DataFrame:
    historical_path = Path(historical_path)
    output_path = Path(output_path) if output_path is not None else historical_path
    existing = load_parquet(historical_path) if historical_path.exists() else None
    realtime = RealtimeKlineStore(db_path).ohlcv_frame(
        inst_id=inst_id,
        channel=channel,
        confirmed_only=confirmed_only,
    )
    merged = merge_ohlcv(existing, realtime)

    # Validate before writing so a malformed realtime candle cannot silently
    # contaminate the historical research parquet. The default remains backward
    # compatible for unit tests, while scripts pass the project quality config.
    if validate_timeframe:
        from crypto_quant.data.quality import run_ohlcv_quality_checks, save_quality_artifacts

        qc = quality_config or {}
        report, issues = run_ohlcv_quality_checks(
            merged,
            timeframe=str(validate_timeframe),
            max_abs_log_return=float(qc.get("max_abs_log_return", 0.20)),
            zscore_threshold=float(qc.get("zscore_threshold", 8.0)),
            max_range_pct=float(qc.get("max_range_pct", 0.35)),
            max_zero_volume_fraction=float(qc.get("max_zero_volume_fraction", 0.01)),
            allow_incomplete_latest_bar=bool(qc.get("allow_incomplete_latest_bar", True)),
        )
        report["context"] = "realtime_merge"
        report["historical_path"] = str(historical_path)
        report["output_path"] = str(output_path)
        report["realtime_rows"] = int(len(realtime))
        if quality_output_dir is not None:
            save_quality_artifacts(report, issues, quality_output_dir)
        if require_quality_pass and report.get("status") != "pass":
            raise ValueError(
                "Merged OHLCV failed quality gate; output was not written. "
                f"status={report.get('status')} critical_count={report.get('critical_count')}"
            )

    save_parquet(merged, output_path)
    logger.info(
        "Merged historical=%s realtime=%s rows into %s",
        0 if existing is None else len(existing),
        len(realtime),
        output_path,
    )
    return merged


def run_okx_realtime_listener(
    *,
    db_path: str | Path,
    inst_id: str,
    channels: list[str],
    ws_url: str | None = None,
    proxy_url: str | None = None,
    use_env_proxy: bool = True,
    prefer_base_volume: bool = True,
    max_messages: int | None = None,
    component: str = "okx_realtime_ws",
    auto_merge_config: dict[str, Any] | None = None,
    reconnects: int = 0,
    reconnect_sleep_seconds: float = 3.0,
) -> dict[str, Any]:
    import websocket

    store = RealtimeKlineStore(db_path)
    channels = [str(channel) for channel in channels if str(channel).strip()]
    if not channels:
        raise ValueError("At least one OKX WebSocket channel is required")
    ws_url = ws_url or okx_ws_url_for_channels(channels)
    counts = {"messages": 0, "klines": 0, "closed_by_limit": False}
    subscribe_payload = {
        "op": "subscribe",
        "args": [{"channel": channel, "instId": inst_id} for channel in channels],
    }
    auto_merge_config = auto_merge_config or {}
    merge_channel = auto_merge_config.get("channel")
    max_reconnects = max(0, int(reconnects))
    last_error_info: dict[str, Any] | None = None

    def maybe_merge(klines: list[RealtimeKline]) -> None:
        if not auto_merge_config.get("enabled"):
            return
        if not merge_channel:
            return
        if not any(k.channel == merge_channel and k.confirm for k in klines):
            return
        try:
            merge_realtime_ohlcv_file(
                historical_path=auto_merge_config["historical_path"],
                db_path=db_path,
                inst_id=inst_id,
                channel=merge_channel,
                output_path=auto_merge_config.get("output_path"),
                confirmed_only=bool(auto_merge_config.get("confirmed_only", True)),
                validate_timeframe=auto_merge_config.get("timeframe"),
                quality_config=auto_merge_config.get("quality_config"),
                quality_output_dir=auto_merge_config.get("quality_output_dir"),
                require_quality_pass=bool(auto_merge_config.get("require_quality_pass", False)),
            )
        except Exception as exc:
            store.update_status(
                component=component,
                inst_id=inst_id,
                channels=channels,
                status="merge_error",
                last_error=f"realtime_merge_failed: {type(exc).__name__}: {exc}",
                message_count=counts["messages"],
                kline_count=counts["klines"],
                details={"url": ws_url, "attempt": attempts, "max_reconnects": max_reconnects, "merge_channel": merge_channel},
            )
            logger.error("Realtime OHLCV merge failed; historical output was not updated: %r", exc)

    def on_open(ws):
        nonlocal last_error_info
        last_error_info = None
        store.update_status(
            component=component,
            inst_id=inst_id,
            channels=channels,
            status="connected",
            details={"url": ws_url, "attempt": attempts, "max_reconnects": max_reconnects},
            clear_last_error=True,
        )
        ws.send(json.dumps(subscribe_payload))
        logger.info("Subscribed to OKX realtime channels: %s", channels)

    def on_message(ws, message):
        now = utc_now_iso()
        counts["messages"] += 1
        klines = parse_okx_candle_message(
            message,
            prefer_base_volume=prefer_base_volume,
            received_at=now,
        )
        if klines:
            counts["klines"] += store.upsert_klines(klines)
            maybe_merge(klines)
        store.update_status(
            component=component,
            inst_id=inst_id,
            channels=channels,
            status="receiving",
            last_message_at=now,
            last_kline_at=klines[-1].received_at if klines else None,
            last_error=None,
            message_count=counts["messages"],
            kline_count=counts["klines"],
            details={
                "url": ws_url,
                "attempt": attempts,
                "max_reconnects": max_reconnects,
                "last_payload_type": "kline" if klines else "control",
            },
            clear_last_error=True,
        )
        if max_messages is not None and counts["messages"] >= int(max_messages):
            counts["closed_by_limit"] = True
            ws.close()

    def on_error(ws, error):
        nonlocal last_error_info
        last_error_info = classify_realtime_error(error)
        store.update_status(
            component=component,
            inst_id=inst_id,
            channels=channels,
            status="error",
            last_error=str(last_error_info["summary"]),
            message_count=counts["messages"],
            kline_count=counts["klines"],
            details={
                "url": ws_url,
                "attempt": attempts,
                "max_reconnects": max_reconnects,
                "error": last_error_info,
            },
        )
        logger.warning("OKX realtime WebSocket error: %r", error)

    def on_close(ws, code, message):
        status = "sample_complete" if counts["closed_by_limit"] else "closed"
        if not counts["closed_by_limit"] and last_error_info is not None:
            status = "closed_after_error"
        store.update_status(
            component=component,
            inst_id=inst_id,
            channels=channels,
            status=status,
            message_count=counts["messages"],
            kline_count=counts["klines"],
            details={
                "url": ws_url,
                "attempt": attempts,
                "max_reconnects": max_reconnects,
                "close_code": code,
                "close_message": message,
                "error": last_error_info,
            },
        )
        logger.info("OKX realtime WebSocket closed: code=%s message=%s", code, message)

    attempts = 0
    while True:
        attempts += 1
        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        kwargs = _proxy_kwargs(proxy_url, use_env_proxy=use_env_proxy)
        try:
            ws.run_forever(ping_interval=20, ping_timeout=10, **kwargs)
        except Exception as exc:
            last_error_info = classify_realtime_error(exc)
            store.update_status(
                component=component,
                inst_id=inst_id,
                channels=channels,
                status="error",
                last_error=str(last_error_info["summary"]),
                message_count=counts["messages"],
                kline_count=counts["klines"],
                details={
                    "url": ws_url,
                    "attempt": attempts,
                    "max_reconnects": max_reconnects,
                    "error": last_error_info,
                },
            )
            logger.warning("OKX realtime WebSocket run_forever failed: %r", exc)
        if counts["closed_by_limit"]:
            break
        if attempts > max_reconnects:
            break
        store.update_status(
            component=component,
            inst_id=inst_id,
            channels=channels,
            status="reconnecting",
            last_error=str(last_error_info["summary"]) if last_error_info else None,
            message_count=counts["messages"],
            kline_count=counts["klines"],
            details={
                "url": ws_url,
                "attempt": attempts,
                "next_attempt": attempts + 1,
                "max_reconnects": max_reconnects,
                "sleep_seconds": reconnect_sleep_seconds,
                "error": last_error_info,
            },
        )
        time.sleep(float(reconnect_sleep_seconds))

    if not counts["closed_by_limit"] and last_error_info is not None and attempts > max_reconnects:
        store.update_status(
            component=component,
            inst_id=inst_id,
            channels=channels,
            status="error_stopped",
            last_error=str(last_error_info["summary"]),
            message_count=counts["messages"],
            kline_count=counts["klines"],
            details={
                "url": ws_url,
                "attempts": attempts,
                "max_reconnects": max_reconnects,
                "error": last_error_info,
            },
        )

    return {
        "db_path": str(db_path),
        "inst_id": inst_id,
        "channels": channels,
        "messages": counts["messages"],
        "klines": counts["klines"],
        "attempts": attempts,
        "max_reconnects": max_reconnects,
        "last_error": last_error_info,
        "status": store.latest_status(component),
    }
