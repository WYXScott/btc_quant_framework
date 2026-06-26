from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.models.train_direction_model import train_direction_model


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    metrics = train_direction_model(
        dataset=dataset,
        feature_columns=feature_columns,
        train_end=cfg["model"]["train_end"],
        valid_end=cfg["model"]["valid_end"],
        model_path=resolve_path(cfg["model"]["model_path"]),
        feature_list_path=resolve_path(cfg["model"]["feature_list_path"]),
    )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"feature_count={len(feature_columns)}")


if __name__ == "__main__":
    main()
