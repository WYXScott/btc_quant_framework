from __future__ import annotations

import _bootstrap  # noqa: F401

from pathlib import Path

import pandas as pd

from crypto_quant.config import resolve_path
from crypto_quant.reporting.html_report import build_research_html_report


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def main() -> None:
    strategy_summary = _read_csv(resolve_path("reports/strategy_library/strategy_library_summary.csv"))
    model_summary = _read_csv(resolve_path("reports/model_library/model_library_summary.csv"))
    matrix_summary = _read_csv(resolve_path("reports/model_strategy_matrix/model_strategy_matrix_summary.csv"))
    output_path = resolve_path("reports/v1_2_research_report/v1_2_research_report.html")
    summary = {
        "strategy_candidates": int(len(strategy_summary)) if not strategy_summary.empty else 0,
        "model_diagnostics_rows": int(len(model_summary)) if not model_summary.empty else 0,
        "model_strategy_candidates": int(len(matrix_summary)) if not matrix_summary.empty else 0,
    }
    tables = {
        "strategy_library_summary": strategy_summary,
        "model_library_summary": model_summary,
        "model_strategy_matrix_summary": matrix_summary,
    }
    notes = [
        "V1.2 compares strategy families and model families under one common BTC low-frequency research pipeline.",
        "Best backtest row is not automatically tradable; require walk-forward stability, paper trading and Demo/Testnet validation.",
        "For 3x-10x leverage, prioritize drawdown, liquidation buffer and trade frequency over raw return.",
    ]
    build_research_html_report(output_path, title="BTC Quant Framework V1.2 Strategy/Model Library Report", summary=summary, tables=tables, images=[], notes=notes)
    print(f"saved report: {output_path}")


if __name__ == "__main__":
    main()
