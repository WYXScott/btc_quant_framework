from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401

from crypto_quant.config import project_root
from crypto_quant.models.calibration import train_calibrated_direction_model
from crypto_quant.research.signal_confidence import run_signal_confidence_analysis


def make_synthetic_dataset(periods: int = 1000) -> pd.DataFrame:
    rng = np.random.default_rng(25)
    idx = pd.date_range("2020-01-01", periods=periods, freq="4h", tz="UTC")
    x = np.arange(periods)
    f1 = np.sin(x / 20.0)
    f2 = np.cos(x / 55.0)
    noise = rng.normal(0, 0.45, periods)
    score = f1 + 0.35 * f2 + noise
    label = (score > np.quantile(score, 0.52)).astype(int)
    returns = 0.002 * score + rng.normal(0, 0.006, periods)
    close = 40000 * np.exp(np.cumsum(returns))
    close_s = pd.Series(close)
    return pd.DataFrame({
        "close": close,
        "ma_24": close_s.rolling(24).mean().bfill().values,
        "ma_120": close_s.rolling(120).mean().bfill().values,
        "f1": f1,
        "f2": f2,
        "noise": noise,
        "label_up": label,
        "future_return": np.roll(close, -6) / close - 1,
    }, index=idx)


def main() -> None:
    out_dir = project_root() / "reports" / "calibration_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = make_synthetic_dataset()
    result = train_calibrated_direction_model(
        dataset=dataset,
        feature_columns=["f1", "f2", "noise", "ma_24", "ma_120"],
        train_end="2020-04-15",
        valid_end="2020-05-20",
        model_path=out_dir / "smoke_calibrated_model.joblib",
        feature_list_path=out_dir / "smoke_calibrated_features.txt",
        model_type="extra_trees",
        calibration_method="isotonic",
    )
    cfg = {
        "trading": {"initial_equity": 1000, "fee_rate": 0.0005, "slippage_rate": 0.0005, "max_notional_fraction": 3.0},
        "risk": {"max_drawdown_stop_fraction": 0.2},
        "data": {"timeframe": "4h"},
        "calibration": {"bins": 10, "confidence": {"max_exposure": 2.5, "trend_filter": True}},
    }
    confidence_payload = run_signal_confidence_analysis(dataset, out_dir / "smoke_calibrated_model.joblib", out_dir / "confidence", cfg)
    payload = {"status": "ok", "metrics": result["metrics"], "confidence": confidence_payload}
    (out_dir / "calibration_smoke_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
