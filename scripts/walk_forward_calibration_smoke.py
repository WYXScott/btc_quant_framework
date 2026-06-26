from __future__ import annotations

import json
import numpy as np
import pandas as pd
import _bootstrap  # noqa: F401

from crypto_quant.config import project_root
from crypto_quant.models.walk_forward_calibration import WalkForwardCalibrationConfig, walk_forward_calibrated_predict, save_walk_forward_calibration_report


def make_dataset(periods: int = 1400) -> pd.DataFrame:
    rng = np.random.default_rng(26)
    idx = pd.date_range("2021-01-01", periods=periods, freq="4h", tz="UTC")
    x = np.arange(periods)
    f1 = np.sin(x / 17.0)
    f2 = np.cos(x / 43.0)
    noise = rng.normal(0, 0.5, periods)
    score = f1 + 0.45 * f2 + noise
    label = (score > np.median(score)).astype(int)
    returns = 0.0015 * score + rng.normal(0, 0.005, periods)
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
    dataset = make_dataset()
    cfg = WalkForwardCalibrationConfig(
        train_window_days=120,
        calibration_window_days=35,
        test_window_days=25,
        min_train_bars=400,
        min_calibration_bars=120,
        min_test_bars=30,
        model_type="extra_trees",
        calibration_method="isotonic",
        bins=8,
    )
    preds, folds, skipped = walk_forward_calibrated_predict(dataset, ["f1", "f2", "noise", "ma_24", "ma_120"], cfg)
    assert not preds.empty
    assert not folds.empty
    assert {"prob_up_raw_wf", "prob_up_calibrated_wf", "fold_id"}.issubset(preds.columns)
    out_dir = project_root() / "reports" / "walk_forward_calibration_smoke"
    full_cfg = {
        "trading": {"initial_equity": 1000, "fee_rate": 0.0005, "slippage_rate": 0.0005, "max_notional_fraction": 3.0},
        "risk": {"max_drawdown_stop_fraction": 0.2},
        "data": {"timeframe": "4h"},
        "calibration": {"bins": 8, "confidence": {"max_exposure": 2.5, "trend_filter": True}},
    }
    summary = save_walk_forward_calibration_report(preds, folds, skipped, out_dir, full_cfg, cfg)
    payload = {"status": "ok", "folds": len(folds), "bars": len(preds), "summary": summary}
    (out_dir / "walk_forward_calibration_smoke_result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
