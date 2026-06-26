from __future__ import annotations

from pathlib import Path
import pandas as pd


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
        out = pd.concat([existing, new_data], axis=0)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out
