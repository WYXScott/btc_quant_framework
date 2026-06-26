from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.walk_forward_calibration import run_walk_forward_calibration_pipeline


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    out_dir = resolve_path(cfg.get("walk_forward_calibration", {}).get("output_path", "reports/walk_forward_calibration"))
    summary = run_walk_forward_calibration_pipeline(dataset, feature_columns, cfg, out_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
