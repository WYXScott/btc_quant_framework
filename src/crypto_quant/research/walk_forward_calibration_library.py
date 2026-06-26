from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from crypto_quant.models.registry import MODEL_REGISTRY, canonical_model_name, default_enabled_models, model_availability_rows
from crypto_quant.models.walk_forward_calibration import run_walk_forward_calibration_pipeline


def _flatten_summary(model: str, status: str, output_dir: Path, summary: dict[str, object] | None = None, reason: str = "") -> dict[str, object]:
    summary = summary or {}
    raw = summary.get("raw", {}) if isinstance(summary.get("raw"), dict) else {}
    cal = summary.get("calibrated", {}) if isinstance(summary.get("calibrated"), dict) else {}
    bt = summary.get("backtest", {}) if isinstance(summary.get("backtest"), dict) else {}
    return {
        "model": model,
        "status": status,
        "reason": reason,
        "output_dir": str(output_dir),
        "folds": summary.get("folds", 0),
        "bars": summary.get("bars", 0),
        "raw_brier": raw.get("brier_score"),
        "calibrated_brier": cal.get("brier_score"),
        "raw_ece": raw.get("ece"),
        "calibrated_ece": cal.get("ece"),
        "raw_auc": raw.get("roc_auc"),
        "calibrated_auc": cal.get("roc_auc"),
        "brier_delta_calibrated_minus_raw": summary.get("brier_delta_calibrated_minus_raw"),
        "ece_delta_calibrated_minus_raw": summary.get("ece_delta_calibrated_minus_raw"),
        "backtest_total_return": bt.get("total_return"),
        "backtest_cagr": bt.get("cagr"),
        "backtest_sharpe": bt.get("sharpe"),
        "backtest_max_drawdown": bt.get("max_drawdown"),
        "backtest_calmar": bt.get("calmar"),
        "backtest_trades": bt.get("trades"),
        "backtest_final_equity": bt.get("final_equity"),
    }


def run_walk_forward_calibration_model_library(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    cfg: dict[str, object],
    output_dir: str | Path,
    model_names: Iterable[str] | None = None,
    include_optional_if_installed: bool = True,
) -> pd.DataFrame:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if model_names is None:
        model_names = default_enabled_models(include_optional_if_installed=include_optional_if_installed)
    requested = [canonical_model_name(m) for m in model_names]

    pd.DataFrame(model_availability_rows()).to_csv(out_dir / "model_availability.csv", index=False, encoding="utf-8-sig")
    rows: list[dict[str, object]] = []
    for model_name in requested:
        model_dir = out_dir / model_name
        model_dir.mkdir(parents=True, exist_ok=True)
        if model_name not in MODEL_REGISTRY:
            rows.append(_flatten_summary(model_name, "skipped", model_dir, reason="unknown_model"))
            continue
        spec = MODEL_REGISTRY[model_name]
        if not spec.is_available:
            rows.append(_flatten_summary(
                model_name,
                "skipped",
                model_dir,
                reason=f"missing_optional_dependency:{spec.optional_package}; {spec.install_hint}",
            ))
            continue
        run_cfg = copy.deepcopy(cfg)
        run_cfg.setdefault("walk_forward_calibration", {})
        run_cfg["walk_forward_calibration"]["model_type"] = model_name
        run_cfg["walk_forward_calibration"]["output_path"] = str(model_dir)
        try:
            summary = run_walk_forward_calibration_pipeline(dataset, feature_columns, run_cfg, model_dir)
            rows.append(_flatten_summary(model_name, "ok", model_dir, summary=summary))
        except Exception as exc:
            rows.append(_flatten_summary(model_name, "failed", model_dir, reason=f"{type(exc).__name__}: {exc}"))

    table = pd.DataFrame(rows)
    if not table.empty:
        sort_cols = [c for c in ["status", "backtest_calmar", "calibrated_brier", "calibrated_ece"] if c in table]
        if sort_cols:
            table = table.sort_values(sort_cols, ascending=[True, False, True, True][:len(sort_cols)])
    table.to_csv(out_dir / "walk_forward_calibration_model_library_summary.csv", index=False, encoding="utf-8-sig")
    (out_dir / "walk_forward_calibration_model_library_summary.json").write_text(
        json.dumps({"rows": rows}, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    html_table = table.to_html(index=False, border=0, classes="table") if not table.empty else "<p>No results.</p>"
    html = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>BTC V2.7 Walk-forward Calibration Model Library</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;margin:32px;background:#f7f8fb;color:#111827;}}
.card{{background:white;border-radius:18px;padding:22px;margin-bottom:18px;box-shadow:0 10px 28px rgba(15,23,42,.08);}}
.table{{border-collapse:collapse;width:100%;font-size:13px;}} .table th,.table td{{border-bottom:1px solid #e5e7eb;padding:7px;text-align:left;}}
.table th{{background:#111827;color:white;}}
.badge{{display:inline-block;border-radius:999px;padding:4px 10px;background:#dcfce7;color:#166534;font-weight:700;}}
</style></head><body>
<div class='card'><h1>BTC V2.7 Walk-forward 校准模型库对比</h1><p><span class='badge'>train → calibration → test</span></p><p>每个模型独立滚动训练、校准和测试；可选模型未安装时自动跳过。</p></div>
<div class='card'><h2>模型对比汇总</h2>{html_table}</div>
</body></html>"""
    (out_dir / "walk_forward_calibration_model_library_report.html").write_text(html, encoding="utf-8")
    return table
