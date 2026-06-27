from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from crypto_quant.models.registry import make_model_by_name
from crypto_quant.models.train_direction_model import time_split


@dataclass
class ModelDiagnosticResult:
    metrics: dict[str, float]
    threshold_table: pd.DataFrame
    feature_importance: pd.DataFrame
    calibration_table: pd.DataFrame
    predictions: pd.DataFrame


def _positive_proba(model, X: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    if hasattr(model, "decision_function"):
        score = model.decision_function(X)
        return 1.0 / (1.0 + np.exp(-score))
    pred = model.predict(X)
    return np.asarray(pred, dtype=float)


def classifier_metric_summary(y_true: pd.Series, prob: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    pred = (prob >= threshold).astype(int)
    out = {
        "samples": float(len(y_true)),
        "positive_rate": float(np.mean(y_true)),
        "mean_probability": float(np.mean(prob)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "brier_score": float(brier_score_loss(y_true, prob)),
    }
    try:
        out["roc_auc"] = float(roc_auc_score(y_true, prob))
    except ValueError:
        out["roc_auc"] = 0.0
    try:
        clipped = np.clip(prob, 1e-6, 1 - 1e-6)
        out["log_loss"] = float(log_loss(y_true, clipped))
    except ValueError:
        out["log_loss"] = 0.0
    return out


def threshold_diagnostics(
    y_true: pd.Series,
    prob: np.ndarray,
    thresholds: Iterable[float] = tuple(np.round(np.arange(0.45, 0.76, 0.025), 3)),
) -> pd.DataFrame:
    rows = []
    y = np.asarray(y_true, dtype=int)
    for th in thresholds:
        pred = (prob >= float(th)).astype(int)
        selected = pred == 1
        selected_n = int(selected.sum())
        rows.append({
            "threshold": float(th),
            "selected_n": selected_n,
            "selected_rate": float(selected.mean()),
            "precision": float(precision_score(y, pred, zero_division=0)),
            "recall": float(recall_score(y, pred, zero_division=0)),
            "f1": float(f1_score(y, pred, zero_division=0)),
            "avg_future_return_selected": np.nan,
        })
    return pd.DataFrame(rows)


def probability_bucket_table(
    y_true: pd.Series,
    prob: np.ndarray,
    future_return: pd.Series | None = None,
    bins: int = 10,
) -> pd.DataFrame:
    frame = pd.DataFrame({"prob": prob, "label": np.asarray(y_true, dtype=int)}, index=y_true.index)
    if future_return is not None:
        frame["future_return"] = future_return.reindex(frame.index)
    frame["bucket"] = pd.cut(frame["prob"], bins=np.linspace(0, 1, bins + 1), include_lowest=True)
    rows = []
    for bucket, chunk in frame.groupby("bucket", observed=False):
        if chunk.empty:
            continue
        row = {
            "bucket": str(bucket),
            "count": int(len(chunk)),
            "prob_mean": float(chunk["prob"].mean()),
            "actual_positive_rate": float(chunk["label"].mean()),
        }
        if "future_return" in chunk:
            row["future_return_mean"] = float(chunk["future_return"].mean())
            row["future_return_median"] = float(chunk["future_return"].median())
        rows.append(row)
    return pd.DataFrame(rows)


def model_feature_importance(model, X: pd.DataFrame, y: pd.Series, n_repeats: int = 5) -> pd.DataFrame:
    names = list(X.columns)
    fitted_model = model
    # Pipeline with a named ExtraTrees step exposes impurity importances directly.
    direct_importance = None
    try:
        estimator = getattr(fitted_model, "named_steps", {}).get("model")
        if estimator is not None and hasattr(estimator, "feature_importances_"):
            direct_importance = np.asarray(estimator.feature_importances_, dtype=float)
    except Exception:
        direct_importance = None

    rows = []
    if direct_importance is not None and len(direct_importance) == len(names):
        for name, val in zip(names, direct_importance):
            rows.append({"feature": name, "importance": float(val), "importance_type": "model_feature_importance"})
        out = pd.DataFrame(rows).sort_values("importance", ascending=False)
        out["rank"] = np.arange(1, len(out) + 1)
        return out[["rank", "feature", "importance", "importance_type"]]

    perm = permutation_importance(fitted_model, X, y, n_repeats=n_repeats, random_state=42, n_jobs=-1)
    out = pd.DataFrame({
        "feature": names,
        "importance": perm.importances_mean,
        "importance_std": perm.importances_std,
        "importance_type": "permutation_importance",
    }).sort_values("importance", ascending=False)
    out["rank"] = np.arange(1, len(out) + 1)
    return out[["rank", "feature", "importance", "importance_std", "importance_type"]]


def train_validation_diagnostics(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    train_end: str,
    valid_end: str,
    model_type: str = "extra_trees",
    purge_bars: int = 0,
    label_col: str = "label_up",
    future_return_col: str = "future_return",
) -> ModelDiagnosticResult:
    feature_columns = list(feature_columns)
    data = dataset.copy().sort_index()
    train, valid, test = time_split(data, train_end=train_end, valid_end=valid_end, purge_bars=purge_bars)
    eval_df = test if not test.empty else valid
    if train.empty or eval_df.empty:
        raise ValueError("Not enough data for diagnostics. Check train_end/valid_end or dataset date range.")
    if train[label_col].nunique(dropna=True) < 2:
        raise ValueError("Training split contains a single label class; adjust dates or label threshold.")

    model = make_model_by_name(model_type)
    model.fit(train[feature_columns], train[label_col])
    prob = _positive_proba(model, eval_df[feature_columns])
    metrics = classifier_metric_summary(eval_df[label_col], prob, threshold=0.5)
    thresholds = threshold_diagnostics(eval_df[label_col], prob)
    if future_return_col in eval_df:
        tmp = pd.DataFrame({"prob": prob, "future_return": eval_df[future_return_col].values})
        for idx, row in thresholds.iterrows():
            selected = tmp["prob"] >= row["threshold"]
            thresholds.loc[idx, "avg_future_return_selected"] = float(tmp.loc[selected, "future_return"].mean()) if selected.any() else np.nan
    fi = model_feature_importance(model, eval_df[feature_columns], eval_df[label_col])
    calib = probability_bucket_table(
        eval_df[label_col],
        prob,
        future_return=eval_df[future_return_col] if future_return_col in eval_df else None,
        bins=10,
    )
    try:
        frac_pos, mean_pred = calibration_curve(eval_df[label_col], prob, n_bins=10, strategy="uniform")
        curve = pd.DataFrame({"mean_predicted_probability": mean_pred, "fraction_of_positives": frac_pos})
        calib = calib.merge(curve, left_index=True, right_index=True, how="left")
    except Exception:
        pass
    preds = eval_df[["close", label_col] + ([future_return_col] if future_return_col in eval_df else [])].copy()
    preds["prob_up_diag"] = prob
    preds["pred_label_0p5"] = (prob >= 0.5).astype(int)
    return ModelDiagnosticResult(metrics=metrics, threshold_table=thresholds, feature_importance=fi, calibration_table=calib, predictions=preds)
