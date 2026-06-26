from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_quant.config import project_root, resolve_path
from crypto_quant.ui.dashboard_helpers import collect_core_status, load_yaml, summarize_dataset, summarize_model, sqlite_table_counts


@dataclass
class AuditItem:
    area: str
    status: str
    severity: str
    message: str
    recommendation: str


def _exists(path: str | Path) -> bool:
    p = Path(path)
    if not p.is_absolute():
        p = project_root() / p
    return p.exists()


def build_package_audit() -> dict[str, Any]:
    cfg = load_yaml()
    items: list[AuditItem] = []

    data = summarize_dataset(cfg)
    model = summarize_model(cfg)
    db_path = resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    table_counts = sqlite_table_counts(db_path)

    if data.get("exists"):
        items.append(AuditItem("data", "pass", "info", f"Dataset exists with {data.get('rows')} rows.", "Continue to use walk-forward validation; avoid random train/test split."))
    else:
        items.append(AuditItem("data", "missing", "high", "Dataset is missing.", "Run download_ohlcv.py and build_features.py first."))

    if model.get("model_exists"):
        items.append(AuditItem("model", "pass", "info", f"Model exists with {model.get('feature_count')} features.", "Run run_model_diagnostics.py before trusting the signal."))
    else:
        items.append(AuditItem("model", "missing", "high", "Model file is missing.", "Run train_model.py after building the dataset."))

    calib_model = resolve_path(cfg.get("calibration", {}).get("calibrated_model_path", "models/btc_direction_model_calibrated.joblib"))
    if calib_model.exists():
        items.append(AuditItem("calibration", "pass", "info", "Calibrated probability model exists.", "Review reports/calibration before using probability tiers for sizing."))
    else:
        items.append(AuditItem("calibration", "missing", "medium", "Calibrated probability model is missing.", "Run train_calibrated_model.py after train_model.py."))

    wf_cal_report = resolve_path("reports/walk_forward_calibration/walk_forward_calibration_summary.json")
    if wf_cal_report.exists():
        items.append(AuditItem("walk_forward_calibration", "pass", "info", "Walk-forward calibration summary exists.", "Prefer this report over fixed-split calibration before sizing live-like paper positions."))
    else:
        items.append(AuditItem("walk_forward_calibration", "missing", "medium", "Walk-forward calibration summary is missing.", "Run run_walk_forward_calibration.py after building the dataset."))

    if db_path.exists():
        items.append(AuditItem("paper", "pass", "info", f"Paper database exists with {len(table_counts)} tables.", "Use paper_ensemble_replay_dataset.py to stress test account state transitions."))
    else:
        items.append(AuditItem("paper", "missing", "medium", "Paper database is missing.", "Run paper_init.py --reset before paper trading."))

    live_cfg = cfg.get("live_trading", {})
    if live_cfg.get("master_enable", False):
        items.append(AuditItem("live_safety", "blocked", "critical", "live_trading.master_enable is true.", "Keep it false while you are not ready for live trading."))
    else:
        items.append(AuditItem("live_safety", "pass", "info", "Live trading master switch is disabled.", "This matches the current no-live requirement."))

    broker_safety = cfg.get("broker", {}).get("safety", {})
    if broker_safety.get("allow_live_trading", False):
        items.append(AuditItem("broker_safety", "blocked", "critical", "broker.safety.allow_live_trading is true.", "Set it false unless you deliberately enter live mode after review."))
    else:
        items.append(AuditItem("broker_safety", "pass", "info", "Broker live execution is disabled.", "Safe for research/demo use."))


    dq_report = resolve_path("reports/data_quality/data_quality_report.json")
    if dq_report.exists():
        try:
            dq = json.loads(dq_report.read_text(encoding="utf-8"))
            if dq.get("critical_count", 0) > 0:
                items.append(AuditItem("data_quality", "blocked", "critical", f"Data quality report has {dq.get('critical_count')} critical issues.", "Fix or explicitly exclude bad candles before training."))
            else:
                items.append(AuditItem("data_quality", "pass", "info", "Data quality report has no critical issue.", "Re-run after each data update."))
        except Exception:
            items.append(AuditItem("data_quality", "warning", "medium", "Data quality report exists but could not be parsed.", "Regenerate run_data_quality_check.py."))
    else:
        items.append(AuditItem("data_quality", "missing", "medium", "Data quality report is missing.", "Run run_data_quality_check.py before training."))

    if "streamlit" in (project_root() / "requirements.txt").read_text(encoding="utf-8"):
        items.append(AuditItem("ui", "pass", "info", "Streamlit dashboard dependency is listed.", "Run python scripts/run_dashboard.py to open the UI."))
    else:
        items.append(AuditItem("ui", "missing", "medium", "Streamlit is not listed in requirements.", "Install streamlit or run scripts without the dashboard."))

    key_outputs = {
        "data_quality_report": "reports/data_quality/data_quality_report.json",
        "purged_embargo_cv": "reports/validation/purged_embargo_cv_metrics.csv",
        "market_realism_report": "reports/market_realism/market_realism_report.json",
        "calibration_metrics": "reports/calibration/calibration_metrics.json",
        "confidence_tier_table": "reports/signal_confidence/confidence_tier_table.csv",
        "walk_forward_calibration_summary": "reports/walk_forward_calibration/walk_forward_calibration_summary.json",
        "walk_forward_confidence_tiers": "reports/walk_forward_calibration/walk_forward_confidence_tiers.csv",
        "model_backend_availability": "reports/model_backends/model_backend_availability.csv",
        "enhanced_model_library_summary": "reports/enhanced_model_library/model_library_summary.csv",
        "wf_calibration_model_library_summary": "reports/walk_forward_calibration_model_library/walk_forward_calibration_model_library_summary.csv",
        "sequence_model_summary": "reports/sequence_models/sequence_model_summary.csv",
        "sequence_walk_forward_summary": "reports/sequence_walk_forward/sequence_walk_forward_summary.csv",
        "model_strategy_leaderboard": "reports/model_admission/model_strategy_leaderboard.csv",
        "model_strategy_admission_report": "reports/model_admission/model_strategy_admission_report.html",
        "strategy_library_summary": "reports/strategy_library/strategy_library_summary.csv",
        "parameter_search_summary": "reports/robustness/parameter_search/strategy_parameter_search_summary.csv",
        "ensemble_summary": "reports/ensemble/ensemble_summary.csv",
        "prelive_console": "reports/prelive_operator/prelive_operator_console.html",
    }
    for name, path in key_outputs.items():
        if _exists(path):
            items.append(AuditItem("report", "pass", "info", f"{name} exists.", "Review this report before proceeding."))
        else:
            items.append(AuditItem("report", "missing", "low", f"{name} has not been generated yet.", "Run the corresponding research or safety script."))

    payload: dict[str, Any] = {
        "project": cfg.get("project", {}),
        "audit_items": [asdict(x) for x in items],
        "core_files": collect_core_status(cfg).to_dict(orient="records"),
        "dataset_summary": data,
        "model_summary": model,
        "paper_table_counts": table_counts.to_dict(orient="records"),
        "overall_status": "blocked" if any(i.severity == "critical" for i in items) else "ready_for_research",
    }
    return payload


def write_package_audit(output_dir: str | Path = "reports/software_review") -> dict[str, Path]:
    out = resolve_path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = build_package_audit()
    json_path = out / "software_review.json"
    csv_path = out / "software_review_items.csv"
    html_path = out / "software_review.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(payload["audit_items"]).to_csv(csv_path, index=False)

    rows = "".join(
        f"<tr><td>{i['area']}</td><td>{i['status']}</td><td>{i['severity']}</td><td>{i['message']}</td><td>{i['recommendation']}</td></tr>"
        for i in payload["audit_items"]
    )
    html = f"""<!doctype html>
<html lang='zh-CN'>
<head><meta charset='utf-8'><title>BTC Quant Software Review</title>
<style>
body {{font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; margin: 32px; background:#f7f8fb; color:#1f2937;}}
.card {{background:white; border-radius:18px; padding:24px; box-shadow:0 10px 30px rgba(15,23,42,.08); margin-bottom:20px;}}
table {{border-collapse:collapse; width:100%; background:white;}}
th, td {{border-bottom:1px solid #e5e7eb; padding:10px; text-align:left; vertical-align:top;}}
th {{background:#111827; color:white;}}
.badge {{display:inline-block; padding:4px 10px; border-radius:999px; background:#e5f4ff;}}
</style></head>
<body>
<div class='card'><h1>BTC Quant Framework V2.9 软件审查报告</h1>
<p>整体状态：<span class='badge'>{payload['overall_status']}</span></p>
<p>本报告只评估研究、回测、模拟盘和只读安全监控，不代表允许实盘自动交易。</p></div>
<div class='card'><h2>审查项</h2><table><thead><tr><th>区域</th><th>状态</th><th>级别</th><th>说明</th><th>建议</th></tr></thead><tbody>{rows}</tbody></table></div>
</body></html>"""
    html_path.write_text(html, encoding="utf-8")
    return {"json": json_path, "csv": csv_path, "html": html_path}
