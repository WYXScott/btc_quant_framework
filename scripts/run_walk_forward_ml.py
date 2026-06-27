from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.walk_forward import WalkForwardConfig, walk_forward_predict
from crypto_quant.strategy.ml_strategy import probability_signal
from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import save_backtest_reports
from crypto_quant.reporting.plots import plot_equity_curve, plot_drawdown


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(df)
    wf_cfg = WalkForwardConfig.from_config(cfg)
    pred_df, folds = walk_forward_predict(df, feature_columns, wf_cfg)
    pred_df = probability_signal(
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
    result = bt.run(pred_df, signal_col="signal")
    out_dir = resolve_path("reports/walk_forward_ml")
    out_dir.mkdir(parents=True, exist_ok=True)
    folds.to_csv(out_dir / "walk_forward_folds.csv", index=False, encoding="utf-8-sig")
    pred_df.to_parquet(out_dir / "walk_forward_predictions.parquet")
    report = save_backtest_reports(result, out_dir, prefix="walk_forward_ml", timeframe=cfg["data"]["timeframe"])
    plot_equity_curve(result, out_dir / "walk_forward_ml_equity.png", title="Walk-forward ML Equity")
    plot_drawdown(result, out_dir / "walk_forward_ml_drawdown.png", title="Walk-forward ML Drawdown")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
