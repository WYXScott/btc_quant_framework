from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.features.feature_builder import get_model_feature_columns
from crypto_quant.realism.validation import evaluate_purged_embargo_cv, save_validation_artifacts


def main() -> None:
    cfg = load_config()
    val_cfg = cfg.get("validation", {})
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    feature_columns = get_model_feature_columns(dataset)
    metrics, preds = evaluate_purged_embargo_cv(
        dataset,
        feature_columns,
        model_type=val_cfg.get("model_type", "extra_trees"),
        n_splits=int(val_cfg.get("n_splits", 5)),
        label_horizon_bars=int(cfg["labels"].get("horizon_bars", 6)),
        embargo_bars=int(val_cfg.get("embargo_bars", cfg["labels"].get("horizon_bars", 6))),
        min_train_bars=int(val_cfg.get("min_train_bars", 1000)),
    )
    paths = save_validation_artifacts(metrics, preds, resolve_path(val_cfg.get("output_path", "reports/validation")))
    print("Purged/embargo CV folds:", len(metrics))
    if not metrics.empty:
        print(metrics[["fold_id", "train_bars", "test_bars", "roc_auc", "accuracy", "brier_score"]].to_string(index=False))
    for key, value in paths.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
