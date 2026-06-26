from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd


def load_feature_columns(path: str | Path) -> list[str]:
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def add_model_probability(df: pd.DataFrame, model_path: str | Path, feature_list_path: str | Path) -> pd.DataFrame:
    out = df.copy()
    model = joblib.load(model_path)
    feature_columns = load_feature_columns(feature_list_path)
    missing = [c for c in feature_columns if c not in out.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing[:10]}")
    out["prob_up"] = model.predict_proba(out[feature_columns])[:, 1]
    return out


def add_calibrated_model_probability(
    df: pd.DataFrame,
    calibrated_model_path: str | Path,
    feature_list_path: str | Path | None = None,
) -> pd.DataFrame:
    """Add raw and calibrated probabilities from a V2.5 calibrated model.

    feature_list_path is optional because the calibrated model stores its feature
    columns internally. It is kept for compatibility with older script patterns.
    """
    out = df.copy()
    model = joblib.load(calibrated_model_path)
    feature_columns = getattr(model, "feature_columns", None)
    if feature_columns is None:
        if feature_list_path is None:
            raise ValueError("feature_list_path is required when calibrated model does not store feature_columns")
        feature_columns = load_feature_columns(feature_list_path)
    missing = [c for c in feature_columns if c not in out.columns]
    if missing:
        raise ValueError(f"Missing feature columns: {missing[:10]}")
    if hasattr(model, "raw_predict_proba"):
        out["prob_up_raw"] = model.raw_predict_proba(out[feature_columns])
    if hasattr(model, "predict_calibrated_proba"):
        out["prob_up_calibrated"] = model.predict_calibrated_proba(out[feature_columns])
    else:
        out["prob_up_calibrated"] = model.predict_proba(out[feature_columns])[:, 1]
    return out
