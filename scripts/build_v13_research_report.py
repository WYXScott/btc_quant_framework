from __future__ import annotations

import _bootstrap  # noqa: F401
import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.reporting.html_report import build_research_html_report


def _read_csv(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def main() -> None:
    cfg = load_config()
    rob_cfg = cfg.get("robustness", {})
    search_dir = resolve_path(rob_cfg.get("parameter_search_path", "reports/robustness/parameter_search"))
    top_dir = resolve_path(rob_cfg.get("top_candidate_path", "reports/robustness/top_candidate"))
    ml_dir = resolve_path(rob_cfg.get("ml_threshold_grid_path", "reports/robustness/ml_threshold_grid"))
    output_path = resolve_path(rob_cfg.get("report_path", "reports/v1_3_research_report/v1_3_research_report.html"))

    search = _read_csv(search_dir / "strategy_parameter_search_summary.csv")
    summary = {
        "version": cfg.get("project", {}).get("version", "1.3.0"),
        "symbol": cfg.get("symbol", {}).get("ccxt_symbol", "BTC/USDT"),
        "timeframe": cfg.get("data", {}).get("timeframe", "4h"),
        "strategy_candidates": len(search),
        "default_leverage": cfg.get("trading", {}).get("leverage", ""),
        "initial_equity": cfg.get("trading", {}).get("initial_equity", ""),
    }
    if not search.empty and "strategy" in search:
        best = search.iloc[0]
        summary.update({
            "best_strategy": best.get("strategy", ""),
            "best_robust_rank_score": best.get("robust_rank_score", ""),
            "best_overfit_risk_score": best.get("overfit_risk_score", ""),
            "best_max_drawdown": best.get("max_drawdown", ""),
        })

    tables = {
        "top_strategy_parameter_candidates": search.head(20),
        "top_candidate_segment_performance": _read_csv(top_dir / "segments.csv"),
        "top_candidate_regime_performance": _read_csv(top_dir / "regimes.csv"),
        "top_candidate_cost_slippage_stress": _read_csv(top_dir / "cost_slippage_stress.csv"),
        "top_candidate_leverage_boundary": _read_csv(top_dir / "leverage_boundary.csv"),
        "ml_threshold_grid": _read_csv(ml_dir / "ml_threshold_grid_summary.csv").head(20),
    }
    notes = [
        "V1.3 ranks candidates with a heuristic robustness score; it is a research filter, not a trading guarantee.",
        "Prefer candidates with acceptable drawdown, enough trades, positive segment coverage, and low sensitivity to cost/slippage stress.",
        "For 1000 USDT and 3-10x leverage, any candidate with poor 10x stress behavior should remain paper/demo only.",
    ]
    path = build_research_html_report(
        output_path=output_path,
        title="BTC Quant Framework V1.3 Robustness Report",
        summary=summary,
        tables=tables,
        images=[],
        notes=notes,
    )
    print(f"saved report: {path}")


if __name__ == "__main__":
    main()
