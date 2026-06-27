from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.registry import available_models
from crypto_quant.models.walk_forward import WalkForwardConfig
from crypto_quant.research.model_strategy_matrix import run_model_strategy_matrix


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    matrix_cfg = cfg.get("model_strategy_matrix", {})
    models = matrix_cfg.get("models") or available_models()
    wf_cfg = WalkForwardConfig.from_config(cfg)
    out_dir = resolve_path(matrix_cfg.get("output_path", "reports/model_strategy_matrix"))
    summary = run_model_strategy_matrix(
        dataset=dataset,
        feature_columns=feature_columns,
        model_names=models,
        walk_forward_config=wf_cfg,
        output_dir=out_dir,
        timeframe=cfg["data"]["timeframe"],
        initial_equity=cfg["trading"]["initial_equity"],
        leverage=cfg["trading"]["leverage"],
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
        buy_threshold=cfg["model"]["probability_buy_threshold"],
        exit_threshold=cfg["model"]["probability_exit_threshold"],
        trend_filter=matrix_cfg.get("trend_filter", True),
        max_holding_bars=cfg["risk"].get("max_holding_bars"),
    )
    print(summary.to_string(index=False))
    print(f"feature_count={len(feature_columns)}")
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
