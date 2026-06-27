from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd

from crypto_quant.models.train_direction_model import evaluate_classifier
from crypto_quant.models.registry import make_model_by_name


@dataclass
class WalkForwardConfig:
    train_window_days: int = 1095
    test_window_days: int = 90
    min_train_bars: int = 1000
    start: str | None = None
    end: str | None = None
    purge_bars: int = 0

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "WalkForwardConfig":
        c = cfg.get("walk_forward", {}) or {}
        labels = cfg.get("labels", {}) or {}
        return cls(
            train_window_days=int(c.get("train_window_days", 1095)),
            test_window_days=int(c.get("test_window_days", 90)),
            min_train_bars=int(c.get("min_train_bars", 1000)),
            start=c.get("start"),
            end=c.get("end"),
            purge_bars=int(c.get("purge_bars", labels.get("horizon_bars", 0))),
        )


def _as_utc_timestamp(value: str | None) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


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


def walk_forward_predict(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    cfg: WalkForwardConfig,
    label_col: str = "label_up",
    probability_col: str = "prob_up_wf",
    model_type: str = "extra_trees",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Anchored/rolling walk-forward probability generation.

    For each fold, train only on data strictly before the fold test window.
    The default uses a rolling train window to reduce regime-staleness.
    """
    feature_columns = list(feature_columns)
    data = _ensure_utc_index(dataset)

    start = _as_utc_timestamp(cfg.start)
    end = _as_utc_timestamp(cfg.end)
    if start is None:
        start = data.index.min() + pd.Timedelta(days=cfg.train_window_days)
    if end is None:
        end = data.index.max()

    prob = pd.Series(index=data.index, dtype=float, name=probability_col)
    fold_rows: list[dict[str, object]] = []
    fold_id = 0
    test_start = start

    while test_start < end:
        train_start = test_start - pd.Timedelta(days=cfg.train_window_days)
        test_end = min(test_start + pd.Timedelta(days=cfg.test_window_days), end)

        train_mask = (data.index >= train_start) & (data.index < test_start)
        test_mask = (data.index >= test_start) & (data.index < test_end)
        train = _drop_tail_for_purge(data.loc[train_mask], cfg.purge_bars)
        test = data.loc[test_mask]

        if len(train) < cfg.min_train_bars or len(test) == 0 or train[label_col].nunique(dropna=True) < 2:
            test_start = test_end
            continue

        X_train = train[feature_columns]
        y_train = train[label_col]
        X_test = test[feature_columns]
        y_test = test[label_col]

        model = make_model_by_name(model_type)
        model.fit(X_train, y_train)
        prob.loc[test.index] = model.predict_proba(X_test)[:, 1]
        metrics = evaluate_classifier(model, X_test, y_test)
        fold_rows.append(
            {
                "fold_id": fold_id,
                "train_start": train.index.min(),
                "train_end": train.index.max(),
                "test_start": test.index.min(),
                "test_end": test.index.max(),
                "train_bars": len(train),
                "test_bars": len(test),
                "purge_bars": int(cfg.purge_bars),
                "model_type": model_type,
                **metrics,
            }
        )
        fold_id += 1
        test_start = test_end

    out = data.copy()
    out[probability_col] = prob
    out = out.dropna(subset=[probability_col])
    folds = pd.DataFrame(fold_rows)
    return out, folds
