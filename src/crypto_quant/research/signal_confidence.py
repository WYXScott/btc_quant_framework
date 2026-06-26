from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from crypto_quant.backtest.dynamic_engine import DynamicExposureBacktester
from crypto_quant.backtest.metrics import save_backtest_reports
from crypto_quant.models.calibration import load_calibrated_model, reliability_table
from crypto_quant.reporting.plots import plot_drawdown, plot_equity_curve


@dataclass(frozen=True)
class ConfidencePolicy:
    weak_threshold: float = 0.55
    medium_threshold: float = 0.60
    strong_threshold: float = 0.65
    weak_exposure: float = 0.75
    medium_exposure: float = 1.5
    strong_exposure: float = 2.5
    max_exposure: float = 3.0
    trend_filter: bool = True
    min_expected_return: float = 0.0

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "ConfidencePolicy":
        c = cfg.get("calibration", {}).get("confidence", {})
        return cls(
            weak_threshold=float(c.get("weak_threshold", 0.55)),
            medium_threshold=float(c.get("medium_threshold", 0.60)),
            strong_threshold=float(c.get("strong_threshold", 0.65)),
            weak_exposure=float(c.get("weak_exposure", 0.75)),
            medium_exposure=float(c.get("medium_exposure", 1.5)),
            strong_exposure=float(c.get("strong_exposure", 2.5)),
            max_exposure=float(c.get("max_exposure", cfg.get("trading", {}).get("max_notional_fraction", 3.0))),
            trend_filter=bool(c.get("trend_filter", True)),
            min_expected_return=float(c.get("min_expected_return", 0.0)),
        )


def _trend_ok(df: pd.DataFrame) -> pd.Series:
    if {"close", "ma_24", "ma_120"}.issubset(df.columns):
        return (df["close"] > df["ma_120"]) & (df["ma_24"] > df["ma_120"])
    return pd.Series(True, index=df.index)


def apply_confidence_policy(
    df: pd.DataFrame,
    prob_col: str = "prob_up_calibrated",
    policy: ConfidencePolicy | None = None,
) -> pd.DataFrame:
    policy = policy or ConfidencePolicy()
    out = df.copy().sort_index()
    prob = pd.to_numeric(out[prob_col], errors="coerce").fillna(0.0)
    tier = pd.Series("no_trade", index=out.index, dtype="object")
    exposure = pd.Series(0.0, index=out.index, dtype=float)

    weak = prob >= policy.weak_threshold
    medium = prob >= policy.medium_threshold
    strong = prob >= policy.strong_threshold
    tier.loc[weak] = "weak_long"
    tier.loc[medium] = "medium_long"
    tier.loc[strong] = "strong_long"
    exposure.loc[weak] = policy.weak_exposure
    exposure.loc[medium] = policy.medium_exposure
    exposure.loc[strong] = policy.strong_exposure

    if policy.trend_filter:
        ok = _trend_ok(out)
        tier.loc[~ok] = "blocked_by_trend"
        exposure.loc[~ok] = 0.0

    # Optional guard: for BTC long-only low-frequency strategies, avoid acting on
    # barely-positive signals if future-return bucket research sets a stricter floor.
    if policy.min_expected_return > 0 and "expected_return_estimate" in out.columns:
        ev_ok = out["expected_return_estimate"].fillna(0.0) >= policy.min_expected_return
        tier.loc[~ev_ok & (exposure > 0)] = "blocked_by_ev"
        exposure.loc[~ev_ok] = 0.0

    out["confidence_tier"] = tier
    out["target_exposure_confidence"] = exposure.clip(lower=0.0, upper=policy.max_exposure)
    out["signal"] = (out["target_exposure_confidence"] > 0).astype(int)
    return out


def confidence_tier_report(df: pd.DataFrame, future_return_col: str = "future_return") -> pd.DataFrame:
    if "confidence_tier" not in df:
        raise ValueError("DataFrame must contain confidence_tier. Run apply_confidence_policy first.")
    rows = []
    for tier, chunk in df.groupby("confidence_tier", observed=False):
        row = {
            "confidence_tier": tier,
            "bars": int(len(chunk)),
            "bar_fraction": float(len(chunk) / max(len(df), 1)),
            "mean_probability": float(chunk.get("prob_up_calibrated", pd.Series(dtype=float)).mean()) if "prob_up_calibrated" in chunk else np.nan,
            "mean_target_exposure": float(chunk.get("target_exposure_confidence", pd.Series(dtype=float)).mean()) if "target_exposure_confidence" in chunk else np.nan,
        }
        if "label_up" in chunk:
            row["actual_positive_rate"] = float(chunk["label_up"].mean())
        if future_return_col in chunk:
            row["future_return_mean"] = float(chunk[future_return_col].mean())
            row["future_return_median"] = float(chunk[future_return_col].median())
            row["future_return_p05"] = float(chunk[future_return_col].quantile(0.05))
            row["future_return_p95"] = float(chunk[future_return_col].quantile(0.95))
        rows.append(row)
    return pd.DataFrame(rows).sort_values("confidence_tier")


def add_calibrated_probabilities(
    df: pd.DataFrame,
    calibrated_model_path: str | Path,
) -> pd.DataFrame:
    model = load_calibrated_model(calibrated_model_path)
    out = df.copy()
    out["prob_up_raw"] = model.raw_predict_proba(out[model.feature_columns])
    out["prob_up_calibrated"] = model.predict_calibrated_proba(out[model.feature_columns])
    return out


def run_signal_confidence_analysis(
    dataset: pd.DataFrame,
    calibrated_model_path: str | Path,
    output_dir: str | Path,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = ConfidencePolicy.from_config(cfg)
    df = add_calibrated_probabilities(dataset, calibrated_model_path)
    df = apply_confidence_policy(df, prob_col="prob_up_calibrated", policy=policy)

    confidence_table = confidence_tier_report(df)
    confidence_table.to_csv(out_dir / "confidence_tier_table.csv", index=False, encoding="utf-8-sig")
    reliability = reliability_table(
        df["label_up"],
        df["prob_up_calibrated"].values,
        future_return=df["future_return"] if "future_return" in df else None,
        bins=int(cfg.get("calibration", {}).get("bins", 10)),
    )
    reliability.to_csv(out_dir / "calibrated_reliability_table.csv", index=False, encoding="utf-8-sig")
    df.to_csv(out_dir / "signal_confidence_dataset.csv", encoding="utf-8-sig")

    bt = DynamicExposureBacktester(
        initial_equity=cfg["trading"]["initial_equity"],
        max_notional_fraction=policy.max_exposure,
        fee_rate=cfg["trading"]["fee_rate"],
        slippage_rate=cfg["trading"]["slippage_rate"],
        max_drawdown_stop_fraction=cfg["risk"]["max_drawdown_stop_fraction"],
    )
    result = bt.run(df, exposure_col="target_exposure_confidence")
    summary = save_backtest_reports(result, out_dir, prefix="confidence", timeframe=cfg["data"]["timeframe"])
    plot_equity_curve(result, out_dir / "confidence_equity.png", title="Calibrated Confidence Strategy Equity")
    plot_drawdown(result, out_dir / "confidence_drawdown.png", title="Calibrated Confidence Strategy Drawdown")

    html_rows = confidence_table.to_html(index=False, border=0, classes="table") if not confidence_table.empty else "<p>No confidence table.</p>"
    summary_rows = pd.DataFrame([summary]).to_html(index=False, border=0, classes="table")
    html = f"""<!doctype html>
<html lang='zh-CN'><head><meta charset='utf-8'><title>BTC Signal Confidence Report</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;margin:32px;background:#f7f8fb;color:#111827;}}
.card{{background:white;border-radius:18px;padding:22px;margin-bottom:18px;box-shadow:0 10px 28px rgba(15,23,42,.08);}}
.table{{border-collapse:collapse;width:100%;}} .table th,.table td{{border-bottom:1px solid #e5e7eb;padding:8px;text-align:left;}}
.table th{{background:#111827;color:white;}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
img{{max-width:100%;border-radius:12px;border:1px solid #e5e7eb;}}
</style></head><body>
<div class='card'><h1>BTC V2.5 概率校准与信号可信度报告</h1><p>本报告使用校准概率生成 weak/medium/strong 信号层级，并根据层级映射动态目标敞口；不包含实盘交易。</p></div>
<div class='card'><h2>回测摘要</h2>{summary_rows}</div>
<div class='card'><h2>信号可信度分层</h2>{html_rows}</div>
<div class='grid'><div class='card'><h2>权益曲线</h2><img src='confidence_equity.png'></div><div class='card'><h2>回撤曲线</h2><img src='confidence_drawdown.png'></div></div>
</body></html>"""
    (out_dir / "signal_confidence_report.html").write_text(html, encoding="utf-8")
    return {"summary": summary, "confidence_table_rows": int(len(confidence_table)), "output_dir": str(out_dir)}
