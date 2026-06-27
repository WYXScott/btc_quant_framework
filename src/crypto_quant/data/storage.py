from __future__ import annotations

from pathlib import Path
import pandas as pd


def ensure_utc_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with a UTC DatetimeIndex.

    Historical datasets may be written by different parquet engines or older
    scripts. Normalizing here keeps incremental updates from failing on
    tz-naive indexes and makes merges deterministic.
    """
    out = df.copy()
    if out.empty:
        return out
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True, errors="raise")
    elif out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    return out.sort_index()


def save_parquet(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=True)


def load_parquet(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return pd.read_parquet(path)


def merge_ohlcv(existing: pd.DataFrame | None, new_data: pd.DataFrame) -> pd.DataFrame:
    if existing is None or existing.empty:
        out = new_data.copy()
    else:
        existing = ensure_utc_datetime_index(existing)
        new_data = ensure_utc_datetime_index(new_data) if not new_data.empty else new_data.copy()
        out = pd.concat([existing, new_data], axis=0)
    if not out.empty:
        out = ensure_utc_datetime_index(out)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out
