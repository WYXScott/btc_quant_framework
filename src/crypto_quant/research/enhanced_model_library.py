from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from crypto_quant.models.registry import (
    MODEL_REGISTRY,
    available_models,
    canonical_model_name,
    default_enabled_models,
    model_availability_rows,
)
from crypto_quant.research.model_library import evaluate_model_library


def resolve_requested_models(model_names: Iterable[str] | None, include_optional_if_installed: bool = True) -> tuple[list[str], pd.DataFrame]:
    if model_names is None:
        requested = default_enabled_models(include_optional_if_installed=include_optional_if_installed)
    else:
        requested = [canonical_model_name(m) for m in model_names]

    availability = pd.DataFrame(model_availability_rows())
    rows = []
    runnable: list[str] = []
    for name in requested:
        if name not in MODEL_REGISTRY:
            rows.append({
                "model": name,
                "requested": True,
                "available": False,
                "status": "unknown_model",
                "reason": f"Unknown model. Known models: {available_models(include_unavailable=True)}",
                "install_hint": "",
            })
            continue
        spec = MODEL_REGISTRY[name]
        if spec.is_available:
            runnable.append(name)
            rows.append({
                "model": name,
                "requested": True,
                "available": True,
                "status": "runnable",
                "reason": "",
                "install_hint": spec.install_hint,
            })
        else:
            rows.append({
                "model": name,
                "requested": True,
                "available": False,
                "status": "skipped_missing_optional_dependency",
                "reason": f"Missing optional package: {spec.optional_package}",
                "install_hint": spec.install_hint,
            })
    request_status = pd.DataFrame(rows)
    return runnable, availability.merge(request_status, on="model", how="left", suffixes=("", "_requested"))


def run_enhanced_model_library(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    model_names: Iterable[str] | None,
    train_end: str,
    valid_end: str,
    output_dir: str | Path,
    thresholds: Iterable[float] = (0.5, 0.55, 0.58, 0.6, 0.65),
    calibration_bins: int = 10,
    include_optional_if_installed: bool = True,
    purge_bars: int = 0,
) -> dict[str, object]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    runnable, availability = resolve_requested_models(model_names, include_optional_if_installed=include_optional_if_installed)
    availability.to_csv(out_dir / "model_availability.csv", index=False, encoding="utf-8-sig")

    if runnable:
        summary = evaluate_model_library(
            dataset=dataset,
            feature_columns=feature_columns,
            model_names=runnable,
            train_end=train_end,
            valid_end=valid_end,
            output_dir=out_dir,
            thresholds=thresholds,
            calibration_bins=calibration_bins,
            purge_bars=purge_bars,
        )
    else:
        summary = pd.DataFrame()
        summary.to_csv(out_dir / "model_library_summary.csv", index=False, encoding="utf-8-sig")

    skipped = availability[(availability.get("requested") == True) & (availability.get("status") != "runnable")].copy()  # noqa: E712
    skipped.to_csv(out_dir / "skipped_models.csv", index=False, encoding="utf-8-sig")

    payload = {
        "status": "ok" if runnable else "no_runnable_models",
        "requested_models": int(availability[availability.get("requested") == True].shape[0]) if "requested" in availability else 0,  # noqa: E712
        "runnable_models": runnable,
        "skipped_models": skipped["model"].tolist() if not skipped.empty and "model" in skipped else [],
        "available_models": available_models(include_unavailable=False),
        "all_models": available_models(include_unavailable=True),
    }
    (out_dir / "enhanced_model_library_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    html_summary = summary.to_html(index=False, border=0, classes="table") if not summary.empty else "<p>No runnable models.</p>"
    html_avail = availability.to_html(index=False, border=0, classes="table") if not availability.empty else "<p>No availability rows.</p>"
    html_skipped = skipped.to_html(index=False, border=0, classes="table") if not skipped.empty else "<p>No skipped requested models.</p>"
    html = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>BTC V2.7 Enhanced Model Library</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;margin:32px;background:#f7f8fb;color:#111827;}}
.card{{background:white;border-radius:18px;padding:22px;margin-bottom:18px;box-shadow:0 10px 28px rgba(15,23,42,.08);}}
.table{{border-collapse:collapse;width:100%;font-size:13px;}} .table th,.table td{{border-bottom:1px solid #e5e7eb;padding:7px;text-align:left;}}
.table th{{background:#111827;color:white;}}
.badge{{display:inline-block;border-radius:999px;padding:4px 10px;background:#eef2ff;color:#3730a3;font-weight:700;}}
</style></head><body>
<div class='card'><h1>BTC V2.7 模型库增强报告</h1><p><span class='badge'>研究模式 · 无实盘交易</span></p><p>LightGBM 与 XGBoost 为可选依赖；未安装时自动跳过，核心模型仍可运行。</p></div>
<div class='card'><h2>模型可用性</h2>{html_avail}</div>
<div class='card'><h2>固定切分模型指标</h2>{html_summary}</div>
<div class='card'><h2>跳过模型</h2>{html_skipped}</div>
</body></html>"""
    (out_dir / "enhanced_model_library_report.html").write_text(html, encoding="utf-8")
    return payload
