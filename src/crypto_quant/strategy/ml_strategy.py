from __future__ import annotations

import pandas as pd


def probability_signal(
    df: pd.DataFrame,
    prob_col: str = "prob_up",
    buy_threshold: float = 0.58,
    exit_threshold: float = 0.50,
    trend_filter: bool = True,
    max_holding_bars: int | None = None,
) -> pd.DataFrame:
    """Convert model probability into long-only position signal.

    Uses simple hysteresis:
        - enter above buy_threshold;
        - stay until below exit_threshold;
        - optionally exit after max_holding_bars.
    """
    out = df.copy()
    in_position = False
    bars_in_position = 0
    signals = []
    exit_reasons = []

    for _, row in out.iterrows():
        prob = float(row.get(prob_col, 0.0))
        trend_ok = True
        if trend_filter and {"ma_24", "ma_120", "close"}.issubset(out.columns):
            trend_ok = bool(row["close"] > row["ma_120"] and row["ma_24"] > row["ma_120"])

        exit_reason = ""
        if not in_position and prob >= buy_threshold and trend_ok:
            in_position = True
            bars_in_position = 0
        elif in_position:
            bars_in_position += 1
            if prob <= exit_threshold:
                in_position = False
                bars_in_position = 0
                exit_reason = "probability_exit"
            elif not trend_ok:
                in_position = False
                bars_in_position = 0
                exit_reason = "trend_exit"
            elif max_holding_bars is not None and bars_in_position >= max_holding_bars:
                in_position = False
                bars_in_position = 0
                exit_reason = "time_exit"

        signals.append(1 if in_position else 0)
        exit_reasons.append(exit_reason)

    out["signal"] = signals
    out["signal_exit_reason"] = exit_reasons
    return out
