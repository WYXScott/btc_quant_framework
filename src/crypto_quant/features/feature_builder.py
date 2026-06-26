from __future__ import annotations

import numpy as np
import pandas as pd


def add_return_features(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    out = df.copy()
    out["log_close"] = np.log(out["close"])
    out["ret_1"] = out["close"].pct_change(1)
    out["log_ret_1"] = out["log_close"].diff(1)
    for w in windows:
        out[f"ret_{w}"] = out["close"].pct_change(w)
        out[f"log_ret_{w}"] = out["log_close"].diff(w)
    return out


def add_trend_features(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    out = df.copy()
    for w in windows:
        ma = out["close"].rolling(w).mean()
        ema = out["close"].ewm(span=w, adjust=False).mean()
        out[f"ma_{w}"] = ma
        out[f"ema_{w}"] = ema
        out[f"close_ma_ratio_{w}"] = out["close"] / ma - 1
        out[f"close_ema_ratio_{w}"] = out["close"] / ema - 1
    if 12 in windows and 24 in windows:
        out["trend_ma_12_24"] = out["ma_12"] / out["ma_24"] - 1
    if 24 in windows and 120 in windows:
        out["trend_ma_24_120"] = out["ma_24"] / out["ma_120"] - 1
    return out


def add_volatility_features(df: pd.DataFrame, windows: list[int], atr_window: int = 14) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["close"].shift(1)
    tr1 = out["high"] - out["low"]
    tr2 = (out["high"] - prev_close).abs()
    tr3 = (out["low"] - prev_close).abs()
    out["true_range"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    out[f"atr_{atr_window}"] = out["true_range"].rolling(atr_window).mean()
    out[f"atr_pct_{atr_window}"] = out[f"atr_{atr_window}"] / out["close"]
    for w in windows:
        out[f"rv_{w}"] = out["log_ret_1"].rolling(w).std() * np.sqrt(w)
        out[f"range_pct_{w}"] = ((out["high"] - out["low"]) / out["close"]).rolling(w).mean()
    if 24 in windows and 120 in windows:
        out["vol_ratio_24_120"] = out["rv_24"] / out["rv_120"]
    return out


def add_volume_features(df: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    out = df.copy()
    out["volume_change_1"] = out["volume"].pct_change(1)
    out["quote_volume"] = out["close"] * out["volume"]
    for w in windows:
        vol_ma = out["volume"].rolling(w).mean()
        qv_ma = out["quote_volume"].rolling(w).mean()
        out[f"volume_ratio_{w}"] = out["volume"] / vol_ma - 1
        out[f"quote_volume_ratio_{w}"] = out["quote_volume"] / qv_ma - 1
    return out


def add_candle_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    bar_range = (out["high"] - out["low"]).replace(0, np.nan)
    body = (out["close"] - out["open"]).abs()
    upper_shadow = out["high"] - out[["open", "close"]].max(axis=1)
    lower_shadow = out[["open", "close"]].min(axis=1) - out["low"]
    out["body_ratio"] = body / bar_range
    out["upper_shadow_ratio"] = upper_shadow / bar_range
    out["lower_shadow_ratio"] = lower_shadow / bar_range
    out["close_position"] = (out["close"] - out["low"]) / bar_range
    out["is_green"] = (out["close"] > out["open"]).astype(int)
    return out


def add_rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    out = df.copy()
    delta = out["close"].diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    out[f"rsi_{window}"] = 100 - 100 / (1 + rs)
    return out



def sanitize_feature_frame(df: pd.DataFrame, clip_abs: float | None = 1e6) -> pd.DataFrame:
    """Replace non-finite values produced by feature ratios with NaN.

    Some venue datasets can contain zero/near-zero volume or rolling volatility
    values. Ratio features such as volume_ratio and vol_ratio can then become
    +/-inf, which SimpleImputer does not accept. This function converts those
    values to NaN so the existing imputer/dropna pipeline can handle them.
    Optionally clip extreme finite numeric values to keep models numerically
    well-conditioned.
    """
    out = df.copy()
    numeric_cols = out.select_dtypes(include=[np.number]).columns
    if len(numeric_cols) == 0:
        return out
    out[numeric_cols] = out[numeric_cols].replace([np.inf, -np.inf], np.nan)
    if clip_abs is not None and clip_abs > 0:
        out[numeric_cols] = out[numeric_cols].clip(lower=-float(clip_abs), upper=float(clip_abs))
    return out

def build_features(
    df: pd.DataFrame,
    windows: list[int],
    atr_window: int = 14,
    rsi_window: int = 14,
    dropna: bool = True,
) -> pd.DataFrame:
    out = df.copy().sort_index()
    out = add_return_features(out, windows)
    out = add_trend_features(out, windows)
    out = add_volatility_features(out, windows, atr_window=atr_window)
    out = add_volume_features(out, windows)
    out = add_candle_features(out)
    out = add_rsi(out, window=rsi_window)
    out = sanitize_feature_frame(out)
    if dropna:
        out = out.dropna()
    return out


def get_model_feature_columns(df: pd.DataFrame) -> list[str]:
    excluded = {
        "open", "high", "low", "close", "volume", "log_close", "future_return", "label_up",
        "ma_3", "ma_6", "ma_12", "ma_24", "ma_48", "ma_120",
        "ema_3", "ema_6", "ema_12", "ema_24", "ema_48", "ema_120",
    }
    cols = [c for c in df.columns if c not in excluded and pd.api.types.is_numeric_dtype(df[c])]
    return cols
