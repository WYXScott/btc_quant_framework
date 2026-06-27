from __future__ import annotations

import json
import _bootstrap  # noqa: F401

import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.models.predict import add_model_probability
from crypto_quant.strategy.ml_strategy import probability_signal
from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import save_backtest_reports
from crypto_quant.reporting.plots import plot_equity_curve, plot_drawdown


def _filter_out_of_sample(df: pd.DataFrame, valid_end: str) -> pd.DataFrame:
    out = df.copy().sort_index()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True, errors="raise")
    elif out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    cutoff = pd.Timestamp(valid_end)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    out = out.loc[out.index > cutoff].copy()
    if out.empty:
        raise RuntimeError("No out-of-sample rows after model.valid_end; adjust config dates before running ML backtest.")
    return out


def main() -> None:
    cfg = load_config()
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    df = add_model_probability(
        df,
        model_path=resolve_path(cfg["model"]["model_path"]),
        feature_list_path=resolve_path(cfg["model"]["feature_list_path"]),
    )
    df = _filter_out_of_sample(df, cfg["model"]["valid_end"])
    df = probability_signal(
        df,
        prob_col="prob_up",
        buy_threshold=cfg["model"]["probability_buy_threshold"],
        exit_threshold=cfg["model"]["probability_exit_threshold"],
        trend_filter=True,
        max_holding_bars=cfg["risk"].get("max_holding_bars"),
    )
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
    out_dir = resolve_path("reports/ml_backtest")
    report = save_backtest_reports(result, out_dir, prefix="ml", timeframe=cfg["data"]["timeframe"])
    plot_equity_curve(result, out_dir / "ml_equity.png", title="ML Strategy Equity")
    plot_drawdown(result, out_dir / "ml_drawdown.png", title="ML Strategy Drawdown")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
