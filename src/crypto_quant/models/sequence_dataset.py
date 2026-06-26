from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SequenceDataset:
    """Container for fixed-lookback sequence classification data.

    X has shape (n_samples, lookback_bars, n_features).  Each y/index row is
    aligned to the final bar in the lookback window, so using row t only consumes
    features available up to t.  The label column should already be shifted in
    feature_builder/labels, e.g. future 6-bar direction.
    """

    X: np.ndarray
    y: np.ndarray
    index: pd.DatetimeIndex
    feature_columns: list[str]
    lookback_bars: int
    future_return: np.ndarray | None = None
    close: np.ndarray | None = None

    def flatten(self) -> np.ndarray:
        return flatten_sequences(self.X)

    def to_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame({"label_up": self.y.astype(int)}, index=self.index)
        if self.future_return is not None:
            frame["future_return"] = self.future_return.astype(float)
        if self.close is not None:
            frame["close"] = self.close.astype(float)
        return frame


def flatten_sequences(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float)
    if X.ndim != 3:
        raise ValueError(f"Expected 3D sequence array; got shape={X.shape}")
    return X.reshape(X.shape[0], X.shape[1] * X.shape[2])


def _ensure_utc_index(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        return idx.tz_localize("UTC")
    return idx.tz_convert("UTC")


def build_sequence_dataset(
    dataset: pd.DataFrame,
    feature_columns: Iterable[str],
    lookback_bars: int = 48,
    stride_bars: int = 1,
    label_col: str = "label_up",
    future_return_col: str = "future_return",
    close_col: str = "close",
    dropna: bool = True,
) -> SequenceDataset:
    """Build fixed-length rolling windows for sequence model experiments.

    The function is intentionally conservative: missing/inf feature rows are
    replaced with NaN and can be dropped before sequence construction.  This
    keeps the sequence models from silently learning from malformed rows.
    """
    lookback = int(lookback_bars)
    stride = max(int(stride_bars), 1)
    if lookback < 2:
        raise ValueError("lookback_bars must be at least 2")

    feature_columns = list(feature_columns)
    missing = [c for c in feature_columns + [label_col] if c not in dataset.columns]
    if missing:
        raise KeyError(f"Missing columns for sequence dataset: {missing}")

    data = dataset.copy().sort_index()
    data.index = _ensure_utc_index(data.index)
    data = data.replace([np.inf, -np.inf], np.nan)
    required_cols = feature_columns + [label_col]
    optional_cols = [c for c in [future_return_col, close_col] if c in data.columns]
    if dropna:
        data = data.dropna(subset=required_cols)

    if len(data) < lookback:
        empty_index = pd.DatetimeIndex([], tz="UTC")
        return SequenceDataset(
            X=np.empty((0, lookback, len(feature_columns)), dtype=float),
            y=np.empty((0,), dtype=int),
            index=empty_index,
            feature_columns=feature_columns,
            lookback_bars=lookback,
            future_return=np.empty((0,), dtype=float) if future_return_col in data.columns else None,
            close=np.empty((0,), dtype=float) if close_col in data.columns else None,
        )

    feature_values = data[feature_columns].astype(float).to_numpy()
    labels = data[label_col].astype(int).to_numpy()
    future_return_values = data[future_return_col].astype(float).to_numpy() if future_return_col in data.columns else None
    close_values = data[close_col].astype(float).to_numpy() if close_col in data.columns else None

    windows: list[np.ndarray] = []
    ys: list[int] = []
    idx: list[pd.Timestamp] = []
    future_returns: list[float] = []
    closes: list[float] = []
    for end in range(lookback - 1, len(data), stride):
        start = end - lookback + 1
        window = feature_values[start:end + 1]
        if np.isnan(window).any():
            continue
        y = labels[end]
        if pd.isna(y):
            continue
        windows.append(window)
        ys.append(int(y))
        idx.append(data.index[end])
        if future_return_values is not None:
            future_returns.append(float(future_return_values[end]))
        if close_values is not None:
            closes.append(float(close_values[end]))

    if not windows:
        empty_index = pd.DatetimeIndex([], tz="UTC")
        return SequenceDataset(
            X=np.empty((0, lookback, len(feature_columns)), dtype=float),
            y=np.empty((0,), dtype=int),
            index=empty_index,
            feature_columns=feature_columns,
            lookback_bars=lookback,
            future_return=np.empty((0,), dtype=float) if future_return_values is not None else None,
            close=np.empty((0,), dtype=float) if close_values is not None else None,
        )

    return SequenceDataset(
        X=np.asarray(windows, dtype=float),
        y=np.asarray(ys, dtype=int),
        index=pd.DatetimeIndex(idx),
        feature_columns=feature_columns,
        lookback_bars=lookback,
        future_return=np.asarray(future_returns, dtype=float) if future_return_values is not None else None,
        close=np.asarray(closes, dtype=float) if close_values is not None else None,
    )


def split_sequence_dataset(
    seq: SequenceDataset,
    train_end: str,
    valid_end: str,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Time split a SequenceDataset into train/valid/test dictionaries."""
    train_end_ts = pd.Timestamp(train_end, tz="UTC")
    valid_end_ts = pd.Timestamp(valid_end, tz="UTC")
    idx = seq.index
    masks = {
        "train": idx <= train_end_ts,
        "valid": (idx > train_end_ts) & (idx <= valid_end_ts),
        "test": idx > valid_end_ts,
    }

    def pack(mask: np.ndarray) -> dict[str, np.ndarray]:
        out = {
            "X": seq.X[mask],
            "y": seq.y[mask],
            "index": idx[mask],
        }
        if seq.future_return is not None:
            out["future_return"] = seq.future_return[mask]
        if seq.close is not None:
            out["close"] = seq.close[mask]
        return out

    return pack(masks["train"]), pack(masks["valid"]), pack(masks["test"])
