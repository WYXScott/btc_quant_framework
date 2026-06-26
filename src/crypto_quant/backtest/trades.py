from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class TradeRecord:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    entry_equity: float
    exit_equity: float
    exposure: float
    holding_bars: int
    asset_return: float
    net_return_on_equity: float
    pnl: float
    exit_reason: str


def extract_long_trades(result: pd.DataFrame) -> pd.DataFrame:
    """Extract approximate long-only trade records from a backtest result.

    The backtester is bar based. A trade starts when position changes from 0 to >0
    and ends when position returns to 0. PnL is measured from the recorded equity
    curve, so fees/slippage included by the backtester are reflected in the output.
    """
    required = {"close", "position", "equity"}
    missing = required - set(result.columns)
    if missing:
        raise ValueError(f"Cannot extract trades, missing columns: {missing}")

    df = result.copy().sort_index()
    prev_position = df["position"].shift(1).fillna(0.0)

    trades: list[TradeRecord] = []
    in_trade = False
    entry_idx = None
    entry_price = entry_equity = exposure = 0.0
    holding_bars = 0

    for ts, row in df.iterrows():
        pos = float(row["position"])
        prev_pos = float(prev_position.loc[ts])

        if not in_trade and pos > 0 and prev_pos <= 0:
            in_trade = True
            entry_idx = ts
            entry_price = float(row["close"])
            entry_equity = float(row["equity"])
            exposure = float(row.get("gross_exposure", pos))
            holding_bars = 0
            continue

        if in_trade:
            holding_bars += 1

        if in_trade and pos <= 0 and prev_pos > 0:
            exit_price = float(row["close"])
            exit_equity = float(row["equity"])
            asset_return = exit_price / entry_price - 1.0 if entry_price > 0 else 0.0
            net_return = exit_equity / entry_equity - 1.0 if entry_equity > 0 else 0.0
            trades.append(
                TradeRecord(
                    entry_time=entry_idx,
                    exit_time=ts,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    entry_equity=entry_equity,
                    exit_equity=exit_equity,
                    exposure=exposure,
                    holding_bars=holding_bars,
                    asset_return=asset_return,
                    net_return_on_equity=net_return,
                    pnl=exit_equity - entry_equity,
                    exit_reason="signal_exit",
                )
            )
            in_trade = False
            entry_idx = None

    if in_trade and entry_idx is not None:
        last_ts = df.index[-1]
        row = df.iloc[-1]
        exit_price = float(row["close"])
        exit_equity = float(row["equity"])
        asset_return = exit_price / entry_price - 1.0 if entry_price > 0 else 0.0
        net_return = exit_equity / entry_equity - 1.0 if entry_equity > 0 else 0.0
        trades.append(
            TradeRecord(
                entry_time=entry_idx,
                exit_time=last_ts,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_equity=entry_equity,
                exit_equity=exit_equity,
                exposure=exposure,
                holding_bars=holding_bars,
                asset_return=asset_return,
                net_return_on_equity=net_return,
                pnl=exit_equity - entry_equity,
                exit_reason="end_of_backtest",
            )
        )

    if not trades:
        return pd.DataFrame(
            columns=[
                "entry_time", "exit_time", "entry_price", "exit_price", "entry_equity",
                "exit_equity", "exposure", "holding_bars", "asset_return",
                "net_return_on_equity", "pnl", "exit_reason",
            ]
        )

    return pd.DataFrame([t.__dict__ for t in trades])


def trade_summary(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {
            "num_trades": 0,
            "win_rate": 0.0,
            "avg_net_return_on_equity": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "avg_holding_bars": 0.0,
            "total_pnl": 0.0,
        }
    pnl = trades["pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    profit_factor = wins.sum() / abs(losses.sum()) if losses.sum() < 0 else float("inf")
    return {
        "num_trades": int(len(trades)),
        "win_rate": float((pnl > 0).mean()),
        "avg_net_return_on_equity": float(trades["net_return_on_equity"].mean()),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(profit_factor),
        "avg_holding_bars": float(trades["holding_bars"].mean()),
        "total_pnl": float(pnl.sum()),
    }
