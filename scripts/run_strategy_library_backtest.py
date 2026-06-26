from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.strategy.library import available_strategies
from crypto_quant.research.strategy_library import backtest_strategy_library


def main() -> None:
    cfg = load_config()
    dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    lib_cfg = cfg.get("strategy_library", {})
    strategies = lib_cfg.get("strategies") or available_strategies()
    out_dir = resolve_path(lib_cfg.get("output_path", "reports/strategy_library"))
    summary = backtest_strategy_library(
        dataset=dataset,
        strategy_names=strategies,
        output_dir=out_dir,
        timeframe=cfg["data"]["timeframe"],
        initial_equity=cfg["trading"]["initial_equity"],
        leverage=cfg["trading"]["leverage"],
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
    )
    print(summary.head(20).to_string(index=False))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
