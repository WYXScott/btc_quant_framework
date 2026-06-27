from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import performance_summary, save_backtest_reports
from crypto_quant.backtest.trades import extract_long_trades, trade_summary
from crypto_quant.reporting.plots import plot_equity_curve, plot_drawdown
from crypto_quant.strategy.library import build_strategy_signal, get_strategy_spec


def backtest_strategy_library(
    dataset: pd.DataFrame,
    strategy_names: Iterable[str],
    output_dir: str | Path,
    timeframe: str,
    initial_equity: float,
    leverage: float,
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
) -> pd.DataFrame:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for name in strategy_names:
        spec = get_strategy_spec(name)
        signal_df = build_strategy_signal(dataset, name)
        bt = LeveragedBacktester(
            initial_equity=initial_equity,
            leverage=leverage,
            max_margin_fraction=max_margin_fraction,
            max_notional_fraction=max_notional_fraction,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            max_drawdown_stop_fraction=max_drawdown_stop_fraction,
        )
        result = bt.run(signal_df, signal_col="signal")
        prefix = f"strategy_{spec.name}"
        strategy_dir = out_dir / spec.name
        summary = save_backtest_reports(result, strategy_dir, prefix=prefix, timeframe=timeframe)
        trades = extract_long_trades(result)
        summary.update(trade_summary(trades))
        summary.update({
            "strategy": spec.name,
            "description": spec.description,
            "bars": len(result),
            "exposure_mean": float(result.get("position", pd.Series(dtype=float)).mean()),
            "leverage": leverage,
        })
        rows.append(summary)
        plot_equity_curve(result, strategy_dir / f"{prefix}_equity.png", title=f"{spec.name} equity")
        plot_drawdown(result, strategy_dir / f"{prefix}_drawdown.png", title=f"{spec.name} drawdown")
    table = pd.DataFrame(rows)
    if not table.empty:
        preferred = ["strategy", "total_return", "cagr", "sharpe", "max_drawdown", "calmar", "trades", "win_rate", "profit_factor", "final_equity", "description"]
        remaining = [c for c in table.columns if c not in preferred]
        table = table[[c for c in preferred if c in table.columns] + remaining]
        table = table.sort_values(["calmar", "sharpe", "max_drawdown"], ascending=[False, False, False])
    table.to_csv(out_dir / "strategy_library_summary.csv", index=False, encoding="utf-8-sig")
    return table
