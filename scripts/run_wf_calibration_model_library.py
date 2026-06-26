from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.research.walk_forward_calibration_library import run_walk_forward_calibration_model_library


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    lib_cfg = cfg.get("walk_forward_calibration_library", {})
    out_dir = resolve_path(lib_cfg.get("output_path", "reports/walk_forward_calibration_model_library"))
    table = run_walk_forward_calibration_model_library(
        dataset=dataset,
        feature_columns=feature_columns,
        cfg=cfg,
        output_dir=out_dir,
        model_names=lib_cfg.get("models"),
        include_optional_if_installed=bool(lib_cfg.get("include_optional_if_installed", True)),
    )
    print(table.to_string(index=False) if not table.empty else "<empty>")
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
