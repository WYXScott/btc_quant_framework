from __future__ import annotations

from itertools import product
from typing import Iterable

import pandas as pd

from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import performance_summary
from crypto_quant.backtest.trades import extract_long_trades, trade_summary
from crypto_quant.strategy.ml_strategy import probability_signal


def ml_threshold_leverage_scan(
    df: pd.DataFrame,
    leverages: Iterable[float],
    buy_thresholds: Iterable[float],
    exit_thresholds: Iterable[float],
    timeframe: str,
    initial_equity: float,
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
    prob_col: str = "prob_up",
    trend_filter: bool = True,
    max_holding_bars: int | None = None,
) -> pd.DataFrame:
    rows = []
    for leverage, buy_th, exit_th in product(leverages, buy_thresholds, exit_thresholds):
        if exit_th >= buy_th:
            continue
        signal_df = probability_signal(
            df,
            prob_col=prob_col,
            buy_threshold=float(buy_th),
            exit_threshold=float(exit_th),
            trend_filter=trend_filter,
            max_holding_bars=max_holding_bars,
        )
        bt = LeveragedBacktester(
            initial_equity=initial_equity,
            leverage=float(leverage),
            max_margin_fraction=max_margin_fraction,
            max_notional_fraction=max_notional_fraction,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            max_drawdown_stop_fraction=max_drawdown_stop_fraction,
        )
        result = bt.run(signal_df, signal_col="signal")
        summary = performance_summary(result, timeframe=timeframe)
        tsummary = trade_summary(extract_long_trades(result))
        rows.append({
            "leverage": float(leverage),
            "buy_threshold": float(buy_th),
            "exit_threshold": float(exit_th),
            **summary,
            **tsummary,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["calmar", "sharpe", "max_drawdown"], ascending=[False, False, False])
    return out
