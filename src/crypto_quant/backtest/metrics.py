from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity_curve: pd.Series) -> float:
    running_max = equity_curve.cummax()
    dd = equity_curve / running_max - 1
    return float(dd.min())


def annualization_factor(timeframe: str) -> float:
    if timeframe.endswith("h"):
        hours = int(timeframe[:-1])
        return 365 * 24 / hours
    if timeframe.endswith("d"):
        days = int(timeframe[:-1])
        return 365 / days
    if timeframe.endswith("m"):
        minutes = int(timeframe[:-1])
        return 365 * 24 * 60 / minutes
    return 365.0


def performance_summary(result: pd.DataFrame, timeframe: str = "4h") -> dict[str, float]:
    equity = result["equity"]
    returns = equity.pct_change().dropna()
    ann = annualization_factor(timeframe)
    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    years = max(len(result) / ann, 1e-9)
    cagr = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0
    vol = returns.std() * np.sqrt(ann) if len(returns) > 1 else 0.0
    sharpe = returns.mean() / returns.std() * np.sqrt(ann) if returns.std() > 0 else 0.0
    mdd = max_drawdown(equity)
    calmar = cagr / abs(mdd) if mdd < 0 else 0.0
    trades = int(result["trade_flag"].sum()) if "trade_flag" in result else 0
    return {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annual_volatility": float(vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(mdd),
        "calmar": float(calmar),
        "trades": trades,
        "final_equity": float(equity.iloc[-1]),
    }



def period_performance(result: pd.DataFrame, timeframe: str = "4h", freq: str = "YE") -> pd.DataFrame:
    """Return period-level performance, e.g. yearly or monthly rows.

    freq examples:
        "YE" = year end
        "ME" = month end
    """
    if result.empty:
        return pd.DataFrame()
    rows = []
    for period_end, chunk in result.sort_index().resample(freq):
        if len(chunk) < 2:
            continue
        summary = performance_summary(chunk, timeframe=timeframe)
        rows.append({
            "period": period_end,
            "start": chunk.index.min(),
            "end": chunk.index.max(),
            "bars": len(chunk),
            **summary,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def drawdown_series(equity_curve: pd.Series) -> pd.Series:
    running_max = equity_curve.cummax()
    return equity_curve / running_max - 1.0


def save_backtest_reports(
    result: pd.DataFrame,
    output_dir: str | "Path",
    prefix: str,
    timeframe: str = "4h",
) -> dict[str, object]:
    """Save standard result artifacts and return summary metrics."""
    from pathlib import Path

    from crypto_quant.backtest.trades import extract_long_trades, trade_summary

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        result.to_parquet(out_dir / f"{prefix}_result.parquet")
    except Exception:
        # CSV remains the mandatory portable artifact; parquet is optional and depends on pyarrow/fastparquet.
        pass
    result.to_csv(out_dir / f"{prefix}_result.csv", encoding="utf-8-sig")

    annual = period_performance(result, timeframe=timeframe, freq="YE")
    monthly = period_performance(result, timeframe=timeframe, freq="ME")
    if not annual.empty:
        annual.to_csv(out_dir / f"{prefix}_annual_performance.csv", index=False, encoding="utf-8-sig")
    if not monthly.empty:
        monthly.to_csv(out_dir / f"{prefix}_monthly_performance.csv", index=False, encoding="utf-8-sig")

    trades = extract_long_trades(result)
    trades.to_csv(out_dir / f"{prefix}_trades.csv", index=False, encoding="utf-8-sig")

    summary = performance_summary(result, timeframe=timeframe)
    summary.update(trade_summary(trades))
    pd.DataFrame([summary]).to_csv(out_dir / f"{prefix}_summary.csv", index=False, encoding="utf-8-sig")
    return summary
