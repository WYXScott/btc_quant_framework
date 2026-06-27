from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from crypto_quant.models.registry import make_model_by_name, MODEL_REGISTRY
from crypto_quant.models.train_direction_model import time_split, evaluate_classifier
from crypto_quant.research.model_diagnostics import classifier_metric_summary, threshold_diagnostics, probability_bucket_table


def _predict_prob(model, X: pd.DataFrame) -> np.ndarray:
    if len(X) == 0:
        return np.array([], dtype=float)
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    score = model.decision_function(X)
    return 1.0 / (1.0 + np.exp(-score))


def _extract_importance(model, feature_columns: list[str]) -> pd.DataFrame:
    final_model = model.named_steps.get("model") if hasattr(model, "named_steps") else model
    if hasattr(final_model, "feature_importances_"):
        values = np.asarray(final_model.feature_importances_, dtype=float)
    elif hasattr(final_model, "coef_"):
        values = np.abs(np.asarray(final_model.coef_).ravel())
    else:
        values = np.zeros(len(feature_columns), dtype=float)
    if len(values) != len(feature_columns):
        values = np.resize(values, len(feature_columns))
    table = pd.DataFrame({"feature": feature_columns, "importance": values})
    total = table["importance"].sum()
    if total > 0:
        table["importance_norm"] = table["importance"] / total
    else:
        table["importance_norm"] = 0.0
    return table.sort_values("importance", ascending=False)


def evaluate_model_library(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    model_names: Iterable[str],
    train_end: str,
    valid_end: str,
    output_dir: str | Path,
    thresholds: Iterable[float] = (0.5, 0.55, 0.58, 0.6, 0.65),
    calibration_bins: int = 10,
    purge_bars: int = 0,
) -> pd.DataFrame:
    feature_columns = list(feature_columns)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train, valid, test = time_split(dataset, train_end=train_end, valid_end=valid_end, purge_bars=purge_bars)
    rows: list[dict[str, object]] = []

    for name in model_names:
        model = make_model_by_name(name)
        model_dir = out_dir / name
        model_dir.mkdir(parents=True, exist_ok=True)
        X_train, y_train = train[feature_columns], train["label_up"]
        X_valid, y_valid = valid[feature_columns], valid["label_up"]
        X_test, y_test = test[feature_columns], test["label_up"]
        if train.empty:
            raise ValueError("Training split is empty after applying train_end and purge_bars.")
        if y_train.nunique(dropna=True) < 2:
            raise ValueError("Training split contains a single label class; adjust dates or label threshold.")
        model.fit(X_train, y_train)

        split_frames = []
        for split_name, X, y in [("train", X_train, y_train), ("valid", X_valid, y_valid), ("test", X_test, y_test)]:
            if len(X) == 0:
                metrics = {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "roc_auc": 0.0, "brier_score": 0.0, "log_loss": 0.0}
                prob = np.array([], dtype=float)
            else:
                metrics = evaluate_classifier(model, X, y)
                prob = _predict_prob(model, X)
                metrics.update(classifier_metric_summary(y, prob))
            rows.append({
                "model": name,
                "split": split_name,
                "description": MODEL_REGISTRY.get(name).description if name in MODEL_REGISTRY else "",
                "samples": len(X),
                **metrics,
            })
            if len(X):
                pred = pd.DataFrame({"label_up": y, "prob_up": prob}, index=X.index)
                pred["split"] = split_name
                split_frames.append(pred)
                if split_name in {"valid", "test"}:
                    threshold_diagnostics(y, prob, thresholds=thresholds).to_csv(
                        model_dir / f"{split_name}_threshold_diagnostics.csv", index=False, encoding="utf-8-sig"
                    )
                    probability_bucket_table(y, prob, bins=calibration_bins).to_csv(
                        model_dir / f"{split_name}_calibration_table.csv", index=False, encoding="utf-8-sig"
                    )
        if split_frames:
            pd.concat(split_frames).to_csv(model_dir / "predictions.csv", encoding="utf-8-sig")
        _extract_importance(model, feature_columns).to_csv(model_dir / "feature_importance.csv", index=False, encoding="utf-8-sig")

    summary = pd.DataFrame(rows)
    if not summary.empty:
        summary = summary.sort_values(["split", "roc_auc", "brier_score"], ascending=[True, False, True])
    summary.to_csv(out_dir / "model_library_summary.csv", index=False, encoding="utf-8-sig")
    return summary
