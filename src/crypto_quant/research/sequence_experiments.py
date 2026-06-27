from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score

from crypto_quant.models.calibration import probability_metrics, reliability_table
from crypto_quant.models.sequence_dataset import build_sequence_dataset, split_sequence_dataset, SequenceDataset
from crypto_quant.models.sequence_models import (
    SEQUENCE_MODEL_REGISTRY,
    default_sequence_models,
    make_sequence_model_by_name,
    sequence_model_availability_rows,
)


@dataclass(frozen=True)
class SequenceExperimentConfig:
    lookback_bars: int = 48
    stride_bars: int = 1
    train_end: str = "2022-12-31"
    valid_end: str = "2023-12-31"
    label_col: str = "label_up"
    future_return_col: str = "future_return"
    close_col: str = "close"
    model_names: tuple[str, ...] = ("sequence_mlp",)
    include_torch_if_installed: bool = False
    torch_epochs: int = 12
    torch_batch_size: int = 128
    torch_hidden_size: int = 64
    torch_device: str = "auto"
    bins: int = 10

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "SequenceExperimentConfig":
        c = cfg.get("sequence_models", {})
        model_names = c.get("models")
        if not model_names:
            model_names = default_sequence_models(bool(c.get("include_torch_if_installed", False)))
        return cls(
            lookback_bars=int(c.get("lookback_bars", 48)),
            stride_bars=int(c.get("stride_bars", 1)),
            train_end=str(c.get("train_end", cfg.get("model", {}).get("train_end", "2022-12-31"))),
            valid_end=str(c.get("valid_end", cfg.get("model", {}).get("valid_end", "2023-12-31"))),
            label_col=str(c.get("label_col", "label_up")),
            future_return_col=str(c.get("future_return_col", "future_return")),
            close_col=str(c.get("close_col", "close")),
            model_names=tuple(str(x) for x in model_names),
            include_torch_if_installed=bool(c.get("include_torch_if_installed", False)),
            torch_epochs=int(c.get("torch_epochs", 12)),
            torch_batch_size=int(c.get("torch_batch_size", 128)),
            torch_hidden_size=int(c.get("torch_hidden_size", 64)),
            torch_device=str(c.get("torch_device", "auto")),
            bins=int(c.get("bins", cfg.get("calibration", {}).get("bins", 10))),
        )


@dataclass(frozen=True)
class SequenceWalkForwardConfig:
    lookback_bars: int = 48
    stride_bars: int = 1
    train_window_days: int = 1095
    test_window_days: int = 90
    min_train_sequences: int = 600
    min_test_sequences: int = 30
    start: str | None = None
    end: str | None = None
    model_names: tuple[str, ...] = ("sequence_mlp",)
    include_torch_if_installed: bool = False
    torch_epochs: int = 8
    torch_batch_size: int = 128
    torch_hidden_size: int = 64
    torch_device: str = "auto"
    bins: int = 10

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "SequenceWalkForwardConfig":
        c = cfg.get("sequence_walk_forward", {})
        base = cfg.get("sequence_models", {})
        model_names = c.get("models", base.get("models"))
        include_torch = bool(c.get("include_torch_if_installed", base.get("include_torch_if_installed", False)))
        if not model_names:
            model_names = default_sequence_models(include_torch)
        return cls(
            lookback_bars=int(c.get("lookback_bars", base.get("lookback_bars", 48))),
            stride_bars=int(c.get("stride_bars", base.get("stride_bars", 1))),
            train_window_days=int(c.get("train_window_days", 1095)),
            test_window_days=int(c.get("test_window_days", 90)),
            min_train_sequences=int(c.get("min_train_sequences", 600)),
            min_test_sequences=int(c.get("min_test_sequences", 30)),
            start=c.get("start"),
            end=c.get("end"),
            model_names=tuple(str(x) for x in model_names),
            include_torch_if_installed=include_torch,
            torch_epochs=int(c.get("torch_epochs", base.get("torch_epochs", 8))),
            torch_batch_size=int(c.get("torch_batch_size", base.get("torch_batch_size", 128))),
            torch_hidden_size=int(c.get("torch_hidden_size", base.get("torch_hidden_size", 64))),
            torch_device=str(c.get("torch_device", base.get("torch_device", "auto"))),
            bins=int(c.get("bins", base.get("bins", cfg.get("calibration", {}).get("bins", 10)))),
        )


def _clip(p: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), 1e-6, 1.0 - 1e-6)


def _safe_auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    try:
        return float(roc_auc_score(y, p))
    except Exception:
        return 0.0


def _classification_metrics(y: np.ndarray, p: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    pred = (_clip(p) >= float(threshold)).astype(int)
    return {
        "samples": float(len(y)),
        "positive_rate": float(np.mean(y)) if len(y) else 0.0,
        "accuracy": float(accuracy_score(y, pred)) if len(y) else 0.0,
        "precision": float(precision_score(y, pred, zero_division=0)) if len(y) else 0.0,
        "recall": float(recall_score(y, pred, zero_division=0)) if len(y) else 0.0,
        "roc_auc": _safe_auc(y, p),
    } | probability_metrics(pd.Series(y), p)


def _make_model_kwargs(cfg: SequenceExperimentConfig | SequenceWalkForwardConfig) -> dict[str, object]:
    return {
        "epochs": int(cfg.torch_epochs),
        "batch_size": int(cfg.torch_batch_size),
        "hidden_size": int(cfg.torch_hidden_size),
        "device": cfg.torch_device,
    }


def _fit_predict_sequence_model(model_name: str, X_train: np.ndarray, y_train: np.ndarray, X_eval: np.ndarray, cfg) -> tuple[np.ndarray | None, str]:
    if model_name not in SEQUENCE_MODEL_REGISTRY:
        return None, "unknown_model"
    spec = SEQUENCE_MODEL_REGISTRY[model_name]
    if not spec.is_available:
        return None, f"missing_optional_dependency:{spec.optional_package}"
    if len(X_train) == 0 or len(X_eval) == 0:
        return None, "empty_train_or_eval"
    if len(np.unique(y_train.astype(int))) < 2:
        return None, "single_class_train"
    try:
        kwargs = _make_model_kwargs(cfg) if spec.optional_package == "torch" else {}
        model = make_sequence_model_by_name(model_name, **kwargs)
        model.fit(X_train, y_train)
        prob = _clip(model.predict_proba(X_eval)[:, 1])
        return prob, "ok"
    except Exception as exc:
        return None, f"failed:{type(exc).__name__}:{exc}"


def _save_bar_plot(table: pd.DataFrame, x_col: str, y_col: str, path: Path, title: str) -> None:
    if table.empty or y_col not in table or x_col not in table:
        return
    try:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(9, 4.8))
        table.plot(kind="bar", x=x_col, y=y_col, ax=ax, legend=False)
        ax.set_title(title)
        ax.set_ylabel(y_col)
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
    except Exception:
        return


def _write_html(title: str, output_path: Path, sections: list[tuple[str, str]]) -> None:
    cards = []
    for heading, body in sections:
        cards.append(f"<div class='card'><h2>{heading}</h2>{body}</div>")
    html = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>{title}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:#f7f8fb;color:#111827;margin:32px;}}
.card{{background:white;border-radius:18px;padding:22px;margin-bottom:18px;box-shadow:0 10px 28px rgba(15,23,42,.08);}}
.table{{border-collapse:collapse;width:100%;font-size:13px;}} .table th,.table td{{border-bottom:1px solid #e5e7eb;padding:7px;text-align:left;}}
.table th{{background:#111827;color:white;}}
.badge{{display:inline-block;border-radius:999px;padding:4px 10px;background:#eef2ff;color:#3730a3;font-weight:700;}}
</style></head><body><div class='card'><h1>{title}</h1><p><span class='badge'>V2.8 序列模型实验 · 不接实盘</span></p></div>{''.join(cards)}</body></html>"""
    output_path.write_text(html, encoding="utf-8")


def run_sequence_model_experiments(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    output_dir: str | Path,
    cfg: SequenceExperimentConfig,
) -> dict[str, object]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    availability = pd.DataFrame(sequence_model_availability_rows())
    availability.to_csv(out_dir / "sequence_model_availability.csv", index=False, encoding="utf-8-sig")

    seq = build_sequence_dataset(
        dataset,
        feature_columns,
        lookback_bars=cfg.lookback_bars,
        stride_bars=cfg.stride_bars,
        label_col=cfg.label_col,
        future_return_col=cfg.future_return_col,
        close_col=cfg.close_col,
    )
    train, valid, test = split_sequence_dataset(seq, train_end=cfg.train_end, valid_end=cfg.valid_end)
    meta = {
        "total_sequences": int(len(seq.y)),
        "lookback_bars": int(cfg.lookback_bars),
        "feature_count": int(len(seq.feature_columns)),
        "train_sequences": int(len(train["y"])),
        "valid_sequences": int(len(valid["y"])),
        "test_sequences": int(len(test["y"])),
        "models_requested": list(cfg.model_names),
    }

    rows = []
    pred_frames = []
    skipped = []
    for model_name in cfg.model_names:
        model_name = str(model_name)
        if model_name not in SEQUENCE_MODEL_REGISTRY:
            skipped.append({"model": model_name, "status": "unknown_model", "reason": "not in registry"})
            continue
        spec = SEQUENCE_MODEL_REGISTRY[model_name]
        if not spec.is_available:
            skipped.append({"model": model_name, "status": "skipped", "reason": f"missing {spec.optional_package}", "install_hint": spec.install_hint})
            continue
        # Fit on train, evaluate both validation and test.
        valid_prob, valid_status = _fit_predict_sequence_model(model_name, train["X"], train["y"], valid["X"], cfg)
        train_valid_X = np.concatenate([train["X"], valid["X"]], axis=0) if len(valid["X"]) else train["X"]
        train_valid_y = np.concatenate([train["y"], valid["y"]], axis=0) if len(valid["y"]) else train["y"]
        test_prob, test_status = _fit_predict_sequence_model(model_name, train_valid_X, train_valid_y, test["X"], cfg)
        row = {"model": model_name, "status": "ok" if test_prob is not None else test_status, "valid_status": valid_status, "test_status": test_status}
        if valid_prob is not None:
            for k, v in _classification_metrics(valid["y"], valid_prob).items():
                row[f"valid_{k}"] = v
        if test_prob is not None:
            for k, v in _classification_metrics(test["y"], test_prob).items():
                row[f"test_{k}"] = v
            pred = pd.DataFrame({
                "timestamp": test["index"],
                "model": model_name,
                "prob": test_prob,
                "label_up": test["y"].astype(int),
            })
            if "future_return" in test:
                pred["future_return"] = test["future_return"]
            pred_frames.append(pred)
        rows.append(row)

    summary = pd.DataFrame(rows).sort_values("test_roc_auc", ascending=False, na_position="last") if rows else pd.DataFrame()
    summary.to_csv(out_dir / "sequence_model_summary.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(skipped).to_csv(out_dir / "sequence_model_skipped.csv", index=False, encoding="utf-8-sig")
    predictions = pd.concat(pred_frames, ignore_index=True) if pred_frames else pd.DataFrame()
    predictions.to_csv(out_dir / "sequence_model_predictions.csv", index=False, encoding="utf-8-sig")

    if not predictions.empty:
        rel_frames = []
        for model, chunk in predictions.groupby("model"):
            rel = reliability_table(chunk["label_up"], chunk["prob"], chunk.get("future_return"), bins=cfg.bins)
            rel.insert(0, "model", model)
            rel_frames.append(rel)
        pd.concat(rel_frames, ignore_index=True).to_csv(out_dir / "sequence_model_reliability.csv", index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(out_dir / "sequence_model_reliability.csv", index=False, encoding="utf-8-sig")

    _save_bar_plot(summary, "model", "test_roc_auc", out_dir / "sequence_model_auc.png", "Sequence model test ROC-AUC")
    payload = meta | {
        "status": "ok" if not summary.empty else "no_runnable_sequence_models",
        "runnable_models": summary["model"].tolist() if not summary.empty and "model" in summary else [],
        "skipped_models": [r.get("model") for r in skipped],
    }
    (out_dir / "sequence_model_experiment_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_html(
        "BTC V2.8 序列模型固定切分实验",
        out_dir / "sequence_model_experiment_report.html",
        [
            ("实验元信息", f"<pre>{json.dumps(payload, ensure_ascii=False, indent=2)}</pre>"),
            ("模型可用性", availability.to_html(index=False, border=0, classes="table")),
            ("模型指标", summary.to_html(index=False, border=0, classes="table") if not summary.empty else "<p>No runnable models.</p>"),
        ],
    )
    return payload


def _as_utc(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def run_sequence_walk_forward(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    output_dir: str | Path,
    cfg: SequenceWalkForwardConfig,
    label_col: str = "label_up",
    future_return_col: str = "future_return",
    close_col: str = "close",
) -> dict[str, object]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seq = build_sequence_dataset(
        dataset,
        feature_columns,
        lookback_bars=cfg.lookback_bars,
        stride_bars=cfg.stride_bars,
        label_col=label_col,
        future_return_col=future_return_col,
        close_col=close_col,
    )
    if len(seq.y) == 0:
        payload = {"status": "no_sequences", "folds": 0}
        (out_dir / "sequence_walk_forward_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    start = _as_utc(cfg.start)
    end = _as_utc(cfg.end)
    if start is None:
        start = seq.index.min() + pd.Timedelta(days=cfg.train_window_days)
    if end is None:
        end = seq.index.max()

    folds = []
    skipped = []
    pred_frames = []
    fold_id = 0
    test_start = start
    while test_start < end:
        train_start = test_start - pd.Timedelta(days=cfg.train_window_days)
        test_end = min(test_start + pd.Timedelta(days=cfg.test_window_days), end)
        train_mask = (seq.index >= train_start) & (seq.index < test_start)
        test_mask = (seq.index >= test_start) & (seq.index < test_end)
        X_train, y_train = seq.X[train_mask], seq.y[train_mask]
        X_test, y_test = seq.X[test_mask], seq.y[test_mask]
        index_test = seq.index[test_mask]

        skip_reason = None
        if len(y_train) < cfg.min_train_sequences:
            skip_reason = f"train_sequences<{cfg.min_train_sequences}"
        elif len(y_test) < cfg.min_test_sequences:
            skip_reason = f"test_sequences<{cfg.min_test_sequences}"
        elif len(np.unique(y_train.astype(int))) < 2:
            skip_reason = "single_class_train"

        if skip_reason:
            skipped.append({
                "fold_id": fold_id,
                "reason": skip_reason,
                "train_start": train_start,
                "test_start": test_start,
                "test_end": test_end,
                "train_sequences": len(y_train),
                "test_sequences": len(y_test),
            })
            fold_id += 1
            test_start = test_end
            continue

        for model_name in cfg.model_names:
            if model_name not in SEQUENCE_MODEL_REGISTRY:
                skipped.append({"fold_id": fold_id, "model": model_name, "reason": "unknown_model"})
                continue
            spec = SEQUENCE_MODEL_REGISTRY[model_name]
            if not spec.is_available:
                skipped.append({"fold_id": fold_id, "model": model_name, "reason": f"missing {spec.optional_package}", "install_hint": spec.install_hint})
                continue
            prob, status = _fit_predict_sequence_model(model_name, X_train, y_train, X_test, cfg)
            row = {
                "fold_id": fold_id,
                "model": model_name,
                "status": status,
                "train_start": train_start,
                "test_start": test_start,
                "test_end": test_end,
                "train_sequences": len(y_train),
                "test_sequences": len(y_test),
            }
            if prob is not None:
                row.update(_classification_metrics(y_test, prob))
                pred = pd.DataFrame({
                    "timestamp": index_test,
                    "fold_id": fold_id,
                    "model": model_name,
                    "prob": prob,
                    "label_up": y_test.astype(int),
                })
                if seq.future_return is not None:
                    pred["future_return"] = seq.future_return[test_mask]
                if seq.close is not None:
                    pred["close"] = seq.close[test_mask]
                pred_frames.append(pred)
            folds.append(row)
        fold_id += 1
        test_start = test_end

    folds_df = pd.DataFrame(folds)
    skipped_df = pd.DataFrame(skipped)
    preds = pd.concat(pred_frames, ignore_index=True) if pred_frames else pd.DataFrame()
    folds_df.to_csv(out_dir / "sequence_walk_forward_folds.csv", index=False, encoding="utf-8-sig")
    skipped_df.to_csv(out_dir / "sequence_walk_forward_skipped.csv", index=False, encoding="utf-8-sig")
    preds.to_csv(out_dir / "sequence_walk_forward_predictions.csv", index=False, encoding="utf-8-sig")

    if not folds_df.empty:
        summary = folds_df[folds_df["status"] == "ok"].groupby("model", as_index=False).agg(
            folds=("fold_id", "nunique"),
            samples=("test_sequences", "sum"),
            roc_auc_mean=("roc_auc", "mean"),
            brier_score_mean=("brier_score", "mean"),
            ece_mean=("ece", "mean"),
            accuracy_mean=("accuracy", "mean"),
            precision_mean=("precision", "mean"),
            recall_mean=("recall", "mean"),
        ).sort_values("roc_auc_mean", ascending=False, na_position="last")
    else:
        summary = pd.DataFrame()
    summary.to_csv(out_dir / "sequence_walk_forward_summary.csv", index=False, encoding="utf-8-sig")
    _save_bar_plot(summary, "model", "roc_auc_mean", out_dir / "sequence_walk_forward_auc.png", "Sequence walk-forward mean ROC-AUC")

    if not preds.empty:
        rel_frames = []
        for model, chunk in preds.groupby("model"):
            rel = reliability_table(chunk["label_up"], chunk["prob"], chunk.get("future_return"), bins=cfg.bins)
            rel.insert(0, "model", model)
            rel_frames.append(rel)
        pd.concat(rel_frames, ignore_index=True).to_csv(out_dir / "sequence_walk_forward_reliability.csv", index=False, encoding="utf-8-sig")
    else:
        pd.DataFrame().to_csv(out_dir / "sequence_walk_forward_reliability.csv", index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok" if not summary.empty else "no_successful_folds",
        "lookback_bars": int(cfg.lookback_bars),
        "feature_count": int(len(seq.feature_columns)),
        "total_sequences": int(len(seq.y)),
        "fold_rows": int(len(folds_df)),
        "skipped_rows": int(len(skipped_df)),
        "models": summary["model"].tolist() if not summary.empty else [],
    }
    (out_dir / "sequence_walk_forward_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_html(
        "BTC V2.8 序列模型 Walk-forward 实验",
        out_dir / "sequence_walk_forward_report.html",
        [
            ("实验元信息", f"<pre>{json.dumps(payload, ensure_ascii=False, indent=2)}</pre>"),
            ("模型汇总", summary.to_html(index=False, border=0, classes="table") if not summary.empty else "<p>No successful folds.</p>"),
            ("Fold明细", folds_df.to_html(index=False, border=0, classes="table") if not folds_df.empty else "<p>No folds.</p>"),
        ],
    )
    return payload


def build_v28_sequence_report(sequence_dir: str | Path, wf_dir: str | Path, output_dir: str | Path) -> Path:
    sequence_dir = Path(sequence_dir)
    wf_dir = Path(wf_dir)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fixed = pd.read_csv(sequence_dir / "sequence_model_summary.csv") if (sequence_dir / "sequence_model_summary.csv").exists() else pd.DataFrame()
    wf = pd.read_csv(wf_dir / "sequence_walk_forward_summary.csv") if (wf_dir / "sequence_walk_forward_summary.csv").exists() else pd.DataFrame()
    availability = pd.read_csv(sequence_dir / "sequence_model_availability.csv") if (sequence_dir / "sequence_model_availability.csv").exists() else pd.DataFrame()
    _write_html(
        "BTC V2.8 序列模型实验总报告",
        out_dir / "v2_8_sequence_research_report.html",
        [
            ("模型可用性", availability.to_html(index=False, border=0, classes="table") if not availability.empty else "<p>Not generated.</p>"),
            ("固定切分实验", fixed.to_html(index=False, border=0, classes="table") if not fixed.empty else "<p>Not generated.</p>"),
            ("Walk-forward实验", wf.to_html(index=False, border=0, classes="table") if not wf.empty else "<p>Not generated.</p>"),
            ("解释", "<p>V2.8 的序列模型只作为研究实验层。只有当序列模型在 walk-forward、成本压力和校准评估中稳定优于表格模型时，才应考虑进入模拟盘候选池。</p>"),
        ],
    )
    return out_dir / "v2_8_sequence_research_report.html"
