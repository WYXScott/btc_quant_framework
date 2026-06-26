from __future__ import annotations

import pandas as pd


def add_future_return_label(
    df: pd.DataFrame,
    horizon_bars: int = 6,
    positive_return_threshold: float = 0.0,
) -> pd.DataFrame:
    out = df.copy()
    out["future_return"] = out["close"].shift(-horizon_bars) / out["close"] - 1
    out["label_up"] = (out["future_return"] > positive_return_threshold).astype(int)
    out = out.iloc[:-horizon_bars].copy()
    return out
