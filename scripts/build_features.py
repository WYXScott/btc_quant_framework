from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet, save_parquet
from crypto_quant.data.quality import validate_ohlcv_dataframe_from_config
from crypto_quant.features.feature_builder import build_features
from crypto_quant.features.labels import add_future_return_label


def main() -> None:
    cfg = load_config()
    raw = load_parquet(resolve_path(cfg["data"]["raw_path"]))
    validate_ohlcv_dataframe_from_config(
        raw,
        cfg,
        output_dir=resolve_path(cfg.get("data_quality", {}).get("output_path", "reports/data_quality")),
        context="build_features",
    )
    feat = build_features(
        raw,
        windows=cfg["features"]["windows"],
        atr_window=cfg["features"]["atr_window"],
        rsi_window=cfg["features"]["rsi_window"],
        dropna=cfg["features"]["dropna"],
    )
    dataset = add_future_return_label(
        feat,
        horizon_bars=cfg["labels"]["horizon_bars"],
        positive_return_threshold=cfg["labels"]["positive_return_threshold"],
    ).dropna()
    save_parquet(feat, resolve_path(cfg["data"]["feature_path"]))
    save_parquet(dataset, resolve_path(cfg["data"]["dataset_path"]))
    print(f"features: {feat.shape}, dataset: {dataset.shape}")
    print(dataset[["close", "future_return", "label_up"]].tail())


if __name__ == "__main__":
    main()
