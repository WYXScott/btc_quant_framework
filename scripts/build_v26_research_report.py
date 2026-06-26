from __future__ import annotations

import json
from pathlib import Path
import _bootstrap  # noqa: F401

import pandas as pd

from crypto_quant.config import load_config, resolve_path


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _csv_html(path: Path, rows: int = 30) -> str:
    if not path.exists():
        return f"<p>Missing: {path}</p>"
    try:
        df = pd.read_csv(path)
        if len(df) > rows:
            df = df.head(rows)
        return df.to_html(index=False, border=0, classes="table")
    except Exception as exc:
        return f"<p>Failed to read {path}: {exc}</p>"


def main() -> None:
    cfg = load_config()
    root = resolve_path(cfg.get("walk_forward_calibration", {}).get("output_path", "reports/walk_forward_calibration"))
    out_dir = resolve_path("reports/v2_6_research_report")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = _read_json(root / "walk_forward_calibration_summary.json")

    metrics = []
    for name in ["raw", "calibrated"]:
        row = {"probability_version": name}
        row.update(summary.get(name, {}))
        metrics.append(row)
    metrics_html = pd.DataFrame(metrics).to_html(index=False, border=0, classes="table") if metrics else "<p>No metrics.</p>"
    bt = summary.get("backtest", {})
    bt_html = pd.DataFrame([bt]).to_html(index=False, border=0, classes="table") if bt else "<p>No backtest summary.</p>"

    html = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>BTC V2.6 Research Report</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;margin:32px;background:#f7f8fb;color:#111827;}}
.card{{background:white;border-radius:18px;padding:22px;margin-bottom:18px;box-shadow:0 10px 28px rgba(15,23,42,.08);}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
.table{{border-collapse:collapse;width:100%;font-size:13px;}} .table th,.table td{{border-bottom:1px solid #e5e7eb;padding:7px;text-align:left;}}
.table th{{background:#111827;color:white;}} img{{max-width:100%;border-radius:12px;border:1px solid #e5e7eb;}}
.badge{{display:inline-block;border-radius:999px;padding:4px 10px;background:#dcfce7;color:#166534;font-weight:700;}}
</style></head><body>
<div class='card'><h1>BTC V2.6 Walk-forward 概率校准研究报告</h1><p><span class='badge'>Research / Paper only</span></p><p>该报告聚合滚动训练、滚动校准、滚动测试输出；用于判断校准概率是否在样本外稳定。</p></div>
<div class='card'><h2>Raw vs Calibrated Overall Metrics</h2>{metrics_html}</div>
<div class='card'><h2>Dynamic Exposure Backtest Summary</h2>{bt_html}</div>
<div class='grid'><div class='card'><h2>Reliability</h2><img src='../walk_forward_calibration/walk_forward_reliability.png'></div><div class='card'><h2>Equity</h2><img src='../walk_forward_calibration/walk_forward_calibrated_equity.png'></div></div>
<div class='card'><h2>Confidence Tiers</h2>{_csv_html(root / 'walk_forward_confidence_tiers.csv')}</div>
<div class='card'><h2>Fold Metrics</h2>{_csv_html(root / 'walk_forward_calibrated_folds.csv')}</div>
</body></html>"""
    target = out_dir / "v2_6_research_report.html"
    target.write_text(html, encoding="utf-8")
    print(f"saved report: {target}")


if __name__ == "__main__":
    main()
