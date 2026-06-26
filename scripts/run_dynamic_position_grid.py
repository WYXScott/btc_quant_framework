from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.research.ensemble import (
    load_candidate_table,
    select_top_candidates,
    build_ensemble_signal_table,
    dynamic_position_grid,
)


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    ens_cfg = cfg.get("ensemble", {})
    dyn_cfg = cfg.get("dynamic_positioning", {})
    rob_cfg = cfg.get("robustness", {})
    candidate_path = resolve_path(
        ens_cfg.get(
            "candidate_table_path",
            str(resolve_path(rob_cfg.get("parameter_search_path", "reports/robustness/parameter_search")) / "strategy_parameter_search_summary.csv"),
        )
    )
    table = load_candidate_table(candidate_path)
    candidates = select_top_candidates(
        table,
        top_n=int(ens_cfg.get("top_n", 5)),
        min_trades=int(ens_cfg.get("min_trades", 5)),
        max_overfit_risk=float(ens_cfg.get("max_overfit_risk", 80.0)),
    )
    signal_table, meta = build_ensemble_signal_table(
        dataset,
        candidates,
        vote_threshold=float(ens_cfg.get("vote_threshold", 0.50)),
    )
    out_dir = resolve_path(dyn_cfg.get("output_path", "reports/dynamic_positioning"))
    grid = dynamic_position_grid(
        signal_table=signal_table,
        output_dir=out_dir,
        timeframe=cfg["data"]["timeframe"],
        initial_equity=cfg["trading"]["initial_equity"],
        base_leverages=dyn_cfg.get("base_leverages", [2.0, 3.0, 5.0]),
        max_exposures=dyn_cfg.get("max_exposures", [1.5, 2.0, 3.0]),
        vol_targets=dyn_cfg.get("vol_targets_annual", [0.30, 0.45, 0.60]),
        vol_windows=dyn_cfg.get("vol_windows_bars", [24, 42, 72]),
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
    )
    meta.to_csv(out_dir / "grid_candidate_meta.csv", index=False, encoding="utf-8-sig")
    print(grid.head(30).to_string(index=False))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
