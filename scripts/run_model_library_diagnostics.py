from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.registry import available_models
from crypto_quant.research.model_library import evaluate_model_library


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    lib_cfg = cfg.get("model_library", {})
    models = lib_cfg.get("models") or available_models()
    out_dir = resolve_path(lib_cfg.get("output_path", "reports/model_library"))
    summary = evaluate_model_library(
        dataset=dataset,
        feature_columns=feature_columns,
        model_names=models,
        train_end=cfg["model"]["train_end"],
        valid_end=cfg["model"]["valid_end"],
        output_dir=out_dir,
        thresholds=lib_cfg.get("thresholds", [0.5, 0.55, 0.58, 0.6, 0.65]),
        calibration_bins=cfg.get("research", {}).get("calibration_bins", 10),
    )
    print(summary.to_string(index=False))
    print(f"feature_count={len(feature_columns)}")
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
