from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.research.sequence_experiments import SequenceExperimentConfig, run_sequence_model_experiments


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    seq_cfg = SequenceExperimentConfig.from_config(cfg)
    out_dir = resolve_path(cfg.get("sequence_models", {}).get("output_path", "reports/sequence_models"))
    payload = run_sequence_model_experiments(dataset, feature_columns, out_dir, seq_cfg)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    print(f"feature_count={len(feature_columns)}")
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
