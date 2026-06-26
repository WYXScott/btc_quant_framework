from __future__ import annotations

import json
import _bootstrap  # noqa: F401

import pandas as pd

from crypto_quant.config import resolve_path
from crypto_quant.reporting.html_report import build_research_html_report


def _read_csv(path):
    path = resolve_path(path)
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _read_json(path):
    path = resolve_path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    model_dir = resolve_path("reports/model_diagnostics")
    strat_dir = resolve_path("reports/strategy_diagnostics")
    lev_dir = resolve_path("reports/leverage_risk")
    out_dir = resolve_path("reports/research_report")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy plot images into the report folder so the HTML remains portable.
    images = []
    for src in [
        model_dir / "feature_importance_top20.png",
        model_dir / "calibration_curve.png",
        strat_dir / "strategy_equity.png",
        strat_dir / "strategy_drawdown.png",
    ]:
        if src.exists():
            dst = out_dir / src.name
            dst.write_bytes(src.read_bytes())
            images.append(dst)

    summary = {}
    summary.update({f"model_{k}": v for k, v in _read_json("reports/model_diagnostics/model_metrics.json").items()})
    summary.update({f"strategy_{k}": v for k, v in _read_json("reports/strategy_diagnostics/strategy_summary.json").items()})

    tables = {
        "model_threshold_diagnostics": _read_csv("reports/model_diagnostics/threshold_diagnostics.csv"),
        "feature_importance_top20": _read_csv("reports/model_diagnostics/feature_importance.csv").head(20),
        "calibration_table": _read_csv("reports/model_diagnostics/calibration_table.csv"),
        "annual_performance": _read_csv("reports/strategy_diagnostics/annual_performance.csv"),
        "regime_performance": _read_csv("reports/strategy_diagnostics/regime_performance.csv"),
        "drawdown_events": _read_csv("reports/strategy_diagnostics/drawdown_events.csv"),
        "leverage_risk_table": _read_csv("reports/leverage_risk/leverage_risk_table.csv"),
    }
    notes = [
        "Prefer parameters that remain acceptable across leverage and threshold scans rather than the single best historical row.",
        "For a 1000 USDT account, keep demo validation at 3x before considering 5x or 10x.",
        "Any live version must pass long demo operation, private API reconciliation, and kill-switch testing first.",
    ]
    path = build_research_html_report(
        output_path=out_dir / "research_report.html",
        title="BTC Quant Research Report V1.2",
        summary=summary,
        tables=tables,
        images=images,
        notes=notes,
    )
    print(f"saved report: {path}")


if __name__ == "__main__":
    main()
