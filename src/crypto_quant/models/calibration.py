from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from crypto_quant.models.registry import make_model_by_name
from crypto_quant.models.train_direction_model import time_split


def _clip_probability(prob: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.clip(np.asarray(prob, dtype=float), eps, 1.0 - eps)


def positive_proba(model, X: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(X)[:, 1], dtype=float)
    if hasattr(model, "decision_function"):
        score = np.asarray(model.decision_function(X), dtype=float)
        return 1.0 / (1.0 + np.exp(-score))
    return np.asarray(model.predict(X), dtype=float)


@dataclass
class CalibratedProbabilityModel:
    """Base classifier plus a post-hoc probability calibrator.

    The base model is trained only on the training period. The calibrator is fit
    on the validation period using base-model probabilities as input. This keeps
    calibration separate from the test period and makes the saved object safe for
    later inference in backtests/paper mode.
    """

    base_model: object
    method: str
    calibrator: object | None
    feature_columns: list[str]
    train_end: str
    valid_end: str
    base_model_type: str

    def raw_predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return _clip_probability(positive_proba(self.base_model, X[self.feature_columns]))

    def predict_calibrated_proba(self, X: pd.DataFrame) -> np.ndarray:
        raw = self.raw_predict_proba(X)
        if self.calibrator is None or self.method == "none":
            return raw
        if self.method == "isotonic":
            return _clip_probability(self.calibrator.predict(raw))
        if self.method in {"sigmoid", "platt"}:
            return _clip_probability(self.calibrator.predict_proba(raw.reshape(-1, 1))[:, 1])
        raise ValueError(f"Unknown calibration method: {self.method}")

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        p = self.predict_calibrated_proba(X)
        return np.column_stack([1.0 - p, p])

    def predict(self, X: pd.DataFrame, threshold: float = 0.5) -> np.ndarray:
        return (self.predict_calibrated_proba(X) >= float(threshold)).astype(int)


def fit_probability_calibrator(raw_prob: np.ndarray, y_true: pd.Series, method: str = "isotonic") -> object | None:
    method = str(method).strip().lower()
    raw_prob = _clip_probability(raw_prob)
    y = np.asarray(y_true, dtype=int)
    if method == "none":
        return None
    if len(np.unique(y)) < 2:
        raise ValueError("Calibration validation labels contain only one class; cannot calibrate.")
    if method == "isotonic":
        # out_of_bounds='clip' is important when live probabilities exceed validation range.
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(raw_prob, y)
        return calibrator
    if method in {"sigmoid", "platt"}:
        calibrator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000, random_state=42)
        calibrator.fit(raw_prob.reshape(-1, 1), y)
        return calibrator
    raise ValueError("method must be one of: isotonic, sigmoid, none")


def probability_metrics(y_true: pd.Series, prob: np.ndarray, bins: int = 10) -> dict[str, float]:
    y = np.asarray(y_true, dtype=int)
    p = _clip_probability(prob)
    out = {
        "samples": float(len(y)),
        "positive_rate": float(np.mean(y)) if len(y) else 0.0,
        "mean_probability": float(np.mean(p)) if len(p) else 0.0,
        "brier_score": float(brier_score_loss(y, p)) if len(y) else 0.0,
    }
    try:
        out["roc_auc"] = float(roc_auc_score(y, p))
    except ValueError:
        out["roc_auc"] = 0.0
    try:
        out["log_loss"] = float(log_loss(y, p))
    except ValueError:
        out["log_loss"] = 0.0
    rel = reliability_table(y, p, bins=bins)
    if rel.empty:
        out["ece"] = 0.0
        out["mce"] = 0.0
    else:
        total = max(float(rel["count"].sum()), 1.0)
        errors = (rel["actual_positive_rate"] - rel["prob_mean"]).abs()
        out["ece"] = float((errors * rel["count"] / total).sum())
        out["mce"] = float(errors.max())
    return out


def reliability_table(
    y_true: pd.Series | np.ndarray,
    prob: np.ndarray,
    future_return: pd.Series | None = None,
    bins: int = 10,
) -> pd.DataFrame:
    frame = pd.DataFrame({"prob": _clip_probability(prob), "label": np.asarray(y_true, dtype=int)})
    if future_return is not None:
        frame["future_return"] = np.asarray(future_return, dtype=float)
    frame["bucket"] = pd.cut(frame["prob"], bins=np.linspace(0, 1, int(bins) + 1), include_lowest=True)
    rows = []
    for bucket, chunk in frame.groupby("bucket", observed=False):
        if chunk.empty:
            continue
        row = {
            "bucket": str(bucket),
            "count": int(len(chunk)),
            "prob_mean": float(chunk["prob"].mean()),
            "actual_positive_rate": float(chunk["label"].mean()),
            "calibration_error": float(abs(chunk["label"].mean() - chunk["prob"].mean())),
        }
        if "future_return" in chunk:
            row["future_return_mean"] = float(chunk["future_return"].mean())
            row["future_return_median"] = float(chunk["future_return"].median())
        rows.append(row)
    return pd.DataFrame(rows)


def train_calibrated_direction_model(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    train_end: str,
    valid_end: str,
    model_path: str | Path,
    feature_list_path: str | Path,
    model_type: str = "extra_trees",
    calibration_method: str = "isotonic",
    label_col: str = "label_up",
    future_return_col: str = "future_return",
    bins: int = 10,
) -> dict[str, object]:
    feature_columns = list(feature_columns)
    train, valid, test = time_split(dataset.sort_index(), train_end=train_end, valid_end=valid_end)
    if train.empty or valid.empty:
        raise ValueError("Training and validation periods must both be non-empty for probability calibration.")
    eval_df = test if not test.empty else valid

    base_model = make_model_by_name(model_type)
    base_model.fit(train[feature_columns], train[label_col])

    valid_raw = positive_proba(base_model, valid[feature_columns])
    calibrator = fit_probability_calibrator(valid_raw, valid[label_col], method=calibration_method)
    calibrated = CalibratedProbabilityModel(
        base_model=base_model,
        method=calibration_method,
        calibrator=calibrator,
        feature_columns=feature_columns,
        train_end=train_end,
        valid_end=valid_end,
        base_model_type=model_type,
    )

    raw_eval = calibrated.raw_predict_proba(eval_df[feature_columns])
    cal_eval = calibrated.predict_calibrated_proba(eval_df[feature_columns])
    metrics = {
        "raw": probability_metrics(eval_df[label_col], raw_eval, bins=bins),
        "calibrated": probability_metrics(eval_df[label_col], cal_eval, bins=bins),
    }
    metrics["improvement"] = {
        "brier_score_delta_calibrated_minus_raw": float(metrics["calibrated"]["brier_score"] - metrics["raw"]["brier_score"]),
        "ece_delta_calibrated_minus_raw": float(metrics["calibrated"]["ece"] - metrics["raw"]["ece"]),
        "log_loss_delta_calibrated_minus_raw": float(metrics["calibrated"]["log_loss"] - metrics["raw"]["log_loss"]),
    }

    future = eval_df[future_return_col] if future_return_col in eval_df else None
    reliability_raw = reliability_table(eval_df[label_col], raw_eval, future_return=future, bins=bins)
    reliability_cal = reliability_table(eval_df[label_col], cal_eval, future_return=future, bins=bins)
    predictions = eval_df[["close", label_col] + ([future_return_col] if future_return_col in eval_df else [])].copy()
    predictions["prob_up_raw"] = raw_eval
    predictions["prob_up_calibrated"] = cal_eval

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(calibrated, model_path)
    feature_list_path = Path(feature_list_path)
    feature_list_path.parent.mkdir(parents=True, exist_ok=True)
    feature_list_path.write_text("\n".join(feature_columns), encoding="utf-8")

    return {
        "model": calibrated,
        "metrics": metrics,
        "reliability_raw": reliability_raw,
        "reliability_calibrated": reliability_cal,
        "predictions": predictions,
    }


def load_calibrated_model(path: str | Path) -> CalibratedProbabilityModel:
    model = joblib.load(path)
    if not hasattr(model, "predict_calibrated_proba"):
        raise TypeError(f"Loaded object is not a CalibratedProbabilityModel: {path}")
    return model
