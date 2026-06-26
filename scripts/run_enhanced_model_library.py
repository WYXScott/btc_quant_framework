from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.research.enhanced_model_library import run_enhanced_model_library


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    lib_cfg = cfg.get("enhanced_model_library", cfg.get("model_library", {}))
    out_dir = resolve_path(lib_cfg.get("output_path", "reports/enhanced_model_library"))
    payload = run_enhanced_model_library(
        dataset=dataset,
        feature_columns=feature_columns,
        model_names=lib_cfg.get("models"),
        train_end=cfg["model"]["train_end"],
        valid_end=cfg["model"]["valid_end"],
        output_dir=out_dir,
        thresholds=lib_cfg.get("thresholds", [0.5, 0.55, 0.58, 0.6, 0.65]),
        calibration_bins=cfg.get("research", {}).get("calibration_bins", cfg.get("calibration", {}).get("bins", 10)),
        include_optional_if_installed=bool(lib_cfg.get("include_optional_if_installed", True)),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    print(f"feature_count={len(feature_columns)}")
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
