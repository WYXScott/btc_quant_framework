from __future__ import annotations

import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.strategy.rule_strategy import ma_trend_signal
from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import save_backtest_reports
from crypto_quant.reporting.plots import plot_equity_curve, plot_drawdown


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["feature_path"]))
    df = ma_trend_signal(df)
    bt = LeveragedBacktester(
        initial_equity=cfg["trading"]["initial_equity"],
        leverage=cfg["trading"]["leverage"],
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
    )
    result = bt.run(df, signal_col="signal")
    out_dir = resolve_path("reports/rule_backtest")
    report = save_backtest_reports(result, out_dir, prefix="rule", timeframe=cfg["data"]["timeframe"])
    plot_equity_curve(result, out_dir / "rule_equity.png", title="Rule Strategy Equity")
    plot_drawdown(result, out_dir / "rule_drawdown.png", title="Rule Strategy Drawdown")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
