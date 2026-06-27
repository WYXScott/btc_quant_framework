from __future__ import annotations

from itertools import product
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import performance_summary, drawdown_series
from crypto_quant.backtest.trades import extract_long_trades, trade_summary
from crypto_quant.strategy.library import build_strategy_signal, get_strategy_spec
from crypto_quant.strategy.ml_strategy import probability_signal


def expand_grid(grid: dict[str, Iterable[Any]]) -> list[dict[str, Any]]:
    """Expand a simple dict-of-lists grid into parameter dictionaries."""
    if not grid:
        return [{}]
    keys = list(grid.keys())
    values = [list(grid[k]) for k in keys]
    rows = []
    for combo in product(*values):
        rows.append({k: v for k, v in zip(keys, combo)})
    return rows


def default_strategy_param_grid(strategy_name: str) -> dict[str, list[Any]]:
    """Conservative BTC 4h parameter grids for rule strategies.

    The grid is intentionally coarse. Fine-grained grids often fit historical noise.
    """
    name = strategy_name.strip().lower()
    if name == "ma_trend":
        return {
            "fast_col": ["ma_12", "ma_24", "ma_48"],
            "slow_col": ["ma_48", "ma_120"],
            "max_vol_ratio": [1.8, 2.5, 3.2],
        }
    if name == "donchian_breakout":
        return {
            "entry_window": [24, 36, 55, 72],
            "exit_window": [12, 20, 36],
            "max_holding_bars": [12, 24, 36],
        }
    if name == "vol_squeeze_breakout":
        return {
            "breakout_window": [24, 36, 55],
            "squeeze_ratio": [0.70, 0.85, 1.00],
            "max_holding_bars": [12, 18, 24],
        }
    if name == "rsi_mean_reversion":
        return {
            "entry_rsi": [25, 30, 35],
            "exit_rsi": [50, 55, 60],
            "trend_filter": [True],
            "max_holding_bars": [6, 12, 18],
        }
    if name == "regime_filtered_trend":
        return {
            "min_trend_ma_24_120": [-0.005, 0.0, 0.005],
            "max_vol_ratio": [1.5, 1.8, 2.2],
            "min_close_position": [0.40, 0.50, 0.60],
        }
    if name == "buy_and_hold":
        return {}
    # Fallback: evaluate the registry default once.
    return {}


def _safe_metric(row: pd.Series | dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = row[key]  # type: ignore[index]
    except Exception:
        return default
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def overfit_risk_score(row: pd.Series | dict[str, Any]) -> float:
    """Heuristic 0-100 score where higher means more overfitting/fragility risk.

    The score penalizes low trade count, severe drawdowns, high parameter rank dependence,
    poor stress-test retention, and unstable segment performance.
    """
    trades = _safe_metric(row, "num_trades", _safe_metric(row, "trades", 0.0))
    max_drawdown = abs(_safe_metric(row, "max_drawdown", 0.0))
    sharpe = _safe_metric(row, "sharpe", 0.0)
    segment_positive_rate = _safe_metric(row, "segment_positive_rate", 0.0)
    worst_segment_return = _safe_metric(row, "worst_segment_return", 0.0)
    stress_retention = _safe_metric(row, "stress_return_retention", 1.0)

    risk = 0.0
    if trades < 5:
        risk += 28.0
    elif trades < 15:
        risk += 14.0
    if max_drawdown > 0.35:
        risk += 25.0
    elif max_drawdown > 0.20:
        risk += 12.0
    if sharpe < 0:
        risk += 18.0
    elif sharpe < 0.5:
        risk += 8.0
    if segment_positive_rate < 0.4:
        risk += 18.0
    elif segment_positive_rate < 0.6:
        risk += 8.0
    if worst_segment_return < -0.25:
        risk += 12.0
    elif worst_segment_return < -0.10:
        risk += 6.0
    if stress_retention < 0.25:
        risk += 15.0
    elif stress_retention < 0.60:
        risk += 7.0
    return float(min(max(risk, 0.0), 100.0))


def robust_rank_score(row: pd.Series | dict[str, Any]) -> float:
    """Higher-is-better candidate score for research ranking."""
    calmar = _safe_metric(row, "calmar", 0.0)
    sharpe = _safe_metric(row, "sharpe", 0.0)
    max_drawdown = abs(_safe_metric(row, "max_drawdown", 0.0))
    trades = _safe_metric(row, "num_trades", _safe_metric(row, "trades", 0.0))
    segment_rate = _safe_metric(row, "segment_positive_rate", 0.0)
    stress_retention = _safe_metric(row, "stress_return_retention", 1.0)
    risk = overfit_risk_score(row)
    trade_bonus = min(trades / 30.0, 1.0)
    score = (
        1.8 * calmar
        + 0.8 * sharpe
        + 0.8 * segment_rate
        + 0.5 * stress_retention
        + 0.3 * trade_bonus
        - 1.6 * max_drawdown
        - 0.025 * risk
    )
    return float(score)


def chronological_segment_performance(
    result: pd.DataFrame,
    timeframe: str = "4h",
    n_segments: int = 6,
) -> pd.DataFrame:
    """Split a result into equal chronological segments and summarize each segment."""
    if result.empty:
        return pd.DataFrame()
    n = len(result)
    n_segments = int(max(1, min(n_segments, n)))
    rows: list[dict[str, Any]] = []
    for seg_id, positions in enumerate(np.array_split(np.arange(n), n_segments)):
        if len(positions) < 2:
            continue
        chunk = result.iloc[positions].copy()
        summary = performance_summary(chunk, timeframe=timeframe)
        rows.append({
            "segment_id": seg_id,
            "start": chunk.index.min(),
            "end": chunk.index.max(),
            "bars": len(chunk),
            **summary,
        })
    return pd.DataFrame(rows)


def segment_stability_metrics(segment_table: pd.DataFrame) -> dict[str, float]:
    if segment_table.empty or "total_return" not in segment_table:
        return {
            "segment_count": 0.0,
            "segment_positive_rate": 0.0,
            "median_segment_return": 0.0,
            "worst_segment_return": 0.0,
            "segment_return_std": 0.0,
        }
    returns = segment_table["total_return"].astype(float)
    return {
        "segment_count": float(len(segment_table)),
        "segment_positive_rate": float((returns > 0).mean()),
        "median_segment_return": float(returns.median()),
        "worst_segment_return": float(returns.min()),
        "segment_return_std": float(returns.std(ddof=0) if len(returns) > 1 else 0.0),
    }


def add_market_regime_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add coarse bull/bear/sideways and volatility regime labels from K-line features."""
    out = df.copy()
    trend = out.get("trend_ma_24_120")
    if trend is None:
        ma24 = out["close"].rolling(24).mean()
        ma120 = out["close"].rolling(120).mean()
        trend = ma24 / ma120 - 1
    vol_ratio = out.get("vol_ratio_24_120")
    if vol_ratio is None:
        vol_ratio = out["close"].pct_change().rolling(24).std() / out["close"].pct_change().rolling(120).std()
    out["trend_regime"] = np.select(
        [trend > 0.01, trend < -0.01],
        ["bull", "bear"],
        default="sideways",
    )
    out["vol_regime"] = np.select(
        [vol_ratio > 1.2, vol_ratio < 0.8],
        ["high_vol", "low_vol"],
        default="normal_vol",
    )
    out["market_regime"] = out["trend_regime"].astype(str) + "_" + out["vol_regime"].astype(str)
    return out


def regime_performance_table(
    result: pd.DataFrame,
    feature_df: pd.DataFrame,
    timeframe: str = "4h",
) -> pd.DataFrame:
    if result.empty:
        return pd.DataFrame()
    regimes = add_market_regime_columns(feature_df)
    joined = result.copy().join(regimes[["trend_regime", "vol_regime", "market_regime"]], how="left")
    rows: list[dict[str, Any]] = []
    for regime, chunk in joined.groupby("market_regime", dropna=True):
        if len(chunk) < 3:
            continue
        summary = performance_summary(chunk, timeframe=timeframe)
        rows.append({
            "market_regime": regime,
            "bars": len(chunk),
            "exposure_mean": float(chunk.get("position", pd.Series(dtype=float)).mean()),
            **summary,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["total_return", "sharpe"], ascending=[False, False])


def run_single_strategy_backtest(
    dataset: pd.DataFrame,
    strategy_name: str,
    params: dict[str, Any],
    timeframe: str,
    initial_equity: float,
    leverage: float,
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    signal_df = build_strategy_signal(dataset, strategy_name, params=params)
    bt = LeveragedBacktester(
        initial_equity=initial_equity,
        leverage=leverage,
        max_margin_fraction=max_margin_fraction,
        max_notional_fraction=max_notional_fraction,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        max_drawdown_stop_fraction=max_drawdown_stop_fraction,
    )
    result = bt.run(signal_df, signal_col="signal")
    trades = extract_long_trades(result)
    summary = performance_summary(result, timeframe=timeframe)
    summary.update(trade_summary(trades))
    return signal_df, result, summary


def cost_slippage_stress_for_signal(
    signal_df: pd.DataFrame,
    timeframe: str,
    initial_equity: float,
    leverage: float,
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rates: Iterable[float],
    slippage_rates: Iterable[float],
    max_drawdown_stop_fraction: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for fee, slip in product(fee_rates, slippage_rates):
        bt = LeveragedBacktester(
            initial_equity=initial_equity,
            leverage=leverage,
            max_margin_fraction=max_margin_fraction,
            max_notional_fraction=max_notional_fraction,
            fee_rate=float(fee),
            slippage_rate=float(slip),
            max_drawdown_stop_fraction=max_drawdown_stop_fraction,
        )
        result = bt.run(signal_df, signal_col="signal")
        summary = performance_summary(result, timeframe=timeframe)
        summary.update(trade_summary(extract_long_trades(result)))
        rows.append({"fee_rate": float(fee), "slippage_rate": float(slip), **summary})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    base_return = float(out.iloc[0]["total_return"])
    out["return_retention_vs_first"] = out["total_return"].apply(
        lambda x: float(x / base_return) if abs(base_return) > 1e-12 else 0.0
    )
    return out.sort_values(["fee_rate", "slippage_rate"])


def leverage_boundary_for_signal(
    signal_df: pd.DataFrame,
    timeframe: str,
    initial_equity: float,
    leverages: Iterable[float],
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for lev in leverages:
        bt = LeveragedBacktester(
            initial_equity=initial_equity,
            leverage=float(lev),
            max_margin_fraction=max_margin_fraction,
            max_notional_fraction=max_notional_fraction,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            max_drawdown_stop_fraction=max_drawdown_stop_fraction,
        )
        result = bt.run(signal_df, signal_col="signal")
        summary = performance_summary(result, timeframe=timeframe)
        rows.append({"leverage": float(lev), **summary})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("leverage")
    return out


def strategy_parameter_search(
    dataset: pd.DataFrame,
    strategy_names: Iterable[str],
    output_dir: str | Path,
    timeframe: str,
    initial_equity: float,
    leverage: float,
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
    n_segments: int = 6,
    max_candidates_per_strategy: int | None = None,
) -> pd.DataFrame:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for strategy_name in strategy_names:
        spec = get_strategy_spec(strategy_name)
        grid = default_strategy_param_grid(strategy_name)
        candidates = expand_grid(grid)
        if max_candidates_per_strategy is not None:
            candidates = candidates[: int(max_candidates_per_strategy)]
        strategy_dir = out_dir / spec.name
        strategy_dir.mkdir(parents=True, exist_ok=True)

        for candidate_id, params in enumerate(candidates):
            try:
                signal_df, result, summary = run_single_strategy_backtest(
                    dataset=dataset,
                    strategy_name=strategy_name,
                    params=params,
                    timeframe=timeframe,
                    initial_equity=initial_equity,
                    leverage=leverage,
                    max_margin_fraction=max_margin_fraction,
                    max_notional_fraction=max_notional_fraction,
                    fee_rate=fee_rate,
                    slippage_rate=slippage_rate,
                    max_drawdown_stop_fraction=max_drawdown_stop_fraction,
                )
                segments = chronological_segment_performance(result, timeframe=timeframe, n_segments=n_segments)
                seg_metrics = segment_stability_metrics(segments)
                row = {
                    "strategy": spec.name,
                    "candidate_id": candidate_id,
                    "params": params,
                    "description": spec.description,
                    "leverage": leverage,
                    **summary,
                    **seg_metrics,
                }
                row["overfit_risk_score"] = overfit_risk_score(row)
                row["robust_rank_score"] = robust_rank_score(row)
                rows.append(row)

                candidate_prefix = f"{spec.name}_{candidate_id:04d}"
                # Persist only compact artifacts to keep the package/runtime manageable.
                segments.to_csv(strategy_dir / f"{candidate_prefix}_segments.csv", index=False, encoding="utf-8-sig")
            except Exception as exc:
                rows.append({
                    "strategy": spec.name,
                    "candidate_id": candidate_id,
                    "params": params,
                    "error": str(exc),
                    "robust_rank_score": -999.0,
                    "overfit_risk_score": 100.0,
                })

    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(["robust_rank_score", "calmar", "sharpe"], ascending=[False, False, False])
    table.to_csv(out_dir / "strategy_parameter_search_summary.csv", index=False, encoding="utf-8-sig")
    return table


def evaluate_top_candidate_robustness(
    dataset: pd.DataFrame,
    candidate: pd.Series | dict[str, Any],
    output_dir: str | Path,
    timeframe: str,
    initial_equity: float,
    leverage: float,
    leverages: Iterable[float],
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rate: float,
    slippage_rate: float,
    fee_multipliers: Iterable[float],
    slippage_multipliers: Iterable[float],
    max_drawdown_stop_fraction: float,
    n_segments: int = 6,
) -> dict[str, pd.DataFrame]:
    """Create detailed robustness tables for one chosen candidate."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    strategy_name = str(candidate["strategy"] if isinstance(candidate, pd.Series) else candidate["strategy"])
    params_raw = candidate["params"] if isinstance(candidate, pd.Series) else candidate["params"]
    params = params_raw if isinstance(params_raw, dict) else {}

    signal_df, result, summary = run_single_strategy_backtest(
        dataset=dataset,
        strategy_name=strategy_name,
        params=params,
        timeframe=timeframe,
        initial_equity=initial_equity,
        leverage=leverage,
        max_margin_fraction=max_margin_fraction,
        max_notional_fraction=max_notional_fraction,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        max_drawdown_stop_fraction=max_drawdown_stop_fraction,
    )
    signal_df.to_csv(out_dir / "top_candidate_signal.csv", encoding="utf-8-sig")
    result.to_csv(out_dir / "top_candidate_result.csv", encoding="utf-8-sig")

    segment_table = chronological_segment_performance(result, timeframe=timeframe, n_segments=n_segments)
    regime_table = regime_performance_table(result, dataset, timeframe=timeframe)
    fee_rates = [fee_rate * float(m) for m in fee_multipliers]
    slip_rates = [slippage_rate * float(m) for m in slippage_multipliers]
    stress_table = cost_slippage_stress_for_signal(
        signal_df,
        timeframe=timeframe,
        initial_equity=initial_equity,
        leverage=leverage,
        max_margin_fraction=max_margin_fraction,
        max_notional_fraction=max_notional_fraction,
        fee_rates=fee_rates,
        slippage_rates=slip_rates,
        max_drawdown_stop_fraction=max_drawdown_stop_fraction,
    )
    lev_table = leverage_boundary_for_signal(
        signal_df,
        timeframe=timeframe,
        initial_equity=initial_equity,
        leverages=leverages,
        max_margin_fraction=max_margin_fraction,
        max_notional_fraction=max_notional_fraction,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        max_drawdown_stop_fraction=max_drawdown_stop_fraction,
    )
    drawdown = drawdown_series(result["equity"]).rename("drawdown").to_frame()

    tables = {
        "summary": pd.DataFrame([{**summary, "strategy": strategy_name, "params": params}]),
        "segments": segment_table,
        "regimes": regime_table,
        "cost_slippage_stress": stress_table,
        "leverage_boundary": lev_table,
        "drawdown_series": drawdown,
    }
    for name, table in tables.items():
        table.to_csv(out_dir / f"{name}.csv", index=(name == "drawdown_series"), encoding="utf-8-sig")
    return tables


def ml_walk_forward_threshold_grid(
    pred_df: pd.DataFrame,
    output_dir: str | Path,
    timeframe: str,
    initial_equity: float,
    leverage: float,
    max_margin_fraction: float,
    max_notional_fraction: float,
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
    prob_col: str,
    buy_thresholds: Iterable[float],
    exit_thresholds: Iterable[float],
    trend_filter_values: Iterable[bool],
    max_holding_values: Iterable[int | None],
    n_segments: int = 6,
) -> pd.DataFrame:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for buy_th, exit_th, trend_filter, max_hold in product(buy_thresholds, exit_thresholds, trend_filter_values, max_holding_values):
        if float(exit_th) >= float(buy_th):
            continue
        signal_df = probability_signal(
            pred_df,
            prob_col=prob_col,
            buy_threshold=float(buy_th),
            exit_threshold=float(exit_th),
            trend_filter=bool(trend_filter),
            max_holding_bars=max_hold,
        )
        bt = LeveragedBacktester(
            initial_equity=initial_equity,
            leverage=leverage,
            max_margin_fraction=max_margin_fraction,
            max_notional_fraction=max_notional_fraction,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            max_drawdown_stop_fraction=max_drawdown_stop_fraction,
        )
        result = bt.run(signal_df, signal_col="signal")
        summary = performance_summary(result, timeframe=timeframe)
        summary.update(trade_summary(extract_long_trades(result)))
        segments = chronological_segment_performance(result, timeframe=timeframe, n_segments=n_segments)
        row = {
            "buy_threshold": float(buy_th),
            "exit_threshold": float(exit_th),
            "trend_filter": bool(trend_filter),
            "max_holding_bars": max_hold,
            "leverage": leverage,
            **summary,
            **segment_stability_metrics(segments),
        }
        row["overfit_risk_score"] = overfit_risk_score(row)
        row["robust_rank_score"] = robust_rank_score(row)
        rows.append(row)
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(["robust_rank_score", "calmar", "sharpe"], ascending=[False, False, False])
    table.to_csv(out_dir / "ml_threshold_grid_summary.csv", index=False, encoding="utf-8-sig")
    return table
