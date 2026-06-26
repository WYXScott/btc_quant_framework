from __future__ import annotations

from pathlib import Path
import json
import numpy as np
import pandas as pd

import _bootstrap  # noqa: F401

from crypto_quant.config import project_root
from crypto_quant.models.train_direction_model import train_direction_model


def make_synthetic_dataset(periods: int = 900) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=periods, freq="4h", tz="UTC")
    x = np.arange(periods)
    f1 = np.sin(x / 12.0)
    f2 = np.cos(x / 24.0)
    f3 = np.sin(x / 48.0) + 0.1 * np.random.default_rng(42).normal(size=periods)
    score = 0.8 * f1 + 0.4 * f2 + 0.2 * f3
    y = (score > np.median(score)).astype(int)
    close = 40000 + np.cumsum(10 * f1 + np.random.default_rng(7).normal(0, 15, size=periods))
    return pd.DataFrame({
        "close": close,
        "f1": f1,
        "f2": f2,
        "f3": f3,
        "label_up": y,
    }, index=idx)


def main() -> None:
    out_dir = project_root() / "reports" / "model_train_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "smoke_direction_model.joblib"
    feature_list_path = out_dir / "smoke_feature_columns.txt"
    dataset = make_synthetic_dataset()
    metrics = train_direction_model(
        dataset=dataset,
        feature_columns=["f1", "f2", "f3"],
        train_end="2020-04-15",
        valid_end="2020-05-20",
        model_path=model_path,
        feature_list_path=feature_list_path,
        model_type="extra_trees",
    )
    (out_dir / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "metrics": metrics, "model_path": str(model_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
