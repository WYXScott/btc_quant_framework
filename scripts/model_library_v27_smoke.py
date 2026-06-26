from __future__ import annotations

import tempfile
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd

from crypto_quant.research.enhanced_model_library import run_enhanced_model_library
from crypto_quant.research.walk_forward_calibration_library import run_walk_forward_calibration_model_library


def make_dataset(n: int = 600) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    x = np.arange(n)
    close = 40000 + x * 2 + 500 * np.sin(x / 15)
    future_return = pd.Series(close, index=idx).pct_change(6).shift(-6).fillna(0.0)
    y = ((np.sin(x / 9) + 0.25 * np.cos(x / 5)) > 0).astype(int)
    return pd.DataFrame({
        "close": close,
        "ma_24": pd.Series(close).rolling(24, min_periods=1).mean().values,
        "ma_120": pd.Series(close).rolling(120, min_periods=1).mean().values,
        "future_return": future_return.values,
        "label_up": y,
        "f1": np.sin(x / 9),
        "f2": np.cos(x / 7),
        "f3": np.sin(x / 13),
    }, index=idx)


def main() -> None:
    dataset = make_dataset()
    features = ["f1", "f2", "f3"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        enhanced = run_enhanced_model_library(
            dataset=dataset,
            feature_columns=features,
            model_names=["extra_trees", "logistic_l2"],
            train_end="2020-02-15",
            valid_end="2020-03-15",
            output_dir=tmp_path / "enhanced",
        )
        assert enhanced["runnable_models"]
        cfg = {
            "data": {"timeframe": "4h"},
            "trading": {"initial_equity": 1000.0, "fee_rate": 0.0005, "slippage_rate": 0.0005},
            "risk": {"max_drawdown_stop_fraction": 0.20},
            "calibration": {"confidence": {"weak_threshold": 0.55, "medium_threshold": 0.60, "strong_threshold": 0.65,
                                             "weak_exposure": 0.5, "medium_exposure": 1.0, "strong_exposure": 1.5,
                                             "max_exposure": 2.0, "trend_filter": True}},
            "walk_forward_calibration": {
                "train_window_days": 45,
                "calibration_window_days": 15,
                "test_window_days": 15,
                "min_train_bars": 120,
                "min_calibration_bars": 30,
                "min_test_bars": 20,
                "model_type": "extra_trees",
                "method": "isotonic",
                "bins": 5,
            },
        }
        wf_table = run_walk_forward_calibration_model_library(
            dataset=dataset,
            feature_columns=features,
            cfg=cfg,
            output_dir=tmp_path / "wf",
            model_names=["extra_trees", "logistic_l2"],
            include_optional_if_installed=False,
        )
        assert not wf_table.empty
        assert set(wf_table["status"]).issubset({"ok", "failed", "skipped"})
    print("model_library_v27_smoke passed")


if __name__ == "__main__":
    main()
