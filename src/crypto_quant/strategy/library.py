from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Any

import pandas as pd

from crypto_quant.strategy.rule_strategy import ma_trend_signal


SignalFactory = Callable[[pd.DataFrame, dict[str, Any]], pd.DataFrame]


@dataclass(frozen=True)
class StrategySpec:
    """Rule strategy candidate used by the V1.2 strategy library."""

    name: str
    description: str
    factory: SignalFactory
    params: dict[str, Any] = field(default_factory=dict)


def _stateful_long_signal(
    df: pd.DataFrame,
    enter: pd.Series,
    exit_: pd.Series,
    max_holding_bars: int | None = None,
) -> pd.DataFrame:
    out = df.copy()
    in_position = False
    bars_in_position = 0
    signals: list[int] = []
    reasons: list[str] = []

    enter = enter.reindex(out.index).fillna(False).astype(bool)
    exit_ = exit_.reindex(out.index).fillna(False).astype(bool)

    for idx in out.index:
        reason = ""
        if not in_position and bool(enter.loc[idx]):
            in_position = True
            bars_in_position = 0
            reason = "entry"
        elif in_position:
            bars_in_position += 1
            if bool(exit_.loc[idx]):
                in_position = False
                bars_in_position = 0
                reason = "exit_rule"
            elif max_holding_bars is not None and bars_in_position >= int(max_holding_bars):
                in_position = False
                bars_in_position = 0
                reason = "time_exit"
        signals.append(1 if in_position else 0)
        reasons.append(reason)

    out["signal"] = signals
    out["signal_reason"] = reasons
    return out


def buy_and_hold_strategy(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    out = df.copy()
    out["signal"] = 1
    out["signal_reason"] = "always_long"
    return out


def ma_trend_strategy(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    params = params or {}
    out = ma_trend_signal(
        df,
        fast_col=params.get("fast_col", "ma_24"),
        slow_col=params.get("slow_col", "ma_120"),
        close_col=params.get("close_col", "close"),
        vol_filter_col=params.get("vol_filter_col", "vol_ratio_24_120"),
        max_vol_ratio=float(params.get("max_vol_ratio", 2.5)),
    )
    out["signal_reason"] = out["signal"].map({1: "trend_on", 0: "flat"})
    return out


def donchian_breakout_strategy(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    params = params or {}
    entry_window = int(params.get("entry_window", 55))
    exit_window = int(params.get("exit_window", 20))
    max_holding_bars = params.get("max_holding_bars")
    high_break = df["high"].rolling(entry_window).max().shift(1)
    low_exit = df["low"].rolling(exit_window).min().shift(1)
    enter = df["close"] > high_break
    exit_ = df["close"] < low_exit
    return _stateful_long_signal(df, enter, exit_, max_holding_bars=max_holding_bars)


def volatility_squeeze_breakout_strategy(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    params = params or {}
    breakout_window = int(params.get("breakout_window", 36))
    squeeze_ratio = float(params.get("squeeze_ratio", 0.85))
    exit_ma_col = params.get("exit_ma_col", "ma_24")
    max_holding_bars = params.get("max_holding_bars", 18)
    prior_high = df["high"].rolling(breakout_window).max().shift(1)
    squeeze = df.get("vol_ratio_24_120", pd.Series(1.0, index=df.index)) < squeeze_ratio
    trend_ok = df["close"] > df.get("ma_120", df["close"].rolling(120).mean())
    enter = (df["close"] > prior_high) & squeeze & trend_ok
    exit_ = df["close"] < df.get(exit_ma_col, df["close"].rolling(24).mean())
    return _stateful_long_signal(df, enter, exit_, max_holding_bars=max_holding_bars)


def rsi_mean_reversion_strategy(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    params = params or {}
    rsi_col = params.get("rsi_col", "rsi_14")
    entry_rsi = float(params.get("entry_rsi", 32))
    exit_rsi = float(params.get("exit_rsi", 55))
    trend_filter = bool(params.get("trend_filter", True))
    max_holding_bars = params.get("max_holding_bars", 12)
    rsi = df[rsi_col]
    trend_ok = True
    if trend_filter and "ma_120" in df.columns:
        trend_ok = df["close"] > df["ma_120"]
    enter = (rsi < entry_rsi) & trend_ok
    exit_ = (rsi > exit_rsi) | (df["close"] < df.get("ma_120", df["close"]))
    return _stateful_long_signal(df, enter, exit_, max_holding_bars=max_holding_bars)


def regime_filtered_trend_strategy(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    params = params or {}
    min_trend = float(params.get("min_trend_ma_24_120", 0.0))
    max_vol_ratio = float(params.get("max_vol_ratio", 1.8))
    min_close_position = float(params.get("min_close_position", 0.45))
    trend = df.get("trend_ma_24_120", pd.Series(0.0, index=df.index)) > min_trend
    price_above = df["close"] > df.get("ma_120", df["close"].rolling(120).mean())
    vol_ok = df.get("vol_ratio_24_120", pd.Series(1.0, index=df.index)) < max_vol_ratio
    close_strong = df.get("close_position", pd.Series(0.5, index=df.index)) > min_close_position
    out = df.copy()
    out["signal"] = (trend & price_above & vol_ok & close_strong).astype(int)
    out["signal_reason"] = out["signal"].map({1: "regime_trend_on", 0: "flat"})
    return out


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "buy_and_hold": StrategySpec(
        name="buy_and_hold",
        description="Always long benchmark; useful for comparing active strategies against passive BTC exposure.",
        factory=buy_and_hold_strategy,
    ),
    "ma_trend": StrategySpec(
        name="ma_trend",
        description="MA24/MA120 trend-following baseline with optional volatility filter.",
        factory=ma_trend_strategy,
        params={"max_vol_ratio": 2.5},
    ),
    "donchian_breakout": StrategySpec(
        name="donchian_breakout",
        description="Long on 55-bar high breakout and exit on 20-bar low breakdown.",
        factory=donchian_breakout_strategy,
        params={"entry_window": 55, "exit_window": 20, "max_holding_bars": 24},
    ),
    "vol_squeeze_breakout": StrategySpec(
        name="vol_squeeze_breakout",
        description="Enter after low-volatility compression and upside breakout; designed for BTC regime transitions.",
        factory=volatility_squeeze_breakout_strategy,
        params={"breakout_window": 36, "squeeze_ratio": 0.85, "max_holding_bars": 18},
    ),
    "rsi_mean_reversion": StrategySpec(
        name="rsi_mean_reversion",
        description="RSI oversold rebound strategy with long-only trend filter.",
        factory=rsi_mean_reversion_strategy,
        params={"entry_rsi": 32, "exit_rsi": 55, "trend_filter": True, "max_holding_bars": 12},
    ),
    "regime_filtered_trend": StrategySpec(
        name="regime_filtered_trend",
        description="Trend strategy gated by volatility and candle-strength regime features.",
        factory=regime_filtered_trend_strategy,
        params={"max_vol_ratio": 1.8, "min_close_position": 0.45},
    ),
}


def available_strategies() -> list[str]:
    return list(STRATEGY_REGISTRY.keys())


def get_strategy_spec(name: str) -> StrategySpec:
    key = name.strip().lower()
    if key not in STRATEGY_REGISTRY:
        raise KeyError(f"Unknown strategy '{name}'. Available strategies: {available_strategies()}")
    return STRATEGY_REGISTRY[key]


def build_strategy_signal(df: pd.DataFrame, name: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    spec = get_strategy_spec(name)
    merged_params = dict(spec.params)
    if params:
        merged_params.update(params)
    out = spec.factory(df, merged_params)
    out["strategy_name"] = spec.name
    return out
