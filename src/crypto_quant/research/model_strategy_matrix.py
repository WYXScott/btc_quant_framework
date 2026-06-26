from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import performance_summary
from crypto_quant.backtest.trades import extract_long_trades, trade_summary
from crypto_quant.models.walk_forward import WalkForwardConfig, walk_forward_predict
from crypto_quant.strategy.ml_strategy import probability_signal


def run_model_strategy_matrix(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    model_names: Iterable[str],
    walk_forward_config: WalkForwardConfig,
    output_dir: str | Path,
    timeframe: str,
    initial_equity: float,
    leverage: float,
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
    buy_threshold: float,
    exit_threshold: float,
    trend_filter: bool = True,
    max_holding_bars: int | None = None,
) -> pd.DataFrame:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    feature_columns = list(feature_columns)
    rows: list[dict[str, object]] = []
    all_folds: list[pd.DataFrame] = []

    for model_name in model_names:
        prob_col = f"prob_up_wf_{model_name}"
        pred_df, folds = walk_forward_predict(
            dataset,
            feature_columns,
            walk_forward_config,
            probability_col=prob_col,
            model_type=model_name,
        )
        signal_df = probability_signal(
            pred_df,
            prob_col=prob_col,
            buy_threshold=buy_threshold,
            exit_threshold=exit_threshold,
            trend_filter=trend_filter,
            max_holding_bars=max_holding_bars,
        )
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
        model_dir = out_dir / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        try:
            result.to_parquet(model_dir / f"{model_name}_strategy_result.parquet")
        except Exception:
            pass
        result.to_csv(model_dir / f"{model_name}_strategy_result.csv", encoding="utf-8-sig")
        trades = extract_long_trades(result)
        trades.to_csv(model_dir / f"{model_name}_trades.csv", index=False, encoding="utf-8-sig")
        folds = folds.copy()
        folds["model"] = model_name
        folds.to_csv(model_dir / f"{model_name}_walk_forward_folds.csv", index=False, encoding="utf-8-sig")
        all_folds.append(folds)
        summary = performance_summary(result, timeframe=timeframe)
        summary.update(trade_summary(trades))
        summary.update({
            "model": model_name,
            "bars": len(result),
            "buy_threshold": buy_threshold,
            "exit_threshold": exit_threshold,
            "leverage": leverage,
            "folds": len(folds),
            "mean_fold_roc_auc": float(folds["roc_auc"].mean()) if not folds.empty and "roc_auc" in folds else 0.0,
        })
        rows.append(summary)

    summary_table = pd.DataFrame(rows)
    if not summary_table.empty:
        preferred = ["model", "total_return", "cagr", "sharpe", "max_drawdown", "calmar", "num_trades", "win_rate", "profit_factor", "mean_fold_roc_auc", "final_equity"]
        remaining = [c for c in summary_table.columns if c not in preferred]
        summary_table = summary_table[[c for c in preferred if c in summary_table.columns] + remaining]
        summary_table = summary_table.sort_values(["calmar", "sharpe", "mean_fold_roc_auc"], ascending=[False, False, False])
    summary_table.to_csv(out_dir / "model_strategy_matrix_summary.csv", index=False, encoding="utf-8-sig")
    if all_folds:
        pd.concat(all_folds, ignore_index=True).to_csv(out_dir / "model_strategy_matrix_folds.csv", index=False, encoding="utf-8-sig")
    return summary_table
