from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List
import os
import time

import ccxt
import pandas as pd
import requests

from crypto_quant.data.storage import load_parquet, merge_ohlcv, save_parquet
from crypto_quant.utils.logger import get_logger
from crypto_quant.data.okx_downloader import update_okx_ohlcv_file

logger = get_logger(__name__)


BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
BINANCE_SPOT_BASE_URL = "https://api.binance.com"
BINANCE_SPOT_MARKET_DATA_BASE_URL = "https://data-api.binance.vision"


def _env_proxy_dict() -> dict[str, str] | None:
    """Return explicit proxies from common environment variables, if present."""
    http_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not http_proxy and not https_proxy:
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    proxies: dict[str, str] = {}
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return proxies or None


def create_exchange(
    exchange_name: str,
    market_type: str = "future",
    rate_limit: bool = True,
    timeout_ms: int = 30000,
    proxy: str | None = None,
):
    """Create a CCXT exchange instance with timeout and optional proxy support."""
    if not hasattr(ccxt, exchange_name):
        raise ValueError(f"Unsupported exchange in CCXT: {exchange_name}")
    klass = getattr(ccxt, exchange_name)
    params: Dict[str, Any] = {
        "enableRateLimit": rate_limit,
        "timeout": timeout_ms,
        "options": {"defaultType": market_type},
    }
    if proxy:
        params["proxies"] = {"http": proxy, "https": proxy}
    exchange = klass(params)
    return exchange


def fetch_ohlcv_paginated(
    exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    limit: int = 1000,
    max_batches: int = 1000,
) -> pd.DataFrame:
    """Fetch OHLCV data page by page using CCXT public endpoints."""
    all_rows = []
    current_since = since_ms

    for batch_id in range(max_batches):
        rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=current_since, limit=limit)
        if not rows:
            break
        all_rows.extend(rows)
        last_ts = rows[-1][0]
        next_since = last_ts + 1
        if next_since <= current_since:
            break
        current_since = next_since
        logger.info(
            "Fetched CCXT batch %s with %s rows; last_ts=%s",
            batch_id + 1,
            len(rows),
            pd.to_datetime(last_ts, unit="ms", utc=True),
        )
        time.sleep(exchange.rateLimit / 1000 if getattr(exchange, "rateLimit", None) else 0.2)
        if len(rows) < limit:
            break

    if not all_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df.astype(float)


def _binance_endpoint(market_type: str, base_url: str | None = None) -> tuple[str, str]:
    """Resolve the Binance K-line endpoint.

    Notes
    -----
    ``https://data-api.binance.vision`` exposes the public spot-market-data
    ``/api/v3/klines`` endpoint and is often reachable even when
    ``fapi.binance.com`` returns HTTP 451 or resets the connection. Therefore,
    when this base URL is configured, force the spot market-data path regardless
    of ``market_type``. This keeps Binance as the data source while allowing the
    research pipeline to run in restricted network environments.
    """
    configured_base = (base_url or "").rstrip("/")
    if configured_base and "data-api.binance.vision" in configured_base:
        return configured_base, "/api/v3/klines"

    mt = (market_type or "future").lower()
    if mt in {"future", "futures", "swap", "usdm", "linear"}:
        return (base_url or BINANCE_FUTURES_BASE_URL).rstrip("/"), "/fapi/v1/klines"
    return (base_url or BINANCE_SPOT_BASE_URL).rstrip("/"), "/api/v3/klines"


def _binance_native_request(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    timeout_seconds: float,
    max_retries: int,
    retry_sleep_seconds: float,
    proxies: dict[str, str] | None,
) -> list[list[Any]]:
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, params=params, timeout=timeout_seconds, proxies=proxies)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("code"):
                raise RuntimeError(f"Binance error response: {data}")
            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected Binance response type: {type(data)} {data!r}")
            return data
        except Exception as exc:  # requests errors + JSON/API errors
            last_exc = exc
            logger.warning("Binance native request failed, attempt %s/%s: %s", attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(retry_sleep_seconds * attempt)
    raise RuntimeError(f"Binance native request failed after {max_retries} attempts: {last_exc}")


def fetch_binance_ohlcv_native(
    raw_symbol: str,
    timeframe: str,
    since_ms: int,
    market_type: str = "future",
    base_url: str | None = None,
    limit: int = 1000,
    max_batches: int = 1000,
    timeout_seconds: float = 30.0,
    max_retries: int = 5,
    retry_sleep_seconds: float = 2.0,
    use_env_proxy: bool = True,
) -> pd.DataFrame:
    """
    Fetch Binance OHLCV directly from Binance REST kline endpoints.

    This avoids CCXT's market-loading step, which calls exchangeInfo before fetching
    OHLCV and can be a separate timeout point on restricted networks.
    """
    base, path = _binance_endpoint(market_type=market_type, base_url=base_url)
    url = f"{base}{path}"
    session = requests.Session()
    session.trust_env = use_env_proxy
    proxies = _env_proxy_dict() if use_env_proxy else None

    all_rows: List[list[Any]] = []
    current_since = since_ms

    for batch_id in range(max_batches):
        params = {
            "symbol": raw_symbol,
            "interval": timeframe,
            "startTime": int(current_since),
            "limit": int(limit),
        }
        rows = _binance_native_request(
            session=session,
            url=url,
            params=params,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_sleep_seconds=retry_sleep_seconds,
            proxies=proxies,
        )
        if not rows:
            break
        all_rows.extend(rows)
        last_open_time = int(rows[-1][0])
        next_since = last_open_time + 1
        if next_since <= current_since:
            break
        current_since = next_since
        logger.info(
            "Fetched Binance native batch %s with %s rows; last_ts=%s",
            batch_id + 1,
            len(rows),
            pd.to_datetime(last_open_time, unit="ms", utc=True),
        )
        if len(rows) < limit:
            break
        time.sleep(0.15)

    if not all_rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    # Binance kline columns: open_time, open, high, low, close, volume, close_time,
    # quote_asset_volume, number_of_trades, taker_buy_base, taker_buy_quote, ignore
    df = pd.DataFrame(all_rows)
    df = df.iloc[:, :6]
    df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
    df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df.astype(float)


def update_ohlcv_file(
    exchange_name: str,
    market_type: str,
    symbol: str,
    timeframe: str,
    since_iso: str,
    output_path: str | Path,
    raw_symbol: str | None = None,
    downloader: str = "binance_native",
    downloader_config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    output_path = Path(output_path)
    downloader_config = downloader_config or {}

    existing: Optional[pd.DataFrame] = None
    if output_path.exists():
        existing = load_parquet(output_path)
        if not existing.empty:
            last_timestamp = pd.Timestamp(existing.index.max()).tz_convert("UTC")
            since_ms = int(last_timestamp.timestamp() * 1000) + 1
            logger.info("Existing data found. Updating from %s", last_timestamp)
        else:
            since_ms = int(pd.Timestamp(since_iso).timestamp() * 1000)
    else:
        since_ms = int(pd.Timestamp(since_iso).timestamp() * 1000)

    selected = (downloader or "binance_native").lower()
    if selected == "okx_native" or (selected == "auto" and exchange_name.lower().startswith("okx")):
        inst_id = downloader_config.get("inst_id") or raw_symbol or symbol
        new_df = update_okx_ohlcv_file(
            inst_id=inst_id,
            timeframe=timeframe,
            since_iso=since_iso,
            output_path=output_path,
            downloader_config=downloader_config,
        )
        # update_okx_ohlcv_file already merges and saves because OKX's safest
        # incremental mode re-fetches a recent overlap. Return directly.
        return new_df
    if selected == "binance_native" or (selected == "auto" and exchange_name.lower().startswith("binance")):
        raw_symbol = raw_symbol or symbol.replace("/", "").replace(":USDT", "")
        new_df = fetch_binance_ohlcv_native(
            raw_symbol=raw_symbol,
            timeframe=timeframe,
            since_ms=since_ms,
            market_type=market_type,
            base_url=downloader_config.get("base_url"),
            limit=int(downloader_config.get("limit", 1000)),
            max_batches=int(downloader_config.get("max_batches", 1000)),
            timeout_seconds=float(downloader_config.get("timeout_seconds", 30.0)),
            max_retries=int(downloader_config.get("max_retries", 5)),
            retry_sleep_seconds=float(downloader_config.get("retry_sleep_seconds", 2.0)),
            use_env_proxy=bool(downloader_config.get("use_env_proxy", True)),
        )
    else:
        proxy = downloader_config.get("proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        exchange = create_exchange(
            exchange_name,
            market_type=market_type,
            rate_limit=bool(downloader_config.get("rate_limit", True)),
            timeout_ms=int(float(downloader_config.get("timeout_seconds", 30.0)) * 1000),
            proxy=proxy,
        )
        new_df = fetch_ohlcv_paginated(exchange, symbol=symbol, timeframe=timeframe, since_ms=since_ms)

    merged = merge_ohlcv(existing, new_df)
    save_parquet(merged, output_path)
    logger.info("Saved %s rows to %s", len(merged), output_path)
    return merged
