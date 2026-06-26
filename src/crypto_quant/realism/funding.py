from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import ccxt
import pandas as pd

from crypto_quant.data.storage import load_parquet, merge_ohlcv, save_parquet


def create_funding_exchange(exchange_name: str = "binance", rate_limit: bool = True):
    klass = getattr(ccxt, exchange_name)
    return klass({"enableRateLimit": rate_limit, "options": {"defaultType": "future"}})


def _normalize_funding_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["symbol", "funding_rate", "mark_price"])
    normalized = []
    for row in rows:
        ts = row.get("timestamp") or row.get("datetime")
        if isinstance(ts, str):
            ts = pd.Timestamp(ts).timestamp() * 1000
        info = row.get("info", {}) or {}
        rate = row.get("fundingRate", row.get("funding_rate", info.get("fundingRate")))
        mark = row.get("markPrice", info.get("markPrice"))
        normalized.append({
            "timestamp": pd.to_datetime(int(ts), unit="ms", utc=True) if ts is not None else pd.NaT,
            "symbol": row.get("symbol", info.get("symbol")),
            "funding_rate": float(rate) if rate not in (None, "") else None,
            "mark_price": float(mark) if mark not in (None, "") else None,
        })
    df = pd.DataFrame(normalized).dropna(subset=["timestamp"]).set_index("timestamp").sort_index()
    return df


def fetch_funding_rate_history_paginated(
    exchange,
    symbol: str,
    since_ms: int,
    *,
    limit: int = 1000,
    max_batches: int = 1000,
) -> pd.DataFrame:
    if not hasattr(exchange, "fetch_funding_rate_history"):
        raise NotImplementedError(f"{exchange.id} does not expose fetch_funding_rate_history via CCXT")
    all_rows: list[dict[str, Any]] = []
    current_since = since_ms
    for _ in range(max_batches):
        rows = exchange.fetch_funding_rate_history(symbol, since=current_since, limit=limit)
        if not rows:
            break
        all_rows.extend(rows)
        last_ts = rows[-1].get("timestamp")
        if last_ts is None:
            break
        next_since = int(last_ts) + 1
        if next_since <= current_since:
            break
        current_since = next_since
        time.sleep(exchange.rateLimit / 1000 if getattr(exchange, "rateLimit", None) else 0.2)
        if len(rows) < limit:
            break
    return _normalize_funding_rows(all_rows)


def update_funding_rate_file(
    exchange_name: str,
    symbol: str,
    since_iso: str,
    output_path: str | Path,
    *,
    rate_limit: bool = True,
) -> pd.DataFrame:
    output_path = Path(output_path)
    exchange = create_funding_exchange(exchange_name, rate_limit=rate_limit)
    existing = None
    if output_path.exists():
        existing = load_parquet(output_path)
        since_ms = int(pd.Timestamp(existing.index.max()).tz_convert("UTC").timestamp() * 1000) + 1 if not existing.empty else exchange.parse8601(since_iso)
    else:
        since_ms = exchange.parse8601(since_iso)
    new_df = fetch_funding_rate_history_paginated(exchange, symbol, since_ms)
    merged = merge_ohlcv(existing, new_df)
    save_parquet(merged, output_path)
    return merged
