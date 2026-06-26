from __future__ import annotations

import ast
from pathlib import Path

import _bootstrap  # noqa: F401
import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.research.robustness import evaluate_top_candidate_robustness, strategy_parameter_search


def _parse_params(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    rob_cfg = cfg.get("robustness", {})
    search_path = resolve_path(rob_cfg.get("parameter_search_path", "reports/robustness/parameter_search"))
    summary_path = search_path / "strategy_parameter_search_summary.csv"

    if summary_path.exists():
        search_table = pd.read_csv(summary_path)
        if "params" in search_table:
            search_table["params"] = search_table["params"].apply(_parse_params)
    else:
        search_table = strategy_parameter_search(
            dataset=dataset,
            strategy_names=rob_cfg.get("strategies") or cfg.get("strategy_library", {}).get("strategies", []),
            output_dir=search_path,
            timeframe=cfg["data"]["timeframe"],
            initial_equity=cfg["trading"]["initial_equity"],
            leverage=cfg["trading"]["leverage"],
            max_margin_fraction=cfg["trading"]["max_margin_fraction"],
            max_notional_fraction=cfg["trading"]["max_notional_fraction"],
            fee_rate=cfg["trading"]["fee_rate"],
            slippage_rate=cfg["trading"]["slippage_rate"],
            max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
            n_segments=int(rob_cfg.get("n_segments", 6)),
            max_candidates_per_strategy=rob_cfg.get("max_candidates_per_strategy"),
        )
    valid = search_table[~search_table.get("error", pd.Series(index=search_table.index, dtype=object)).notna()].copy()
    if valid.empty:
        raise RuntimeError("No valid strategy candidates found. Run parameter search and inspect errors.")
    top = valid.sort_values(["robust_rank_score", "calmar", "sharpe"], ascending=[False, False, False]).iloc[0]
    out_dir = resolve_path(rob_cfg.get("top_candidate_path", "reports/robustness/top_candidate"))
    tables = evaluate_top_candidate_robustness(
        dataset=dataset,
        candidate=top,
        output_dir=out_dir,
        timeframe=cfg["data"]["timeframe"],
        initial_equity=cfg["trading"]["initial_equity"],
        leverage=cfg["trading"]["leverage"],
        leverages=rob_cfg.get("leverages", cfg.get("scan", {}).get("leverages", [3.0, 5.0, 10.0])),
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        fee_multipliers=rob_cfg.get("fee_multipliers", [1.0, 2.0, 4.0]),
        slippage_multipliers=rob_cfg.get("slippage_multipliers", [1.0, 2.0, 4.0]),
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
        n_segments=int(rob_cfg.get("n_segments", 6)),
    )
    print("top candidate:")
    print(top[["strategy", "candidate_id", "params", "robust_rank_score", "overfit_risk_score", "total_return", "max_drawdown", "sharpe", "calmar"]].to_string())
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
