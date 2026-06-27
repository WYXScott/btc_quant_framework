from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.walk_forward import WalkForwardConfig, walk_forward_predict
from crypto_quant.research.robustness import ml_walk_forward_threshold_grid


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    rob_cfg = cfg.get("robustness", {})
    wf_cfg = WalkForwardConfig.from_config(cfg)
    model_name = cfg.get("model_strategy_matrix", {}).get("models", ["extra_trees"])[0]
    prob_col = f"prob_up_wf_{model_name}"
    pred_df, folds = walk_forward_predict(
        dataset,
        feature_columns,
        wf_cfg,
        probability_col=prob_col,
        model_type=model_name,
    )
    out_dir = resolve_path(rob_cfg.get("ml_threshold_grid_path", "reports/robustness/ml_threshold_grid"))
    out_dir.mkdir(parents=True, exist_ok=True)
    folds.to_csv(out_dir / "ml_threshold_grid_folds.csv", index=False, encoding="utf-8-sig")
    table = ml_walk_forward_threshold_grid(
        pred_df=pred_df,
        output_dir=out_dir,
        timeframe=cfg["data"]["timeframe"],
        initial_equity=cfg["trading"]["initial_equity"],
        leverage=cfg["trading"]["leverage"],
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
        prob_col=prob_col,
        buy_thresholds=rob_cfg.get("ml_buy_thresholds", cfg.get("scan", {}).get("buy_thresholds", [0.58])),
        exit_thresholds=rob_cfg.get("ml_exit_thresholds", cfg.get("scan", {}).get("exit_thresholds", [0.50])),
        trend_filter_values=rob_cfg.get("ml_trend_filter_values", [True]),
        max_holding_values=rob_cfg.get("ml_max_holding_bars", [cfg.get("risk", {}).get("max_holding_bars", 12)]),
        n_segments=int(rob_cfg.get("n_segments", 6)),
    )
    print(table.head(30).to_string(index=False))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
