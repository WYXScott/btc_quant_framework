from __future__ import annotations

import json
import _bootstrap  # noqa: F401

import pandas as pd

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.research.signal_confidence import ConfidencePolicy, add_calibrated_probabilities, apply_confidence_policy
from crypto_quant.backtest.dynamic_engine import DynamicExposureBacktester
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
        raise RuntimeError("No out-of-sample rows after model.valid_end; adjust config dates before running calibrated ML backtest.")
    return out


def main() -> None:
    cfg = load_config()
    calibration_cfg = cfg.get("calibration", {})
    df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    df = add_calibrated_probabilities(
        df,
        calibrated_model_path=resolve_path(calibration_cfg.get("calibrated_model_path", "models/btc_direction_model_calibrated.joblib")),
    )
    df = _filter_out_of_sample(df, cfg["model"]["valid_end"])
    df = apply_confidence_policy(df, policy=ConfidencePolicy.from_config(cfg))
    bt = DynamicExposureBacktester(
        initial_equity=cfg["trading"]["initial_equity"],
        max_notional_fraction=float(calibration_cfg.get("confidence", {}).get("max_exposure", cfg["trading"]["max_notional_fraction"])),
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
    )
    result = bt.run(df, exposure_col="target_exposure_confidence")
    out_dir = resolve_path("reports/calibrated_ml_backtest")
    summary = save_backtest_reports(result, out_dir, prefix="calibrated_ml", timeframe=cfg["data"]["timeframe"])
    plot_equity_curve(result, out_dir / "calibrated_ml_equity.png", title="Calibrated ML Dynamic Exposure Equity")
    plot_drawdown(result, out_dir / "calibrated_ml_drawdown.png", title="Calibrated ML Dynamic Exposure Drawdown")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"saved reports: {out_dir}")


if __name__ == "__main__":
    main()
