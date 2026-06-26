from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.research.ensemble import (
    load_candidate_table,
    select_top_candidates,
    run_ensemble_backtest,
)


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    ens_cfg = cfg.get("ensemble", {})
    rob_cfg = cfg.get("robustness", {})
    candidate_path = resolve_path(
        ens_cfg.get(
            "candidate_table_path",
            str(resolve_path(rob_cfg.get("parameter_search_path", "reports/robustness/parameter_search")) / "strategy_parameter_search_summary.csv"),
        )
    )
    candidate_table = load_candidate_table(candidate_path)
    candidates = select_top_candidates(
        candidate_table,
        top_n=int(ens_cfg.get("top_n", 5)),
        min_trades=int(ens_cfg.get("min_trades", 5)),
        max_overfit_risk=float(ens_cfg.get("max_overfit_risk", 80.0)),
    )
    out_dir = resolve_path(ens_cfg.get("output_path", "reports/ensemble"))
    outputs = run_ensemble_backtest(
        dataset=dataset,
        candidates=candidates,
        output_dir=out_dir,
        timeframe=cfg["data"]["timeframe"],
        initial_equity=cfg["trading"]["initial_equity"],
        base_leverage=float(ens_cfg.get("base_leverage", cfg["trading"].get("leverage", 3.0))),
        max_exposure=float(ens_cfg.get("max_exposure", cfg["trading"].get("max_notional_fraction", 3.0))),
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
        vote_threshold=float(ens_cfg.get("vote_threshold", 0.50)),
        vol_target_annual=float(ens_cfg.get("vol_target_annual", 0.45)),
        vol_window_bars=int(ens_cfg.get("vol_window_bars", 42)),
        regime_adjustment=bool(ens_cfg.get("regime_adjustment", True)),
    )
    print("ensemble summary:")
    print(outputs["summary"])
    print("\nselected candidates:")
    print(outputs["candidate_meta"].to_string(index=False))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
