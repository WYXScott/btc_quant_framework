from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import resolve_path
from crypto_quant.ui.dashboard_helpers import read_csv, read_json


def _table(path: str) -> str:
    df = read_csv(path)
    return df.to_html(index=False, border=0, classes="table") if not df.empty else f"<p>未生成：{path}</p>"


def _json_summary(path: str) -> str:
    obj = read_json(path)
    if obj is None:
        return f"<p>未生成：{path}</p>"
    return f"<pre>{obj}</pre>"


def main() -> None:
    out_dir = resolve_path("reports/v2_7_research_report")
    out_dir.mkdir(parents=True, exist_ok=True)
    html = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>BTC V2.7 模型库增强研究报告</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;margin:32px;background:#f7f8fb;color:#111827;}}
.card{{background:white;border-radius:18px;padding:22px;margin-bottom:18px;box-shadow:0 10px 28px rgba(15,23,42,.08);}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
.table{{border-collapse:collapse;width:100%;font-size:13px;}} .table th,.table td{{border-bottom:1px solid #e5e7eb;padding:7px;text-align:left;}}
.table th{{background:#111827;color:white;}}
.badge{{display:inline-block;border-radius:999px;padding:4px 10px;background:#fef3c7;color:#92400e;font-weight:700;}}
pre{{white-space:pre-wrap;background:#111827;color:#f9fafb;border-radius:12px;padding:14px;overflow:auto;}}
</style></head><body>
<div class='card'><h1>BTC V2.7 模型库增强研究报告</h1><p><span class='badge'>不开放实盘自动交易</span></p><p>本报告汇总可选模型后端、固定切分模型库、walk-forward 概率校准模型库对比结果。</p></div>
<div class='grid'>
<div class='card'><h2>模型后端可用性</h2>{_table('reports/model_backends/model_backend_availability.csv')}</div>
<div class='card'><h2>可选依赖状态</h2>{_table('reports/model_backends/optional_dependency_status.csv')}</div>
</div>
<div class='card'><h2>增强模型库固定切分结果</h2>{_table('reports/enhanced_model_library/model_library_summary.csv')}</div>
<div class='card'><h2>Walk-forward 校准模型库结果</h2>{_table('reports/walk_forward_calibration_model_library/walk_forward_calibration_model_library_summary.csv')}</div>
<div class='card'><h2>增强模型库 JSON 摘要</h2>{_json_summary('reports/enhanced_model_library/enhanced_model_library_summary.json')}</div>
</body></html>"""
    path = out_dir / "v2_7_research_report.html"
    path.write_text(html, encoding="utf-8")
    print(f"saved report: {path}")


if __name__ == "__main__":
    main()
