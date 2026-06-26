from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
from typing import Iterable

import pandas as pd

from crypto_quant.models.registry import make_model_by_name
from crypto_quant.models.train_direction_model import evaluate_classifier


@dataclass
class PurgedFold:
    fold_id: int
    train_start: str | None
    train_end: str | None
    test_start: str
    test_end: str
    train_bars: int
    test_bars: int
    purged_bars: int
    embargo_bars: int


def make_purged_embargo_folds(
    dataset: pd.DataFrame,
    *,
    n_splits: int = 5,
    label_horizon_bars: int = 6,
    embargo_bars: int = 6,
    min_train_bars: int = 1000,
) -> list[tuple[pd.Index, pd.Index, PurgedFold]]:
    data = dataset.sort_index()
    n = len(data)
    if n < n_splits + min_train_bars:
        return []
    fold_size = max(1, n // n_splits)
    folds: list[tuple[pd.Index, pd.Index, PurgedFold]] = []
    for fold_id in range(n_splits):
        test_start_i = fold_id * fold_size
        test_end_i = n if fold_id == n_splits - 1 else min(n, (fold_id + 1) * fold_size)
        if test_end_i <= test_start_i:
            continue
        purge_start = max(0, test_start_i - label_horizon_bars)
        embargo_end = min(n, test_end_i + embargo_bars)
        train_idx = list(range(0, purge_start)) + list(range(embargo_end, n))
        test_idx = list(range(test_start_i, test_end_i))
        if len(train_idx) < min_train_bars:
            continue
        train_index = data.index[train_idx]
        test_index = data.index[test_idx]
        meta = PurgedFold(
            fold_id=fold_id,
            train_start=str(train_index.min()) if len(train_index) else None,
            train_end=str(train_index.max()) if len(train_index) else None,
            test_start=str(test_index.min()),
            test_end=str(test_index.max()),
            train_bars=len(train_index),
            test_bars=len(test_index),
            purged_bars=label_horizon_bars,
            embargo_bars=embargo_bars,
        )
        folds.append((train_index, test_index, meta))
    return folds


def evaluate_purged_embargo_cv(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    *,
    model_type: str = "extra_trees",
    label_col: str = "label_up",
    n_splits: int = 5,
    label_horizon_bars: int = 6,
    embargo_bars: int = 6,
    min_train_bars: int = 1000,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = dataset.copy().sort_index()
    feature_columns = list(feature_columns)
    rows = []
    pred_frames = []
    folds = make_purged_embargo_folds(data, n_splits=n_splits, label_horizon_bars=label_horizon_bars, embargo_bars=embargo_bars, min_train_bars=min_train_bars)
    for train_index, test_index, meta in folds:
        train = data.loc[train_index]
        test = data.loc[test_index]
        model = make_model_by_name(model_type)
        model.fit(train[feature_columns], train[label_col])
        metrics = evaluate_classifier(model, test[feature_columns], test[label_col])
        rows.append({**asdict(meta), "model_type": model_type, **metrics})
        prob = model.predict_proba(test[feature_columns])[:, 1]
        pred_frames.append(pd.DataFrame({"fold_id": meta.fold_id, "y_true": test[label_col], "prob_up": prob}, index=test.index))
    metrics_df = pd.DataFrame(rows)
    preds = pd.concat(pred_frames).sort_index() if pred_frames else pd.DataFrame()
    return metrics_df, preds


def save_validation_artifacts(metrics: pd.DataFrame, preds: pd.DataFrame, output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    metrics_path = out / "purged_embargo_cv_metrics.csv"
    preds_path = out / "purged_embargo_cv_predictions.csv"
    report_path = out / "purged_embargo_cv_report.json"
    html_path = out / "purged_embargo_cv_report.html"
    metrics.to_csv(metrics_path, index=False, encoding="utf-8-sig")
    preds.to_csv(preds_path, encoding="utf-8-sig")
    summary = {
        "folds": int(len(metrics)),
        "mean_roc_auc": float(metrics["roc_auc"].mean()) if "roc_auc" in metrics and not metrics.empty else None,
        "mean_accuracy": float(metrics["accuracy"].mean()) if "accuracy" in metrics and not metrics.empty else None,
        "mean_brier_score": float(metrics["brier_score"].mean()) if "brier_score" in metrics and not metrics.empty else None,
        "warning": "Purged/embargo CV is stricter than ordinary time split and may expose overfitting.",
    }
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_validation_html(summary, metrics, html_path)
    return {"metrics": str(metrics_path), "predictions": str(preds_path), "report": str(report_path), "html": str(html_path)}


def _write_validation_html(summary: dict, metrics: pd.DataFrame, path: Path) -> None:
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in summary.items())
    metrics_html = metrics.to_html(index=False, escape=True) if not metrics.empty else "<p>No folds generated.</p>"
    css = "<style>body{font-family:Arial,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #e5e7eb;padding:8px;text-align:left}th{background:#f9fafb}.card{border:1px solid #e5e7eb;border-radius:16px;padding:18px;margin-bottom:18px}</style>"
    path.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>Purged CV Report</title>{css}</head><body><h1>Purged/Embargo CV Report</h1><div class='card'><table>{rows}</table></div><div class='card'>{metrics_html}</div></body></html>", encoding="utf-8")
