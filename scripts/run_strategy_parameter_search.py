from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.research.robustness import strategy_parameter_search


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    rob_cfg = cfg.get("robustness", {})
    out_dir = resolve_path(rob_cfg.get("parameter_search_path", "reports/robustness/parameter_search"))
    table = strategy_parameter_search(
        dataset=dataset,
        strategy_names=rob_cfg.get("strategies") or cfg.get("strategy_library", {}).get("strategies", []),
        output_dir=out_dir,
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
    print(table.head(30).to_string(index=False))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
