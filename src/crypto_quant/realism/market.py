from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

import numpy as np
import pandas as pd

from crypto_quant.backtest.metrics import performance_summary


@dataclass
class LiquidationRiskConfig:
    maintenance_margin_rate: float = 0.005
    min_liquidation_buffer: float = 0.20
    max_leverage: float = 10.0


def estimate_long_liquidation_price(entry_price: float, leverage: float, maintenance_margin_rate: float = 0.005) -> float:
    """Approximate isolated-margin long liquidation price.

    This is intentionally conservative and not a substitute for the exchange formula. It provides a
    first-order risk warning for research/backtest reporting.
    """
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    return float(entry_price * max(0.0, 1.0 - 1.0 / leverage + maintenance_margin_rate))


def estimate_liquidation_buffer(price: float, leverage: float, maintenance_margin_rate: float = 0.005) -> float:
    liq = estimate_long_liquidation_price(price, leverage, maintenance_margin_rate)
    if price <= 0:
        return 0.0
    return float((price - liq) / price)


def add_liquidation_risk_columns(
    df: pd.DataFrame,
    *,
    price_col: str = "close",
    exposure_col: str = "gross_exposure",
    low_col: str = "low",
    maintenance_margin_rate: float = 0.005,
    min_liquidation_buffer: float = 0.20,
) -> pd.DataFrame:
    out = df.copy()
    if price_col not in out.columns:
        raise ValueError(f"Missing price_col: {price_col}")
    exposure = out[exposure_col].abs() if exposure_col in out.columns else pd.Series(0.0, index=out.index)
    effective_leverage = exposure.clip(lower=0.0)
    # target exposure is not exactly exchange leverage, but it is a useful effective leverage proxy.
    liq_price = pd.Series(np.nan, index=out.index, dtype=float)
    active = effective_leverage > 0
    liq_price.loc[active] = out.loc[active, price_col] * (1.0 - 1.0 / effective_leverage.loc[active].clip(lower=1e-9) + maintenance_margin_rate)
    liq_price = liq_price.clip(lower=0.0)
    out["estimated_liquidation_price"] = liq_price
    out["liquidation_buffer"] = (out[price_col] - out["estimated_liquidation_price"]) / out[price_col]
    out.loc[~active, "liquidation_buffer"] = np.nan
    if low_col in out.columns:
        out["bar_low_breached_estimated_liq"] = ((out[low_col] <= out["estimated_liquidation_price"]) & active).astype(int)
    else:
        out["bar_low_breached_estimated_liq"] = 0
    out["liquidation_buffer_warning"] = ((out["liquidation_buffer"] < min_liquidation_buffer) & active).astype(int)
    return out


def align_funding_to_bars(bar_index: pd.DatetimeIndex, funding: pd.DataFrame) -> pd.Series:
    if funding is None or funding.empty or "funding_rate" not in funding.columns:
        return pd.Series(0.0, index=bar_index, name="funding_rate")
    f = funding.copy().sort_index()
    if not isinstance(f.index, pd.DatetimeIndex):
        f.index = pd.to_datetime(f.index, utc=True)
    elif f.index.tz is None:
        f.index = f.index.tz_localize("UTC")
    else:
        f.index = f.index.tz_convert("UTC")
    target = pd.DataFrame(index=bar_index)
    joined = pd.merge_asof(target.reset_index().rename(columns={"index": "timestamp"}), f[["funding_rate"]].reset_index().rename(columns={f.index.name or "index": "timestamp"}), on="timestamp", direction="backward")
    return pd.Series(joined["funding_rate"].fillna(0.0).values, index=bar_index, name="funding_rate")


def apply_funding_costs(
    result: pd.DataFrame,
    funding: pd.DataFrame | None,
    *,
    exposure_col: str = "gross_exposure",
    equity_col: str = "equity",
    timeframe: str = "4h",
) -> pd.DataFrame:
    """Add funding-cost adjusted return/equity columns to a backtest result.

    Positive funding_rate means longs pay shorts. The cost is approximated as exposure * funding_rate
    on bars where a funding observation is active. This is conservative for low-frequency research.
    """
    out = result.copy().sort_index()
    out["funding_rate"] = align_funding_to_bars(out.index, funding)
    exposure = out.get(exposure_col, pd.Series(0.0, index=out.index)).abs().fillna(0.0)
    position = np.sign(out.get(exposure_col, pd.Series(0.0, index=out.index)).fillna(0.0))
    # Longs pay positive funding; receive negative funding.
    out["funding_return_cost"] = exposure * position.clip(lower=0) * out["funding_rate"].fillna(0.0)
    base_return = out[equity_col].pct_change().fillna(0.0)
    out["strategy_return_after_funding"] = base_return - out["funding_return_cost"]
    equity = [float(out[equity_col].iloc[0])]
    for ret in out["strategy_return_after_funding"].iloc[1:]:
        equity.append(max(0.0, equity[-1] * (1.0 + float(ret))))
    out["equity_after_funding"] = equity
    return out


def build_market_realism_report(
    backtest_result: pd.DataFrame,
    funding: pd.DataFrame | None,
    *,
    timeframe: str = "4h",
    maintenance_margin_rate: float = 0.005,
    min_liquidation_buffer: float = 0.20,
) -> tuple[dict[str, Any], pd.DataFrame]:
    enriched = add_liquidation_risk_columns(
        backtest_result,
        maintenance_margin_rate=maintenance_margin_rate,
        min_liquidation_buffer=min_liquidation_buffer,
    )
    enriched = apply_funding_costs(enriched, funding, timeframe=timeframe)
    base_metrics = performance_summary(backtest_result, timeframe=timeframe)
    funding_result = enriched.copy()
    funding_result["equity"] = funding_result["equity_after_funding"]
    funding_metrics = performance_summary(funding_result, timeframe=timeframe)
    active = enriched["gross_exposure"].abs() > 0 if "gross_exposure" in enriched else pd.Series(False, index=enriched.index)
    report = {
        "timeframe": timeframe,
        "bars": int(len(enriched)),
        "active_bars": int(active.sum()),
        "funding_rows": 0 if funding is None else int(len(funding)),
        "base_final_equity": base_metrics.get("final_equity"),
        "funding_adjusted_final_equity": funding_metrics.get("final_equity"),
        "base_total_return": base_metrics.get("total_return"),
        "funding_adjusted_total_return": funding_metrics.get("total_return"),
        "base_max_drawdown": base_metrics.get("max_drawdown"),
        "funding_adjusted_max_drawdown": funding_metrics.get("max_drawdown"),
        "total_funding_return_cost": float(enriched["funding_return_cost"].sum()),
        "min_liquidation_buffer_observed": float(enriched.loc[active, "liquidation_buffer"].min()) if active.any() else None,
        "liquidation_buffer_warning_bars": int(enriched["liquidation_buffer_warning"].sum()),
        "estimated_liquidation_breach_bars": int(enriched["bar_low_breached_estimated_liq"].sum()),
        "maintenance_margin_rate": float(maintenance_margin_rate),
        "min_liquidation_buffer_threshold": float(min_liquidation_buffer),
        "note": "Liquidation estimates are conservative approximations, not exact exchange formulas.",
    }
    return report, enriched


def save_market_realism_artifacts(report: dict[str, Any], enriched: pd.DataFrame, output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "market_realism_report.json"
    detail_path = out / "market_realism_enriched_result.csv"
    html_path = out / "market_realism_report.html"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    enriched.to_csv(detail_path, encoding="utf-8-sig")
    _write_market_realism_html(report, html_path)
    return {"report": str(report_path), "details": str(detail_path), "html": str(html_path)}


def _write_market_realism_html(report: dict[str, Any], path: Path) -> None:
    rows = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in report.items())
    css = """
    <style>
    body{font-family:Arial,sans-serif;margin:24px;color:#111827}.card{border:1px solid #e5e7eb;border-radius:16px;padding:18px;box-shadow:0 2px 10px rgba(0,0,0,.04)}
    table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #e5e7eb;padding:8px;text-align:left}th{background:#f9fafb}
    </style>
    """
    path.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>Market Realism Report</title>{css}</head><body><h1>Market Realism Report</h1><div class='card'><table>{rows}</table></div></body></html>", encoding="utf-8")
