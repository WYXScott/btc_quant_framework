from __future__ import annotations

import tempfile
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd

from crypto_quant.research.sequence_experiments import (
    SequenceExperimentConfig,
    SequenceWalkForwardConfig,
    build_v28_sequence_report,
    run_sequence_model_experiments,
    run_sequence_walk_forward,
)


def make_dataset(n: int = 760) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="4h", tz="UTC")
    x = np.arange(n)
    close = 40000 + 2 * x + 650 * np.sin(x / 18) + 120 * np.cos(x / 5)
    y_signal = np.sin(x / 14) + 0.35 * np.cos(x / 7)
    y = (y_signal > 0).astype(int)
    future_return = pd.Series(close, index=idx).pct_change(6).shift(-6).fillna(0.0).to_numpy()
    return pd.DataFrame({
        "close": close,
        "future_return": future_return,
        "label_up": y,
        "f1": np.sin(x / 14),
        "f2": np.cos(x / 9),
        "f3": pd.Series(close).pct_change().fillna(0.0).to_numpy(),
        "f4": np.sin(x / 30),
    }, index=idx)


def main() -> None:
    dataset = make_dataset()
    features = ["f1", "f2", "f3", "f4"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cfg = SequenceExperimentConfig(
            lookback_bars=24,
            stride_bars=1,
            train_end="2020-02-20",
            valid_end="2020-03-20",
            model_names=("sequence_mlp",),
            include_torch_if_installed=False,
        )
        payload = run_sequence_model_experiments(dataset, features, tmp_path / "sequence", cfg)
        assert payload["status"] == "ok", payload
        wf_cfg = SequenceWalkForwardConfig(
            lookback_bars=24,
            train_window_days=45,
            test_window_days=20,
            min_train_sequences=120,
            min_test_sequences=25,
            model_names=("sequence_mlp",),
            include_torch_if_installed=False,
        )
        wf_payload = run_sequence_walk_forward(dataset, features, tmp_path / "wf", wf_cfg)
        assert wf_payload["status"] == "ok", wf_payload
        report = build_v28_sequence_report(tmp_path / "sequence", tmp_path / "wf", tmp_path / "report")
        assert report.exists()
    print("sequence_model_smoke passed")


if __name__ == "__main__":
    main()
