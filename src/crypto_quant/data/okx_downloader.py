from __future__ import annotations

from pathlib import Path
from typing import Any, List
import os
import time

import pandas as pd
import requests

from crypto_quant.data.storage import load_parquet, merge_ohlcv, save_parquet
from crypto_quant.utils.logger import get_logger

logger = get_logger(__name__)

OKX_BASE_URL = "https://www.okx.com"

_TIMEFRAME_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "6h": "6H",
    "12h": "12H",
    "1d": "1D",
    "1w": "1W",
}


def _env_proxy_dict() -> dict[str, str] | None:
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    # If only HTTPS_PROXY is set, requests can still use it for https URLs.
    proxies: dict[str, str] = {}
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return proxies or None


def normalize_okx_bar(timeframe: str) -> str:
    tf = (timeframe or "4h").strip()
    return _TIMEFRAME_MAP.get(tf.lower(), tf)


def _okx_get_json(
    session: requests.Session,
    url: str,
    params: dict[str, Any] | None,
    timeout_seconds: float,
    max_retries: int,
    retry_sleep_seconds: float,
    proxies: dict[str, str] | None,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, params=params, timeout=timeout_seconds, proxies=proxies)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                raise RuntimeError(f"Unexpected OKX response type: {type(data)} {data!r}")
            if data.get("code") not in {None, "0", 0}:
                raise RuntimeError(f"OKX error response: {data}")
            return data
        except Exception as exc:
            last_exc = exc
            logger.warning("OKX request failed, attempt %s/%s: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(retry_sleep_seconds * attempt)
    raise RuntimeError(f"OKX request failed after {max_retries} attempts: {last_exc}")


def _parse_okx_candles(rows: list[list[Any]], prefer_base_volume: bool = True) -> pd.DataFrame:
    """Parse OKX candle rows into the project's standard OHLCV frame.

    OKX candle row format is generally:
    [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]

    For SWAP contracts, ``vol`` is contract count while ``volCcy`` is closer to
    base-asset volume. The framework's historical Binance dataset used base
    volume, so the default here uses ``volCcy`` when it is present.
    """
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows)
    # Pad missing optional columns defensively.
    for i in range(df.shape[1], 9):
        df[i] = None
    df = df.iloc[:, :9]
    df.columns = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "vol_contracts",
        "vol_ccy",
        "vol_quote",
        "confirm",
    ]
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "vol_contracts", "vol_ccy", "vol_quote"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if prefer_base_volume and df["vol_ccy"].notna().any():
        df["volume"] = df["vol_ccy"]
    else:
        df["volume"] = df["vol_contracts"]
    out = df[["timestamp", "open", "high", "low", "close", "volume"]]
    out = out.set_index("timestamp").sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out.astype(float)


def fetch_okx_ohlcv_native(
    inst_id: str,
    timeframe: str,
    since_ms: int,
    base_url: str | None = None,
    limit: int = 100,
    max_batches: int = 1000,
    timeout_seconds: float = 30.0,
    max_retries: int = 5,
    retry_sleep_seconds: float = 2.0,
    use_env_proxy: bool = True,
    endpoint: str = "history-candles",
    prefer_base_volume: bool = True,
) -> pd.DataFrame:
    """Fetch OKX OHLCV by paging backwards from the latest candle.

    OKX market/history-candles returns rows in reverse chronological order.
    The ``after`` cursor requests records earlier than the given timestamp, so
    we repeatedly move the cursor to the oldest timestamp in the current page.
    """
    base = (base_url or OKX_BASE_URL).rstrip("/")
    endpoint = (endpoint or "history-candles").strip().strip("/")
    if endpoint not in {"candles", "history-candles"}:
        endpoint = "history-candles"
    url = f"{base}/api/v5/market/{endpoint}"
    bar = normalize_okx_bar(timeframe)
    limit = max(1, min(int(limit), 300))

    session = requests.Session()
    session.trust_env = use_env_proxy
    proxies = _env_proxy_dict() if use_env_proxy else None

    all_rows: List[list[Any]] = []
    cursor_after: int | None = None

    for batch_id in range(max_batches):
        params: dict[str, Any] = {"instId": inst_id, "bar": bar, "limit": limit}
        if cursor_after is not None:
            params["after"] = str(cursor_after)
        data = _okx_get_json(
            session=session,
            url=url,
            params=params,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
            proxies=proxies,
        )
        rows = data.get("data") or []
        if not rows:
            break
        all_rows.extend(rows)
        timestamps = [int(r[0]) for r in rows if r and r[0] is not None]
        if not timestamps:
            break
        newest_ts = max(timestamps)
        oldest_ts = min(timestamps)
        logger.info(
            "Fetched OKX batch %s with %s rows; oldest=%s newest=%s",
            batch_id + 1,
            len(rows),
            pd.to_datetime(oldest_ts, unit="ms", utc=True),
            pd.to_datetime(newest_ts, unit="ms", utc=True),
        )
        if oldest_ts <= since_ms:
            break
        if cursor_after == oldest_ts:
            break
        cursor_after = oldest_ts
        if len(rows) < limit:
            break
        time.sleep(0.12)

    df = _parse_okx_candles(all_rows, prefer_base_volume=prefer_base_volume)
    if df.empty:
        return df
    since_ts = pd.to_datetime(since_ms, unit="ms", utc=True)
    return df[df.index >= since_ts].sort_index()


def update_okx_ohlcv_file(
    inst_id: str,
    timeframe: str,
    since_iso: str,
    output_path: str | Path,
    downloader_config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    output_path = Path(output_path)
    downloader_config = downloader_config or {}

    existing: pd.DataFrame | None = None
    if output_path.exists():
        existing = load_parquet(output_path)
        if not existing.empty:
            # OKX backward pagination is robust from latest, but we still merge
            # against existing data. Fetching from the original configured since
            # is safer for filling small gaps and avoiding cursor-direction
            # mistakes.
            configured_since_ms = int(pd.Timestamp(since_iso).timestamp() * 1000)
            if bool(downloader_config.get("full_refresh", False)):
                since_ms = configured_since_ms
            else:
                # Re-fetch a small overlap window to update recent candles.
                last_timestamp = pd.Timestamp(existing.index.max()).tz_convert("UTC")
                overlap_bars = int(downloader_config.get("overlap_bars", 50))
                tf = (timeframe or "4h").lower()
                if tf.endswith("h"):
                    overlap_ms = int(tf[:-1]) * 60 * 60 * 1000 * overlap_bars
                elif tf.endswith("m"):
                    overlap_ms = int(tf[:-1]) * 60 * 1000 * overlap_bars
                else:
                    overlap_ms = 24 * 60 * 60 * 1000 * overlap_bars
                since_ms = max(configured_since_ms, int(last_timestamp.timestamp() * 1000) - overlap_ms)
                logger.info("Existing OKX data found. Updating with overlap from %s", pd.to_datetime(since_ms, unit="ms", utc=True))
        else:
            since_ms = int(pd.Timestamp(since_iso).timestamp() * 1000)
    else:
        since_ms = int(pd.Timestamp(since_iso).timestamp() * 1000)

    new_df = fetch_okx_ohlcv_native(
        inst_id=inst_id,
        timeframe=timeframe,
        since_ms=since_ms,
        base_url=downloader_config.get("base_url"),
        limit=int(downloader_config.get("limit", 100)),
        max_batches=int(downloader_config.get("max_batches", 1000)),
        timeout_seconds=float(downloader_config.get("timeout_seconds", 30.0)),
        max_retries=int(downloader_config.get("max_retries", 5)),
        retry_sleep_seconds=float(downloader_config.get("retry_sleep_seconds", 2.0)),
        use_env_proxy=bool(downloader_config.get("use_env_proxy", True)),
        endpoint=str(downloader_config.get("endpoint", "history-candles")),
        prefer_base_volume=bool(downloader_config.get("prefer_base_volume", True)),
    )
    merged = merge_ohlcv(existing, new_df)
    save_parquet(merged, output_path)
    logger.info("Saved %s OKX rows to %s", len(merged), output_path)
    return merged
