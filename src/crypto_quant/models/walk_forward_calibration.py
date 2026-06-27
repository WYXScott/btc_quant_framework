from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import json
import numpy as np
import pandas as pd

from crypto_quant.backtest.dynamic_engine import DynamicExposureBacktester
from crypto_quant.backtest.metrics import save_backtest_reports
from crypto_quant.models.calibration import (
    fit_probability_calibrator,
    positive_proba,
    probability_metrics,
    reliability_table,
)
from crypto_quant.models.registry import make_model_by_name
from crypto_quant.reporting.plots import plot_drawdown, plot_equity_curve
from crypto_quant.research.signal_confidence import ConfidencePolicy, apply_confidence_policy, confidence_tier_report


@dataclass(frozen=True)
class WalkForwardCalibrationConfig:
    """Rolling train -> calibration -> test configuration.

    Each fold uses three strictly ordered windows:
        train window       : fit base classifier
        calibration window : fit post-hoc probability calibrator on base probabilities
        test window        : generate out-of-sample raw and calibrated probabilities

    The calibration window is immediately before the test window. This avoids
    using future observations to fit the calibrator and is closer to how the
    system would be operated live.
    """

    train_window_days: int = 1095
    calibration_window_days: int = 180
    test_window_days: int = 90
    min_train_bars: int = 1000
    min_calibration_bars: int = 180
    min_test_bars: int = 30
    start: str | None = None
    end: str | None = None
    model_type: str = "extra_trees"
    calibration_method: str = "isotonic"
    bins: int = 10
    label_horizon_bars: int = 0

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "WalkForwardCalibrationConfig":
        c = cfg.get("walk_forward_calibration", {})
        wf = cfg.get("walk_forward", {})
        cal = cfg.get("calibration", {})
        labels = cfg.get("labels", {})
        return cls(
            train_window_days=int(c.get("train_window_days", wf.get("train_window_days", 1095))),
            calibration_window_days=int(c.get("calibration_window_days", 180)),
            test_window_days=int(c.get("test_window_days", wf.get("test_window_days", 90))),
            min_train_bars=int(c.get("min_train_bars", wf.get("min_train_bars", 1000))),
            min_calibration_bars=int(c.get("min_calibration_bars", 180)),
            min_test_bars=int(c.get("min_test_bars", 30)),
            start=c.get("start", wf.get("start")),
            end=c.get("end", wf.get("end")),
            model_type=str(c.get("model_type", cfg.get("model", {}).get("type", "extra_trees"))),
            calibration_method=str(c.get("method", cal.get("method", "isotonic"))),
            bins=int(c.get("bins", cal.get("bins", 10))),
            label_horizon_bars=int(c.get("label_horizon_bars", labels.get("horizon_bars", 0))),
        )


def _as_utc_timestamp(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


def _clip_probability(prob: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.clip(np.asarray(prob, dtype=float), eps, 1.0 - eps)


def _drop_tail_for_purge(df: pd.DataFrame, purge_bars: int) -> pd.DataFrame:
    purge = max(int(purge_bars), 0)
    if purge == 0:
        return df
    if len(df) <= purge:
        return df.iloc[0:0].copy()
    return df.iloc[:-purge].copy()


def _apply_calibrator(raw_prob: np.ndarray, calibrator: object | None, method: str) -> np.ndarray:
    raw = _clip_probability(raw_prob)
    if calibrator is None or method == "none":
        return raw
    if method == "isotonic":
        return _clip_probability(calibrator.predict(raw))
    if method in {"sigmoid", "platt"}:
        return _clip_probability(calibrator.predict_proba(raw.reshape(-1, 1))[:, 1])
    raise ValueError(f"Unsupported calibration method: {method}")


def _safe_fit_calibrator(raw_prob: np.ndarray, y: pd.Series, method: str) -> tuple[object | None, str, str]:
    """Fit calibrator; gracefully degrade to no calibration when a fold is unusable."""
    method = str(method).strip().lower()
    if method == "none":
        return None, "none", "method_none"
    try:
        if len(np.unique(np.asarray(y, dtype=int))) < 2:
            return None, "none", "single_class_calibration_window"
        calibrator = fit_probability_calibrator(raw_prob, y, method=method)
        return calibrator, method, "ok"
    except Exception as exc:  # keep walk-forward robust across bad folds
        return None, "none", f"calibration_failed:{type(exc).__name__}:{exc}"


def walk_forward_calibrated_predict(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    cfg: WalkForwardCalibrationConfig,
    label_col: str = "label_up",
    future_return_col: str = "future_return",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate leak-resistant walk-forward raw and calibrated probabilities.

    Returns:
        predictions: dataset subset with fold_id, raw/calibrated probability and labels
        folds: one row per fold with calibration/test metrics
        skipped: one row per skipped fold with reason
    """
    feature_columns = list(feature_columns)
    data = dataset.copy().sort_index()
    if data.index.tz is None:
        data.index = data.index.tz_localize("UTC")
    else:
        data.index = data.index.tz_convert("UTC")

    start = _as_utc_timestamp(cfg.start)
    end = _as_utc_timestamp(cfg.end)
    if start is None:
        start = data.index.min() + pd.Timedelta(days=cfg.train_window_days + cfg.calibration_window_days)
    if end is None:
        end = data.index.max()

    pred_frames: list[pd.DataFrame] = []
    fold_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    test_start = start
    fold_id = 0

    while test_start < end:
        calibration_start = test_start - pd.Timedelta(days=cfg.calibration_window_days)
        train_start = calibration_start - pd.Timedelta(days=cfg.train_window_days)
        test_end = min(test_start + pd.Timedelta(days=cfg.test_window_days), end)

        train = data.loc[(data.index >= train_start) & (data.index < calibration_start)].copy()
        cal = data.loc[(data.index >= calibration_start) & (data.index < test_start)].copy()
        test = data.loc[(data.index >= test_start) & (data.index < test_end)].copy()
        train = _drop_tail_for_purge(train, cfg.label_horizon_bars)
        cal = _drop_tail_for_purge(cal, cfg.label_horizon_bars)

        skip_reason = None
        if len(train) < cfg.min_train_bars:
            skip_reason = f"train_bars<{cfg.min_train_bars}"
        elif len(cal) < cfg.min_calibration_bars:
            skip_reason = f"calibration_bars<{cfg.min_calibration_bars}"
        elif len(test) < cfg.min_test_bars:
            skip_reason = f"test_bars<{cfg.min_test_bars}"
        elif train[label_col].nunique(dropna=True) < 2:
            skip_reason = "single_class_train_window"
        elif test[label_col].nunique(dropna=True) < 1:
            skip_reason = "empty_test_labels"

        if skip_reason is not None:
            skipped_rows.append({
                "fold_id": fold_id,
                "reason": skip_reason,
                "train_start": train_start,
                "calibration_start": calibration_start,
                "test_start": test_start,
                "test_end": test_end,
                "train_bars": len(train),
                "calibration_bars": len(cal),
                "test_bars": len(test),
                "label_horizon_bars": int(cfg.label_horizon_bars),
            })
            fold_id += 1
            test_start = test_end
            continue

        model = make_model_by_name(cfg.model_type)
        model.fit(train[feature_columns], train[label_col])

        raw_cal = _clip_probability(positive_proba(model, cal[feature_columns]))
        calibrator, effective_method, calibration_status = _safe_fit_calibrator(raw_cal, cal[label_col], cfg.calibration_method)
        cal_calibrated = _apply_calibrator(raw_cal, calibrator, effective_method)

        raw_test = _clip_probability(positive_proba(model, test[feature_columns]))
        calibrated_test = _apply_calibrator(raw_test, calibrator, effective_method)

        test_out = test.copy()
        test_out["fold_id"] = fold_id
        test_out["prob_up_raw_wf"] = raw_test
        test_out["prob_up_calibrated_wf"] = calibrated_test
        test_out["calibration_method_effective"] = effective_method
        pred_frames.append(test_out)

        raw_cal_metrics = probability_metrics(cal[label_col], raw_cal, bins=cfg.bins)
        cal_cal_metrics = probability_metrics(cal[label_col], cal_calibrated, bins=cfg.bins)
        raw_test_metrics = probability_metrics(test[label_col], raw_test, bins=cfg.bins)
        cal_test_metrics = probability_metrics(test[label_col], calibrated_test, bins=cfg.bins)

        fold_rows.append({
            "fold_id": fold_id,
            "model_type": cfg.model_type,
            "requested_calibration_method": cfg.calibration_method,
            "effective_calibration_method": effective_method,
            "calibration_status": calibration_status,
            "train_start": train.index.min(),
            "train_end": train.index.max(),
            "calibration_start": cal.index.min(),
            "calibration_end": cal.index.max(),
            "test_start": test.index.min(),
            "test_end": test.index.max(),
            "train_bars": len(train),
            "calibration_bars": len(cal),
            "test_bars": len(test),
            "label_horizon_bars": int(cfg.label_horizon_bars),
            "calibration_positive_rate": float(cal[label_col].mean()),
            "test_positive_rate": float(test[label_col].mean()),
            "calibration_raw_brier": raw_cal_metrics["brier_score"],
            "calibration_calibrated_brier": cal_cal_metrics["brier_score"],
            "calibration_raw_ece": raw_cal_metrics["ece"],
            "calibration_calibrated_ece": cal_cal_metrics["ece"],
            "test_raw_brier": raw_test_metrics["brier_score"],
            "test_calibrated_brier": cal_test_metrics["brier_score"],
            "test_raw_ece": raw_test_metrics["ece"],
            "test_calibrated_ece": cal_test_metrics["ece"],
            "test_raw_auc": raw_test_metrics["roc_auc"],
            "test_calibrated_auc": cal_test_metrics["roc_auc"],
            "test_raw_log_loss": raw_test_metrics["log_loss"],
            "test_calibrated_log_loss": cal_test_metrics["log_loss"],
            "test_brier_delta_cal_minus_raw": float(cal_test_metrics["brier_score"] - raw_test_metrics["brier_score"]),
            "test_ece_delta_cal_minus_raw": float(cal_test_metrics["ece"] - raw_test_metrics["ece"]),
        })
        fold_id += 1
        test_start = test_end

    predictions = pd.concat(pred_frames).sort_index() if pred_frames else pd.DataFrame()
    folds = pd.DataFrame(fold_rows)
    skipped = pd.DataFrame(skipped_rows)
    return predictions, folds, skipped


def summarize_wf_calibration(predictions: pd.DataFrame, folds: pd.DataFrame, bins: int = 10) -> dict[str, Any]:
    if predictions.empty:
        return {"status": "empty", "folds": 0, "bars": 0}
    y = predictions["label_up"]
    raw = predictions["prob_up_raw_wf"].values
    cal = predictions["prob_up_calibrated_wf"].values
    raw_metrics = probability_metrics(y, raw, bins=bins)
    cal_metrics = probability_metrics(y, cal, bins=bins)
    return {
        "status": "ok",
        "folds": int(folds["fold_id"].nunique()) if not folds.empty and "fold_id" in folds else 0,
        "bars": int(len(predictions)),
        "start": str(predictions.index.min()),
        "end": str(predictions.index.max()),
        "raw": raw_metrics,
        "calibrated": cal_metrics,
        "brier_delta_calibrated_minus_raw": float(cal_metrics["brier_score"] - raw_metrics["brier_score"]),
        "ece_delta_calibrated_minus_raw": float(cal_metrics["ece"] - raw_metrics["ece"]),
        "log_loss_delta_calibrated_minus_raw": float(cal_metrics["log_loss"] - raw_metrics["log_loss"]),
    }


def build_wf_calibrated_confidence_dataset(
    predictions: pd.DataFrame,
    policy: ConfidencePolicy,
) -> pd.DataFrame:
    if predictions.empty:
        return predictions.copy()
    df = predictions.copy()
    # Reuse V2.5 confidence policy by exposing the walk-forward calibrated column
    # through the standard prob_up_calibrated name.
    df["prob_up_calibrated"] = df["prob_up_calibrated_wf"]
    df["prob_up_raw"] = df["prob_up_raw_wf"]
    return apply_confidence_policy(df, prob_col="prob_up_calibrated", policy=policy)


def save_walk_forward_calibration_report(
    predictions: pd.DataFrame,
    folds: pd.DataFrame,
    skipped: pd.DataFrame,
    output_dir: str | Path,
    cfg: dict[str, Any],
    wf_cfg: WalkForwardCalibrationConfig,
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    predictions.to_csv(out_dir / "walk_forward_calibrated_predictions.csv", encoding="utf-8-sig")
    folds.to_csv(out_dir / "walk_forward_calibrated_folds.csv", index=False, encoding="utf-8-sig")
    skipped.to_csv(out_dir / "walk_forward_calibrated_skipped_folds.csv", index=False, encoding="utf-8-sig")

    summary = summarize_wf_calibration(predictions, folds, bins=wf_cfg.bins)
    (out_dir / "walk_forward_calibration_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    if predictions.empty:
        return summary

    raw_rel = reliability_table(
        predictions["label_up"],
        predictions["prob_up_raw_wf"].values,
        future_return=predictions["future_return"] if "future_return" in predictions else None,
        bins=wf_cfg.bins,
    )
    cal_rel = reliability_table(
        predictions["label_up"],
        predictions["prob_up_calibrated_wf"].values,
        future_return=predictions["future_return"] if "future_return" in predictions else None,
        bins=wf_cfg.bins,
    )
    raw_rel.to_csv(out_dir / "walk_forward_reliability_raw.csv", index=False, encoding="utf-8-sig")
    cal_rel.to_csv(out_dir / "walk_forward_reliability_calibrated.csv", index=False, encoding="utf-8-sig")

    policy = ConfidencePolicy.from_config(cfg)
    confidence_df = build_wf_calibrated_confidence_dataset(predictions, policy)
    confidence_df.to_csv(out_dir / "walk_forward_confidence_dataset.csv", encoding="utf-8-sig")
    tier_table = confidence_tier_report(confidence_df)
    tier_table.to_csv(out_dir / "walk_forward_confidence_tiers.csv", index=False, encoding="utf-8-sig")

    bt = DynamicExposureBacktester(
        initial_equity=cfg["trading"]["initial_equity"],
        max_notional_fraction=policy.max_exposure,
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
    )
    result = bt.run(confidence_df, exposure_col="target_exposure_confidence")
    backtest_summary = save_backtest_reports(result, out_dir, prefix="walk_forward_calibrated", timeframe=cfg["data"]["timeframe"])
    plot_equity_curve(result, out_dir / "walk_forward_calibrated_equity.png", title="Walk-forward Calibrated Confidence Equity")
    plot_drawdown(result, out_dir / "walk_forward_calibrated_drawdown.png", title="Walk-forward Calibrated Confidence Drawdown")
    summary["backtest"] = backtest_summary
    (out_dir / "walk_forward_calibration_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # Reliability plot without imposing custom colors/styles.
    try:
        import matplotlib.pyplot as plt

        fig = plt.figure(figsize=(7, 6))
        ax = fig.add_subplot(111)
        ax.plot([0, 1], [0, 1], linestyle="--", label="perfect")
        if not raw_rel.empty:
            ax.plot(raw_rel["prob_mean"], raw_rel["actual_positive_rate"], marker="o", label="raw wf")
        if not cal_rel.empty:
            ax.plot(cal_rel["prob_mean"], cal_rel["actual_positive_rate"], marker="o", label="calibrated wf")
        ax.set_title("Walk-forward Raw vs Calibrated Reliability")
        ax.set_xlabel("Mean predicted probability")
        ax.set_ylabel("Actual positive rate")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / "walk_forward_reliability.png", dpi=200)
        plt.close(fig)
    except Exception:
        pass

    metrics_rows = []
    for section in ["raw", "calibrated"]:
        row = {"probability_version": section}
        row.update(summary[section])
        metrics_rows.append(row)
    pd.DataFrame(metrics_rows).to_csv(out_dir / "walk_forward_raw_vs_calibrated_metrics.csv", index=False, encoding="utf-8-sig")

    html_metrics = pd.DataFrame(metrics_rows).to_html(index=False, border=0, classes="table")
    html_folds = folds.tail(20).to_html(index=False, border=0, classes="table") if not folds.empty else "<p>No folds.</p>"
    html_tiers = tier_table.to_html(index=False, border=0, classes="table") if not tier_table.empty else "<p>No tiers.</p>"
    html_skipped = skipped.to_html(index=False, border=0, classes="table") if not skipped.empty else "<p>No skipped folds.</p>"
    html = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>BTC V2.6 Walk-forward Calibration</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;margin:32px;background:#f7f8fb;color:#111827;}}
.card{{background:white;border-radius:18px;padding:22px;margin-bottom:18px;box-shadow:0 10px 28px rgba(15,23,42,.08);}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
.table{{border-collapse:collapse;width:100%;font-size:13px;}} .table th,.table td{{border-bottom:1px solid #e5e7eb;padding:7px;text-align:left;}}
.table th{{background:#111827;color:white;}} img{{max-width:100%;border-radius:12px;border:1px solid #e5e7eb;}}
.badge{{display:inline-block;border-radius:999px;padding:4px 10px;background:#e0f2fe;color:#075985;font-weight:700;}}
</style></head><body>
<div class='card'><h1>BTC V2.6 Walk-forward 概率校准报告</h1><p><span class='badge'>无实盘交易</span></p><p>每个 fold 按 train → calibration → test 严格时间顺序运行，校准器只使用测试窗口之前的数据。</p></div>
<div class='card'><h2>整体 Raw vs Calibrated 指标</h2>{html_metrics}</div>
<div class='grid'><div class='card'><h2>可靠性曲线</h2><img src='walk_forward_reliability.png'></div><div class='card'><h2>策略权益曲线</h2><img src='walk_forward_calibrated_equity.png'></div></div>
<div class='card'><h2>信号可信度分层</h2>{html_tiers}</div>
<div class='card'><h2>最近 folds</h2>{html_folds}</div>
<div class='card'><h2>Skipped folds</h2>{html_skipped}</div>
</body></html>"""
    (out_dir / "walk_forward_calibration_report.html").write_text(html, encoding="utf-8")
    return summary


def run_walk_forward_calibration_pipeline(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    cfg: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    wf_cfg = WalkForwardCalibrationConfig.from_config(cfg)
    predictions, folds, skipped = walk_forward_calibrated_predict(dataset, feature_columns, wf_cfg)
    return save_walk_forward_calibration_report(predictions, folds, skipped, output_dir, cfg, wf_cfg)
