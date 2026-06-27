from __future__ import annotations

from pathlib import Path
from typing import Iterable

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline

from crypto_quant.models.registry import make_model_by_name


def _as_utc_timestamp(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_index()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True, errors="raise")
    elif out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")
    return out.sort_index()


def _drop_tail_for_purge(df: pd.DataFrame, purge_bars: int) -> pd.DataFrame:
    purge = max(int(purge_bars), 0)
    if purge == 0:
        return df
    if len(df) <= purge:
        return df.iloc[0:0].copy()
    return df.iloc[:-purge].copy()


def time_split(
    df: pd.DataFrame,
    train_end: str,
    valid_end: str,
    purge_bars: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = _ensure_utc_index(df)
    train_end_ts = _as_utc_timestamp(train_end)
    valid_end_ts = _as_utc_timestamp(valid_end)
    train = data.loc[data.index <= train_end_ts]
    valid = data.loc[(data.index > train_end_ts) & (data.index <= valid_end_ts)]
    test = data.loc[data.index > valid_end_ts]
    train = _drop_tail_for_purge(train, purge_bars)
    if not test.empty:
        valid = _drop_tail_for_purge(valid, purge_bars)
    return train, valid, test


def make_model(model_type: str = "extra_trees") -> Pipeline:
    """Default low-frequency model factory.

    V1.2 routes model construction through the model registry so the same
    training, diagnostics and walk-forward code can compare multiple model
    families without changing strategy logic.
    """
    return make_model_by_name(model_type)


def evaluate_classifier(model, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
    if len(X) == 0:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "roc_auc": 0.0}
    pred = model.predict(X)
    prob = model.predict_proba(X)[:, 1]
    out = {
        "accuracy": float(accuracy_score(y, pred)),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
    }
    try:
        out["roc_auc"] = float(roc_auc_score(y, prob))
    except ValueError:
        out["roc_auc"] = 0.0
    return out


def train_direction_model(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    train_end: str,
    valid_end: str,
    model_path: str | Path,
    feature_list_path: str | Path,
    model_type: str = "extra_trees",
    purge_bars: int = 0,
) -> dict[str, dict[str, float]]:
    feature_columns = list(feature_columns)
    missing = [c for c in feature_columns + ["label_up"] if c not in dataset.columns]
    if missing:
        raise KeyError(f"Missing training columns: {missing[:10]}")

    train, valid, test = time_split(dataset, train_end=train_end, valid_end=valid_end, purge_bars=purge_bars)
    if train.empty:
        raise ValueError("Training split is empty after applying train_end and purge_bars.")
    if train["label_up"].nunique(dropna=True) < 2:
        raise ValueError("Training split contains a single label class; adjust dates or label threshold.")
    X_train, y_train = train[feature_columns], train["label_up"]
    X_valid, y_valid = valid[feature_columns], valid["label_up"]
    X_test, y_test = test[feature_columns], test["label_up"]

    model = make_model(model_type)
    model.fit(X_train, y_train)

    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)

    feature_list_path = Path(feature_list_path)
    feature_list_path.parent.mkdir(parents=True, exist_ok=True)
    feature_list_path.write_text("\n".join(feature_columns), encoding="utf-8")

    return {
        "train": evaluate_classifier(model, X_train, y_train),
        "valid": evaluate_classifier(model, X_valid, y_valid),
        "test": evaluate_classifier(model, X_test, y_test),
    }
