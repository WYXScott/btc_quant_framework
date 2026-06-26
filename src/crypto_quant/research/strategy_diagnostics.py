from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_quant.backtest.metrics import drawdown_series, performance_summary, period_performance
from crypto_quant.backtest.trades import extract_long_trades, trade_summary


def regime_table(result: pd.DataFrame, timeframe: str = "4h") -> pd.DataFrame:
    """Summarize performance by simple BTC market regimes.

    Regimes are intentionally simple and auditable:
    - trend: close above/below ma_120;
    - volatility: atr_pct_14 or rv_24 above/below its rolling median.
    """
    if result.empty:
        return pd.DataFrame()
    data = result.copy()
    if "ma_120" in data and "close" in data:
        data["trend_regime"] = np.where(data["close"] >= data["ma_120"], "above_ma120", "below_ma120")
    else:
        data["trend_regime"] = "unknown_trend"
    vol_col = "atr_pct_14" if "atr_pct_14" in data else ("rv_24" if "rv_24" in data else None)
    if vol_col:
        med = data[vol_col].rolling(120, min_periods=20).median()
        data["vol_regime"] = np.where(data[vol_col] >= med, "high_vol", "low_vol")
    else:
        data["vol_regime"] = "unknown_vol"

    rows = []
    for keys, chunk in data.groupby(["trend_regime", "vol_regime"], dropna=False):
        if len(chunk) < 3:
            continue
        rows.append({
            "trend_regime": keys[0],
            "vol_regime": keys[1],
            "bars": int(len(chunk)),
            **performance_summary(chunk, timeframe=timeframe),
            **trade_summary(extract_long_trades(chunk)),
        })
    return pd.DataFrame(rows).sort_values(["calmar", "sharpe"], ascending=[False, False]) if rows else pd.DataFrame()


def drawdown_event_table(result: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    if result.empty or "equity" not in result:
        return pd.DataFrame()
    dd = drawdown_series(result["equity"])
    events = []
    in_event = False
    start = trough = end = None
    min_dd = 0.0
    for ts, val in dd.items():
        if val < 0 and not in_event:
            in_event = True
            start = ts
            trough = ts
            min_dd = float(val)
        elif val < 0 and in_event:
            if float(val) < min_dd:
                min_dd = float(val)
                trough = ts
        elif val >= 0 and in_event:
            end = ts
            events.append({"start": start, "trough": trough, "recovery": end, "max_drawdown": min_dd})
            in_event = False
    if in_event:
        events.append({"start": start, "trough": trough, "recovery": pd.NaT, "max_drawdown": min_dd})
    out = pd.DataFrame(events)
    if out.empty:
        return out
    out["duration_bars"] = out.apply(lambda r: len(result.loc[r["start"]: (r["recovery"] if pd.notna(r["recovery"]) else result.index.max())]), axis=1)
    return out.sort_values("max_drawdown").head(top_n)


def rolling_performance(result: pd.DataFrame, timeframe: str = "4h", window_bars: int = 180) -> pd.DataFrame:
    if result.empty or "equity" not in result:
        return pd.DataFrame()
    rows = []
    for i in range(window_bars, len(result) + 1):
        chunk = result.iloc[i - window_bars:i]
        summary = performance_summary(chunk, timeframe=timeframe)
        rows.append({"end_time": chunk.index.max(), "window_bars": window_bars, **summary})
    return pd.DataFrame(rows)


def leverage_risk_table(
    base_result: pd.DataFrame,
    timeframe: str = "4h",
    leverages: list[float] | tuple[float, ...] = (1, 2, 3, 5, 10),
    max_margin_fraction: float = 0.30,
    max_notional_fraction: float = 3.0,
) -> pd.DataFrame:
    """Approximate leverage sensitivity using the realized strategy return stream.

    This is a research diagnostic, not an exchange liquidation model. It scales the
    gross pre-cost return relative to the original exposure and caps notional by config.
    """
    if base_result.empty or "asset_return" not in base_result or "position" not in base_result:
        return pd.DataFrame()
    rows = []
    init_equity = float(base_result["equity"].iloc[0]) if "equity" in base_result else 1000.0
    for lev in leverages:
        margin = min(max_margin_fraction, max_notional_fraction / float(lev))
        exposure = base_result["position"].fillna(0).clip(0, 1) * margin * float(lev)
        cost = base_result.get("turnover", pd.Series(0.0, index=base_result.index)).fillna(0) * 0.0
        ret = exposure * base_result["asset_return"].fillna(0) - cost
        equity = init_equity * (1 + ret).cumprod()
        tmp = base_result.copy()
        tmp["equity"] = equity
        tmp["strategy_return"] = ret
        summary = performance_summary(tmp, timeframe=timeframe)
        one_bar_loss_p05 = float(np.nanpercentile(ret, 5)) if len(ret) else 0.0
        one_bar_loss_p01 = float(np.nanpercentile(ret, 1)) if len(ret) else 0.0
        rows.append({
            "leverage": float(lev),
            "effective_max_exposure": float(margin * float(lev)),
            "one_bar_return_p05": one_bar_loss_p05,
            "one_bar_return_p01": one_bar_loss_p01,
            **summary,
        })
    return pd.DataFrame(rows)


def strategy_diagnostic_tables(result: pd.DataFrame, timeframe: str = "4h") -> dict[str, pd.DataFrame]:
    return {
        "annual_performance": period_performance(result, timeframe=timeframe, freq="YE"),
        "monthly_performance": period_performance(result, timeframe=timeframe, freq="ME"),
        "regime_performance": regime_table(result, timeframe=timeframe),
        "drawdown_events": drawdown_event_table(result),
        "rolling_180bar_performance": rolling_performance(result, timeframe=timeframe, window_bars=180),
        "trades": extract_long_trades(result),
    }
