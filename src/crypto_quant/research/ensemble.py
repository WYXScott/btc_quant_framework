from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from crypto_quant.backtest.dynamic_engine import DynamicExposureBacktester, realized_volatility
from crypto_quant.backtest.metrics import performance_summary, drawdown_series
from crypto_quant.backtest.trades import extract_long_trades, trade_summary
from crypto_quant.backtest.metrics import annualization_factor
from crypto_quant.research.robustness import add_market_regime_columns, chronological_segment_performance, segment_stability_metrics
from crypto_quant.strategy.library import build_strategy_signal


@dataclass(frozen=True)
class EnsembleCandidate:
    """A rule-strategy candidate selected from the V1.3 robustness table."""

    name: str
    params: dict[str, Any]
    weight: float = 1.0
    source_rank: int | None = None
    robust_rank_score: float | None = None
    overfit_risk_score: float | None = None


def parse_params(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def load_candidate_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Candidate table not found: {path}. Run scripts/run_strategy_parameter_search.py first.")
    table = pd.read_csv(path)
    if "params" in table.columns:
        table["params"] = table["params"].apply(parse_params)
    if "error" in table.columns:
        table = table[table["error"].isna() | (table["error"].astype(str).str.len() == 0)].copy()
    return table


def select_top_candidates(
    candidate_table: pd.DataFrame,
    top_n: int = 5,
    min_trades: int = 5,
    max_overfit_risk: float = 80.0,
) -> list[EnsembleCandidate]:
    if candidate_table.empty:
        raise ValueError("candidate_table is empty")
    table = candidate_table.copy()
    if "num_trades" not in table.columns and "trades" in table.columns:
        table["num_trades"] = table["trades"]
    if "num_trades" in table.columns:
        table = table[pd.to_numeric(table["num_trades"], errors="coerce").fillna(0) >= int(min_trades)]
    if "overfit_risk_score" in table.columns:
        table = table[pd.to_numeric(table["overfit_risk_score"], errors="coerce").fillna(100) <= float(max_overfit_risk)]
    if table.empty:
        # Fall back to the best available rows, but still keep it explicit in the source_rank metadata.
        table = candidate_table.copy()
    sort_cols = [c for c in ["robust_rank_score", "calmar", "sharpe"] if c in table.columns]
    if sort_cols:
        table = table.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    rows = table.head(int(top_n)).reset_index(drop=True)
    candidates: list[EnsembleCandidate] = []
    for rank, row in rows.iterrows():
        strategy = str(row.get("strategy", row.get("name", ""))).strip()
        if not strategy:
            continue
        robust_score = _safe_float(row.get("robust_rank_score"), default=0.0)
        overfit_score = _safe_float(row.get("overfit_risk_score"), default=50.0)
        # Convert score/risk to a positive weight. This is deliberately conservative.
        raw_weight = max(0.10, 1.0 + robust_score) * max(0.10, 1.0 - overfit_score / 120.0)
        candidates.append(
            EnsembleCandidate(
                name=strategy,
                params=parse_params(row.get("params", {})),
                weight=float(raw_weight),
                source_rank=rank + 1,
                robust_rank_score=robust_score,
                overfit_risk_score=overfit_score,
            )
        )
    if not candidates:
        raise ValueError("No valid strategy candidates could be selected")
    return normalize_candidate_weights(candidates)


def normalize_candidate_weights(candidates: Iterable[EnsembleCandidate]) -> list[EnsembleCandidate]:
    items = list(candidates)
    total = sum(max(c.weight, 0.0) for c in items)
    if total <= 0:
        total = float(len(items))
        return [EnsembleCandidate(c.name, c.params, 1.0 / total, c.source_rank, c.robust_rank_score, c.overfit_risk_score) for c in items]
    return [EnsembleCandidate(c.name, c.params, max(c.weight, 0.0) / total, c.source_rank, c.robust_rank_score, c.overfit_risk_score) for c in items]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def build_ensemble_signal_table(
    dataset: pd.DataFrame,
    candidates: Iterable[EnsembleCandidate],
    vote_threshold: float = 0.50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build candidate signals and aggregate them into weighted-vote ensemble columns."""
    data = dataset.copy().sort_index()
    candidates = list(candidates)
    meta_rows: list[dict[str, Any]] = []
    signal_cols: list[str] = []
    weighted_score = pd.Series(0.0, index=data.index)
    total_weight = 0.0

    for i, cand in enumerate(candidates):
        signal_df = build_strategy_signal(data, cand.name, params=cand.params)
        col = f"signal_{i+1:02d}_{cand.name}"
        data[col] = pd.to_numeric(signal_df["signal"], errors="coerce").fillna(0).clip(0, 1)
        signal_cols.append(col)
        weighted_score += data[col] * float(cand.weight)
        total_weight += float(cand.weight)
        meta_rows.append(
            {
                "candidate_id": i + 1,
                "strategy": cand.name,
                "weight": cand.weight,
                "source_rank": cand.source_rank,
                "robust_rank_score": cand.robust_rank_score,
                "overfit_risk_score": cand.overfit_risk_score,
                "params": cand.params,
                "signal_col": col,
                "active_rate": float(data[col].mean()),
            }
        )

    if total_weight <= 0:
        total_weight = 1.0
    data["ensemble_score"] = (weighted_score / total_weight).clip(0.0, 1.0)
    data["signal"] = (data["ensemble_score"] >= float(vote_threshold)).astype(int)
    data["candidate_active_count"] = data[signal_cols].sum(axis=1) if signal_cols else 0
    data["candidate_active_fraction"] = data["candidate_active_count"] / max(len(signal_cols), 1)
    data["signal_reason"] = np.where(data["signal"] == 1, "ensemble_vote_on", "ensemble_vote_off")
    return data, pd.DataFrame(meta_rows)


def apply_strategy_failure_filter(
    signal_table: pd.DataFrame,
    candidate_meta: pd.DataFrame,
    lookback_bars: int = 90,
    min_recent_return: float = -0.08,
    max_recent_drawdown: float = -0.12,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Detect weak candidates from their own recent exposure and produce disabled flags.

    This function does not rewrite historical candidate weights. It creates diagnostic columns
    so the user can decide whether to use dynamic disabling in later live/demo logic.
    """
    out = signal_table.copy()
    rows: list[dict[str, Any]] = []
    asset_ret = out["close"].pct_change().fillna(0.0)
    for _, meta in candidate_meta.iterrows():
        col = str(meta["signal_col"])
        if col not in out.columns:
            continue
        pos = out[col].shift(1).fillna(0.0)
        candidate_curve = (1.0 + pos * asset_ret).cumprod()
        recent = candidate_curve.iloc[-int(lookback_bars):] if len(candidate_curve) >= int(lookback_bars) else candidate_curve
        recent_return = float(recent.iloc[-1] / recent.iloc[0] - 1.0) if len(recent) > 1 and recent.iloc[0] != 0 else 0.0
        dd = drawdown_series(recent).min() if len(recent) > 1 else 0.0
        disabled = bool(recent_return <= float(min_recent_return) or dd <= float(max_recent_drawdown))
        rows.append(
            {
                "candidate_id": int(meta["candidate_id"]),
                "strategy": meta["strategy"],
                "signal_col": col,
                "lookback_bars": int(lookback_bars),
                "recent_return": recent_return,
                "recent_max_drawdown": float(dd),
                "disabled_by_failure_filter": disabled,
            }
        )
    return out, pd.DataFrame(rows)


def build_dynamic_exposure(
    signal_table: pd.DataFrame,
    timeframe: str = "4h",
    base_leverage: float = 3.0,
    max_exposure: float = 3.0,
    min_exposure: float = 0.0,
    score_exposure_power: float = 1.0,
    vol_target_annual: float = 0.45,
    vol_window_bars: int = 42,
    min_vol_multiplier: float = 0.35,
    max_vol_multiplier: float = 1.35,
    regime_adjustment: bool = True,
) -> pd.DataFrame:
    """Create target exposure from ensemble signal score, realized volatility, and regimes."""
    out = signal_table.copy().sort_index()
    ann = annualization_factor(timeframe)
    realized_vol = realized_volatility(out["close"], int(vol_window_bars), ann).replace([np.inf, -np.inf], np.nan)
    out["realized_vol_annual"] = realized_vol
    vol_mult = (float(vol_target_annual) / realized_vol).replace([np.inf, -np.inf], np.nan)
    vol_mult = vol_mult.fillna(1.0).clip(float(min_vol_multiplier), float(max_vol_multiplier))
    out["volatility_multiplier"] = vol_mult

    score = out.get("ensemble_score", out.get("signal", pd.Series(0.0, index=out.index))).astype(float).clip(0.0, 1.0)
    score_mult = score.pow(float(score_exposure_power)).clip(0.0, 1.0)
    out["score_multiplier"] = score_mult

    if regime_adjustment:
        reg = add_market_regime_columns(out)
        out["trend_regime"] = reg["trend_regime"]
        out["vol_regime"] = reg["vol_regime"]
        trend_mult = np.select(
            [out["trend_regime"].eq("bull"), out["trend_regime"].eq("sideways"), out["trend_regime"].eq("bear")],
            [1.10, 0.75, 0.35],
            default=0.75,
        )
        vol_regime_mult = np.select(
            [out["vol_regime"].eq("high_vol"), out["vol_regime"].eq("normal_vol"), out["vol_regime"].eq("low_vol")],
            [0.65, 1.00, 1.10],
            default=1.0,
        )
        regime_mult = pd.Series(trend_mult * vol_regime_mult, index=out.index).astype(float)
    else:
        regime_mult = pd.Series(1.0, index=out.index)
    out["regime_multiplier"] = regime_mult

    base_exposure = float(base_leverage)
    raw_exposure = out["signal"].astype(float) * base_exposure * score_mult * out["volatility_multiplier"] * out["regime_multiplier"]
    out["target_exposure_raw"] = raw_exposure
    out["target_exposure"] = raw_exposure.clip(float(min_exposure), float(max_exposure))
    out["effective_leverage"] = out["target_exposure"]
    return out


def run_ensemble_backtest(
    dataset: pd.DataFrame,
    candidates: Iterable[EnsembleCandidate],
    output_dir: str | Path,
    timeframe: str,
    initial_equity: float,
    base_leverage: float,
    max_exposure: float,
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
    vote_threshold: float = 0.50,
    vol_target_annual: float = 0.45,
    vol_window_bars: int = 42,
    regime_adjustment: bool = True,
) -> dict[str, pd.DataFrame | dict[str, Any]]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    signal_table, candidate_meta = build_ensemble_signal_table(dataset, candidates, vote_threshold=vote_threshold)
    exposure_table = build_dynamic_exposure(
        signal_table,
        timeframe=timeframe,
        base_leverage=base_leverage,
        max_exposure=max_exposure,
        vol_target_annual=vol_target_annual,
        vol_window_bars=vol_window_bars,
        regime_adjustment=regime_adjustment,
    )
    bt = DynamicExposureBacktester(
        initial_equity=initial_equity,
        max_notional_fraction=max_exposure,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        max_drawdown_stop_fraction=max_drawdown_stop_fraction,
    )
    result = bt.run(exposure_table, exposure_col="target_exposure")
    summary = performance_summary(result, timeframe=timeframe)
    trades = extract_long_trades(result)
    summary.update(trade_summary(trades))
    segments = chronological_segment_performance(result, timeframe=timeframe, n_segments=6)
    summary.update(segment_stability_metrics(segments))
    failure_signal_table, failure_table = apply_strategy_failure_filter(exposure_table, candidate_meta)

    exposure_table.to_csv(out_dir / "ensemble_signal_exposure.csv", encoding="utf-8-sig")
    candidate_meta.to_csv(out_dir / "ensemble_candidates.csv", index=False, encoding="utf-8-sig")
    result.to_csv(out_dir / "ensemble_dynamic_backtest_result.csv", encoding="utf-8-sig")
    trades.to_csv(out_dir / "ensemble_trades.csv", index=False, encoding="utf-8-sig")
    segments.to_csv(out_dir / "ensemble_segments.csv", index=False, encoding="utf-8-sig")
    failure_table.to_csv(out_dir / "strategy_failure_status.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame([summary]).to_csv(out_dir / "ensemble_summary.csv", index=False, encoding="utf-8-sig")

    return {
        "signal_table": exposure_table,
        "candidate_meta": candidate_meta,
        "result": result,
        "trades": trades,
        "segments": segments,
        "failure_status": failure_table,
        "summary": summary,
    }


def dynamic_position_grid(
    signal_table: pd.DataFrame,
    output_dir: str | Path,
    timeframe: str,
    initial_equity: float,
    base_leverages: Iterable[float],
    max_exposures: Iterable[float],
    vol_targets: Iterable[float],
    vol_windows: Iterable[int],
    fee_rate: float,
    slippage_rate: float,
    max_drawdown_stop_fraction: float,
) -> pd.DataFrame:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for base_lev in base_leverages:
        for max_exp in max_exposures:
            for vol_target in vol_targets:
                for vol_window in vol_windows:
                    exposure_table = build_dynamic_exposure(
                        signal_table,
                        timeframe=timeframe,
                        base_leverage=float(base_lev),
                        max_exposure=float(max_exp),
                        vol_target_annual=float(vol_target),
                        vol_window_bars=int(vol_window),
                        regime_adjustment=True,
                    )
                    bt = DynamicExposureBacktester(
                        initial_equity=initial_equity,
                        max_notional_fraction=float(max_exp),
                        fee_rate=fee_rate,
                        slippage_rate=slippage_rate,
                        max_drawdown_stop_fraction=max_drawdown_stop_fraction,
                    )
                    result = bt.run(exposure_table, exposure_col="target_exposure")
                    summary = performance_summary(result, timeframe=timeframe)
                    summary.update(trade_summary(extract_long_trades(result)))
                    rows.append(
                        {
                            "base_leverage": float(base_lev),
                            "max_exposure": float(max_exp),
                            "vol_target_annual": float(vol_target),
                            "vol_window_bars": int(vol_window),
                            "avg_exposure": float(result["gross_exposure"].mean()),
                            "max_realized_exposure": float(result["gross_exposure"].max()),
                            **summary,
                        }
                    )
    table = pd.DataFrame(rows)
    if not table.empty:
        table["risk_adjusted_rank"] = (
            table.get("calmar", 0.0).astype(float) * 1.4
            + table.get("sharpe", 0.0).astype(float) * 0.7
            - table.get("max_drawdown", 0.0).abs().astype(float) * 1.5
        )
        table = table.sort_values(["risk_adjusted_rank", "calmar", "sharpe"], ascending=[False, False, False])
    table.to_csv(out_dir / "dynamic_position_grid.csv", index=False, encoding="utf-8-sig")
    return table


def build_ensemble_report(
    output_path: str | Path,
    ensemble_dir: str | Path,
    grid_dir: str | Path | None = None,
) -> Path:
    from crypto_quant.reporting.html_report import build_research_html_report

    ensemble_dir = Path(ensemble_dir)
    grid_dir = Path(grid_dir) if grid_dir is not None else None
    tables: dict[str, pd.DataFrame] = {}
    summary: dict[str, Any] = {}
    for name, filename in {
        "ensemble_summary": "ensemble_summary.csv",
        "ensemble_candidates": "ensemble_candidates.csv",
        "strategy_failure_status": "strategy_failure_status.csv",
        "ensemble_segments": "ensemble_segments.csv",
        "ensemble_trades": "ensemble_trades.csv",
    }.items():
        path = ensemble_dir / filename
        if path.exists():
            tables[name] = pd.read_csv(path)
    if "ensemble_summary" in tables and not tables["ensemble_summary"].empty:
        summary = tables["ensemble_summary"].iloc[0].to_dict()
    if grid_dir is not None:
        path = grid_dir / "dynamic_position_grid.csv"
        if path.exists():
            tables["dynamic_position_grid"] = pd.read_csv(path)
    notes = [
        "V1.4 uses weighted strategy voting and dynamic exposure, not direct live execution.",
        "target_exposure is clipped by max_exposure; it should be treated as notional exposure relative to equity.",
        "The strategy-failure table is diagnostic; it does not automatically shut down live trading.",
    ]
    return build_research_html_report(
        output_path=output_path,
        title="BTC Quant Framework V1.4 Ensemble and Dynamic Positioning Report",
        summary=summary,
        tables=tables,
        notes=notes,
    )
