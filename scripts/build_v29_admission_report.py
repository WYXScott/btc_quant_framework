from __future__ import annotations

from pathlib import Path

from _bootstrap import ROOT

from crypto_quant.config import load_config, resolve_path
from crypto_quant.research.model_admission import run_model_strategy_admission


def main() -> None:
    cfg = load_config()
    summary = run_model_strategy_admission(cfg)
    src_dir = resolve_path(cfg.get("model_admission", {}).get("output_path", "reports/model_admission"))
    dst_dir = resolve_path(cfg.get("v2_9_report", {}).get("output_path", "reports/v2_9_admission_report"))
    dst_dir.mkdir(parents=True, exist_ok=True)
    src = src_dir / "model_strategy_admission_report.html"
    dst = dst_dir / "v2_9_admission_report.html"
    if src.exists():
        html = src.read_text(encoding="utf-8")
        html = html.replace("BTC V2.9 Unified Model & Strategy Admission Report", "BTC V2.9 统一模型排行榜与策略准入报告")
        dst.write_text(html, encoding="utf-8")
    else:
        dst.write_text("<html><body><h1>No admission report generated.</h1></body></html>", encoding="utf-8")
    print(f"V2.9 report written: {dst}")
    print(summary)


if __name__ == "__main__":
    main()
