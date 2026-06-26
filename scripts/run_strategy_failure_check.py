from __future__ import annotations

import _bootstrap  # noqa: F401

import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.research.ensemble import (
    load_candidate_table,
    select_top_candidates,
    build_ensemble_signal_table,
    apply_strategy_failure_filter,
)


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    ens_cfg = cfg.get("ensemble", {})
    fail_cfg = cfg.get("strategy_failure", {})
    rob_cfg = cfg.get("robustness", {})
    candidate_path = resolve_path(
        ens_cfg.get(
            "candidate_table_path",
            str(resolve_path(rob_cfg.get("parameter_search_path", "reports/robustness/parameter_search")) / "strategy_parameter_search_summary.csv"),
        )
    )
    candidates = select_top_candidates(
        load_candidate_table(candidate_path),
        top_n=int(ens_cfg.get("top_n", 5)),
        min_trades=int(ens_cfg.get("min_trades", 5)),
        max_overfit_risk=float(ens_cfg.get("max_overfit_risk", 80.0)),
    )
    signal_table, meta = build_ensemble_signal_table(dataset, candidates, vote_threshold=float(ens_cfg.get("vote_threshold", 0.50)))
    _, failure = apply_strategy_failure_filter(
        signal_table,
        meta,
        lookback_bars=int(fail_cfg.get("lookback_bars", 90)),
        min_recent_return=float(fail_cfg.get("min_recent_return", -0.08)),
        max_recent_drawdown=float(fail_cfg.get("max_recent_drawdown", -0.12)),
    )
    out_dir = resolve_path(fail_cfg.get("output_path", "reports/strategy_failure"))
    out_dir.mkdir(parents=True, exist_ok=True)
    failure.to_csv(out_dir / "strategy_failure_status.csv", index=False, encoding="utf-8-sig")
    print(failure.to_string(index=False) if not failure.empty else "No candidate failure rows.")
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
