from __future__ import annotations

import pandas as pd


class LeveragedBacktester:
    """Simple single-asset leveraged backtester.

    signal convention:
        0 = flat
        1 = long

    The model assumes exposure = margin_fraction * leverage.
    Fees and slippage are charged on traded notional.
    """

    def __init__(
        self,
        initial_equity: float = 1000.0,
        leverage: float = 3.0,
        max_margin_fraction: float = 0.30,
        max_notional_fraction: float = 3.0,
        fee_rate: float = 0.0005,
        slippage_rate: float = 0.0005,
        max_drawdown_stop_fraction: float = 0.20,
    ) -> None:
        if leverage <= 0:
            raise ValueError("leverage must be positive")
        self.initial_equity = float(initial_equity)
        self.leverage = float(leverage)
        self.max_margin_fraction = float(max_margin_fraction)
        self.max_notional_fraction = float(max_notional_fraction)
        self.fee_rate = float(fee_rate)
        self.slippage_rate = float(slippage_rate)
        self.max_drawdown_stop_fraction = float(max_drawdown_stop_fraction)

    def run(self, df: pd.DataFrame, signal_col: str = "signal") -> pd.DataFrame:
        required = {"close", signal_col}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Backtest data missing columns: {missing}")

        data = df.copy().sort_index()
        data["asset_return"] = data["close"].pct_change().fillna(0.0)
        data["raw_signal"] = data[signal_col].fillna(0).clip(0, 1)

        # Shift signal: decision after bar close acts on next bar return.
        data["position"] = data["raw_signal"].shift(1).fillna(0.0)

        margin_fraction = min(self.max_margin_fraction, self.max_notional_fraction / self.leverage)
        exposure = data["position"] * margin_fraction * self.leverage
        data["gross_exposure"] = exposure

        data["turnover"] = exposure.diff().abs().fillna(exposure.abs())
        trading_cost = data["turnover"] * (self.fee_rate + self.slippage_rate)
        data["strategy_return_before_cost"] = exposure * data["asset_return"]
        data["cost_return"] = trading_cost
        data["strategy_return"] = data["strategy_return_before_cost"] - data["cost_return"]

        equity = [self.initial_equity]
        peak = self.initial_equity
        stopped = False
        stop_flags = [False]

        for ret in data["strategy_return"].iloc[1:]:
            if stopped:
                new_equity = equity[-1]
            else:
                new_equity = equity[-1] * (1 + ret)
                peak = max(peak, new_equity)
                dd = new_equity / peak - 1
                if dd <= -self.max_drawdown_stop_fraction:
                    stopped = True
            equity.append(max(new_equity, 0.0))
            stop_flags.append(stopped)

        data["equity"] = equity
        data["trade_flag"] = (data["turnover"] > 0).astype(int)
        data["risk_stopped"] = stop_flags
        return data
