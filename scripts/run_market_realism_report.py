from __future__ import annotations

import pandas as pd
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.realism.market import build_market_realism_report, save_market_realism_artifacts


def _load_backtest_result(cfg):
    candidates = [
        cfg.get("market_realism", {}).get("preferred_backtest_result"),
        "reports/ensemble/ensemble_dynamic_backtest_result.csv",
        "reports/strategy_diagnostics/strategy_result.csv",
        "reports/ml_backtest/ml_backtest_result.csv",
        "reports/rule_backtest/rule_backtest_result.csv",
    ]
    for item in candidates:
        if not item:
            continue
        path = resolve_path(item)
        if path.exists():
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path, index_col=0, parse_dates=True)
            if "equity" in df.columns:
                return df, path
    raise FileNotFoundError("No usable backtest result found. Run run_ensemble_strategy.py or run_strategy_diagnostics.py first.")


def main() -> None:
    cfg = load_config()
    mr_cfg = cfg.get("market_realism", {})
    result, source_path = _load_backtest_result(cfg)
    funding_path = resolve_path(mr_cfg.get("funding_path", "data/raw/BTCUSDT_funding_rates.parquet"))
    funding = load_parquet(funding_path) if funding_path.exists() else None
    report, enriched = build_market_realism_report(
        result,
        funding,
        timeframe=cfg["data"]["timeframe"],
        maintenance_margin_rate=float(cfg.get("trading", {}).get("maintenance_margin_rate", 0.005)),
        min_liquidation_buffer=float(cfg.get("trading", {}).get("min_liquidation_buffer", 0.20)),
    )
    report["source_backtest_result"] = str(source_path)
    report["funding_path"] = str(funding_path) if funding_path.exists() else None
    paths = save_market_realism_artifacts(report, enriched, resolve_path(mr_cfg.get("output_path", "reports/market_realism")))
    print("Market realism report generated")
    print("source:", source_path)
    for key, value in paths.items():
        print(f"{key}: {value}")
    print(pd.DataFrame([report]).T.to_string(header=False))


if __name__ == "__main__":
    main()
