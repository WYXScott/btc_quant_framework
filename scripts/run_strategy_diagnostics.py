from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.walk_forward import WalkForwardConfig, walk_forward_predict
from crypto_quant.strategy.ml_strategy import probability_signal
from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import performance_summary
from crypto_quant.reporting.plots import plot_equity_curve, plot_drawdown
from crypto_quant.research.strategy_diagnostics import strategy_diagnostic_tables


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(df)
    wf_cfg = WalkForwardConfig(
        train_window_days=cfg["walk_forward"]["train_window_days"],
        test_window_days=cfg["walk_forward"]["test_window_days"],
        min_train_bars=cfg["walk_forward"]["min_train_bars"],
        start=cfg["walk_forward"].get("start"),
        end=cfg["walk_forward"].get("end"),
    )
    pred_df, folds = walk_forward_predict(df, feature_columns, wf_cfg, probability_col="prob_up_wf")
    signal_df = probability_signal(
        pred_df,
        prob_col="prob_up_wf",
        buy_threshold=cfg["model"]["probability_buy_threshold"],
        exit_threshold=cfg["model"]["probability_exit_threshold"],
        trend_filter=True,
        max_holding_bars=cfg["risk"].get("max_holding_bars"),
    )
    bt = LeveragedBacktester(
        initial_equity=cfg["trading"]["initial_equity"],
        leverage=cfg["trading"]["leverage"],
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
    )
    result = bt.run(signal_df, signal_col="signal")
    out_dir = resolve_path("reports/strategy_diagnostics")
    out_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_dir / "strategy_result.csv", encoding="utf-8-sig")
    folds.to_csv(out_dir / "walk_forward_folds.csv", index=False, encoding="utf-8-sig")
    summary = performance_summary(result, timeframe=cfg["data"]["timeframe"])
    (out_dir / "strategy_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    for name, table in strategy_diagnostic_tables(result, timeframe=cfg["data"]["timeframe"]).items():
        table.to_csv(out_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
    plot_equity_curve(result, out_dir / "strategy_equity.png", title="V1.2 Walk-forward Strategy Equity")
    plot_drawdown(result, out_dir / "strategy_drawdown.png", title="V1.2 Walk-forward Strategy Drawdown")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
