from __future__ import annotations

import numpy as np
import pandas as pd


class DynamicExposureBacktester:
    """Single-asset backtester that consumes a precomputed target exposure series.

    exposure convention:
        0.0 = flat
        1.0 = 1x notional exposure relative to current equity
        3.0 = 3x notional exposure relative to current equity

    The exposure is shifted by one bar: a decision formed after bar close is applied
    to the next bar's return. Costs are charged on absolute exposure changes.
    """

    def __init__(
        self,
        initial_equity: float = 1000.0,
        max_notional_fraction: float = 3.0,
        fee_rate: float = 0.0005,
        slippage_rate: float = 0.0005,
        max_drawdown_stop_fraction: float = 0.20,
        min_equity_fraction: float = 0.05,
    ) -> None:
        self.initial_equity = float(initial_equity)
        self.max_notional_fraction = float(max_notional_fraction)
        self.fee_rate = float(fee_rate)
        self.slippage_rate = float(slippage_rate)
        self.max_drawdown_stop_fraction = float(max_drawdown_stop_fraction)
        self.min_equity_fraction = float(min_equity_fraction)
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        if self.max_notional_fraction <= 0:
            raise ValueError("max_notional_fraction must be positive")

    def run(self, df: pd.DataFrame, exposure_col: str = "target_exposure") -> pd.DataFrame:
        required = {"close", exposure_col}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Backtest data missing columns: {missing}")

        data = df.copy().sort_index()
        data[exposure_col] = pd.to_numeric(data[exposure_col], errors="coerce").fillna(0.0)
        data["target_exposure_raw"] = data[exposure_col]
        data["target_exposure"] = data[exposure_col].clip(lower=0.0, upper=self.max_notional_fraction)
        data["asset_return"] = data["close"].pct_change().fillna(0.0)

        # Decision after bar close -> next bar return.
        data["gross_exposure"] = data["target_exposure"].shift(1).fillna(0.0)
        data["position"] = (data["gross_exposure"] > 0).astype(int)
        data["turnover"] = data["gross_exposure"].diff().abs().fillna(data["gross_exposure"].abs())
        data["strategy_return_before_cost"] = data["gross_exposure"] * data["asset_return"]
        data["cost_return"] = data["turnover"] * (self.fee_rate + self.slippage_rate)
        data["strategy_return"] = data["strategy_return_before_cost"] - data["cost_return"]

        equity = [self.initial_equity]
        peak = self.initial_equity
        stopped = False
        stop_flags = [False]
        for ret in data["strategy_return"].iloc[1:]:
            if stopped:
                new_equity = equity[-1]
            else:
                # Prevent pathological leverage return from pushing equity negative in candle-level backtests.
                new_equity = equity[-1] * max(1.0 + float(ret), 0.0)
                peak = max(peak, new_equity)
                dd = new_equity / peak - 1.0 if peak > 0 else -1.0
                if dd <= -self.max_drawdown_stop_fraction or new_equity <= self.initial_equity * self.min_equity_fraction:
                    stopped = True
            equity.append(max(new_equity, 0.0))
            stop_flags.append(stopped)

        data["equity"] = equity
        data["trade_flag"] = (data["turnover"] > 1e-12).astype(int)
        data["risk_stopped"] = stop_flags
        return data


def realized_volatility(close: pd.Series, window: int, annualization: float) -> pd.Series:
    returns = close.pct_change()
    return returns.rolling(int(window)).std() * np.sqrt(float(annualization))
