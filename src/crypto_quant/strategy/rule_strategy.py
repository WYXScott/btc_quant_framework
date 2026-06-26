from __future__ import annotations

import pandas as pd


def ma_trend_signal(
    df: pd.DataFrame,
    fast_col: str = "ma_24",
    slow_col: str = "ma_120",
    close_col: str = "close",
    vol_filter_col: str | None = "vol_ratio_24_120",
    max_vol_ratio: float = 2.5,
) -> pd.DataFrame:
    """Long-only BTC trend-following baseline.

    For 4h bars, ma_24 ~ 4 days and ma_120 ~ 20 days.
    """
    out = df.copy()
    signal = (out[close_col] > out[slow_col]) & (out[fast_col] > out[slow_col])
    if vol_filter_col and vol_filter_col in out.columns:
        signal = signal & (out[vol_filter_col] < max_vol_ratio)
    out["signal"] = signal.astype(int)
    return out
