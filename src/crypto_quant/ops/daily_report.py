from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_quant.config import resolve_path
from crypto_quant.reporting.html_report import build_research_html_report


@dataclass
class OperationsConfig:
    output_path: str = "reports/operations"
    paper_db_path: str = "data/database/paper_trading.sqlite"
    admission_leaderboard_path: str = "reports/model_admission/model_strategy_leaderboard.csv"
    admission_snapshot_path: str = "reports/operations/admission_snapshots.csv"
    confidence_dataset_path: str = "reports/walk_forward_calibration/walk_forward_confidence_dataset.csv"
    fallback_confidence_dataset_path: str = "reports/walk_forward_calibration_smoke/walk_forward_confidence_dataset.csv"
    strategy_failure_path: str = "reports/strategy_failure/strategy_failure_status.csv"
    lookback_bars: int = 180
    hit_rate_window_bars: int = 60
    max_table_rows: int = 80


def _ops_cfg(cfg: dict[str, Any] | None = None) -> OperationsConfig:
    raw = (cfg or {}).get("operations", {}) or {}
    return OperationsConfig(**{k: v for k, v in raw.items() if k in OperationsConfig.__dataclass_fields__})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_read_csv(path: str | Path) -> pd.DataFrame:
    p = resolve_path(path)
    if not p.exists() or p.stat().st_size <= 4:
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


def _safe_read_json(path: str | Path) -> dict[str, Any]:
    p = resolve_path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sqlite_table(db_path: str | Path, table: str, limit: int | None = None) -> pd.DataFrame:
    p = resolve_path(db_path)
    if not p.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(p) as conn:
            query = f'SELECT * FROM "{table}"'
            if limit is not None:
                query += f" LIMIT {int(limit)}"
            return pd.read_sql_query(query, conn)
    except Exception:
        return pd.DataFrame()


def _timestamp_col(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    candidates = ["timestamp", "Unnamed: 0", "datetime", "date", "created_at"]
    for c in candidates:
        if c in out.columns:
            ts = pd.to_datetime(out[c], errors="coerce", utc=True)
            if ts.notna().sum() > 0:
                out["_timestamp"] = ts
                return out
    if isinstance(out.index, pd.DatetimeIndex):
        out["_timestamp"] = pd.to_datetime(out.index, utc=True)
    return out


def _drawdown(equity: pd.Series) -> pd.Series:
    eq = pd.to_numeric(equity, errors="coerce").dropna()
    if eq.empty:
        return pd.Series(dtype=float)
    peak = eq.cummax()
    return eq / peak - 1.0


def _float(x: Any, default: float | None = None) -> float | None:
    try:
        if x is None or pd.isna(x):
            return default
        y = float(x)
        if not math.isfinite(y):
            return default
        return y
    except Exception:
        return default


def _pct(x: float | None) -> str:
    if x is None or not math.isfinite(float(x)):
        return "n/a"
    return f"{100*float(x):.2f}%"


def summarize_paper_account(cfg: dict[str, Any] | None = None) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ocfg = _ops_cfg(cfg)
    equity = _timestamp_col(_sqlite_table(ocfg.paper_db_path, "equity_curve"))
    orders = _timestamp_col(_sqlite_table(ocfg.paper_db_path, "orders"))
    target = _timestamp_col(_sqlite_table(ocfg.paper_db_path, "target_exposure_decisions"))

    summary: dict[str, Any] = {
        "paper_db_exists": resolve_path(ocfg.paper_db_path).exists(),
        "equity_rows": int(len(equity)),
        "order_rows": int(len(orders)),
        "target_decision_rows": int(len(target)),
    }
    if not equity.empty and "equity" in equity.columns:
        eq = pd.to_numeric(equity["equity"], errors="coerce")
        latest = eq.dropna().iloc[-1] if eq.dropna().size else None
        first = eq.dropna().iloc[0] if eq.dropna().size else None
        dd = _drawdown(eq)
        summary.update(
            {
                "latest_equity": _float(latest),
                "start_equity": _float(first),
                "total_return": _float(latest / first - 1.0 if first and latest is not None else None),
                "max_drawdown": _float(dd.min() if not dd.empty else None),
                "latest_drawdown": _float(dd.iloc[-1] if not dd.empty else None),
            }
        )
        if "_timestamp" in equity.columns:
            summary["latest_equity_timestamp"] = str(equity["_timestamp"].dropna().iloc[-1]) if equity["_timestamp"].notna().any() else ""
        if "position_qty" in equity.columns:
            summary["latest_position_qty"] = _float(equity["position_qty"].iloc[-1])
        if "price" in equity.columns and "position_qty" in equity.columns and latest:
            notional = abs(_float(equity["position_qty"].iloc[-1], 0.0) or 0.0) * (_float(equity["price"].iloc[-1], 0.0) or 0.0)
            summary["latest_notional"] = notional
            summary["latest_exposure"] = notional / latest if latest else None
    if not orders.empty:
        if "pnl" in orders.columns:
            pnl = pd.to_numeric(orders["pnl"], errors="coerce").dropna()
            summary["realized_pnl_sum"] = _float(pnl.sum())
            summary["winning_order_rate"] = _float((pnl > 0).mean()) if len(pnl) else None
        if "side" in orders.columns:
            summary["last_order_side"] = str(orders["side"].iloc[-1])
        if "status" in orders.columns:
            summary["last_order_status"] = str(orders["status"].iloc[-1])
    if not target.empty:
        for col in ["target_exposure", "ensemble_score", "action", "reason"]:
            if col in target.columns:
                summary[f"latest_{col}"] = target[col].iloc[-1]

    return summary, equity, orders, target


def build_equity_trend(equity: pd.DataFrame, output_dir: Path) -> list[Path]:
    images: list[Path] = []
    if equity.empty or "equity" not in equity.columns:
        return images
    import matplotlib.pyplot as plt

    eq = equity.copy()
    x = eq["_timestamp"] if "_timestamp" in eq.columns else eq.index
    y = pd.to_numeric(eq["equity"], errors="coerce")
    fig = plt.figure(figsize=(10, 4))
    plt.plot(x, y)
    plt.title("Paper Trading Equity Curve")
    plt.xlabel("Time")
    plt.ylabel("Equity")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    out = output_dir / "paper_equity_curve.png"
    fig.savefig(out, dpi=160)
    plt.close(fig)
    images.append(out)

    dd = _drawdown(y)
    if not dd.empty:
        fig = plt.figure(figsize=(10, 4))
        xx = x.iloc[dd.index] if hasattr(x, "iloc") else dd.index
        plt.plot(xx, dd.values)
        plt.title("Paper Trading Drawdown")
        plt.xlabel("Time")
        plt.ylabel("Drawdown")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        out = output_dir / "paper_drawdown.png"
        fig.savefig(out, dpi=160)
        plt.close(fig)
        images.append(out)
    return images


def build_admission_snapshot(cfg: dict[str, Any] | None = None) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    ocfg = _ops_cfg(cfg)
    now = _now_iso()
    leaderboard = _safe_read_csv(ocfg.admission_leaderboard_path)
    if leaderboard.empty:
        leaderboard = _safe_read_csv("reports/model_admission_smoke/model_strategy_leaderboard.csv")
    summary: dict[str, Any] = {"leaderboard_rows": int(len(leaderboard)), "snapshot_time": now}
    if leaderboard.empty:
        return summary, leaderboard, pd.DataFrame()

    decision_col = "admission_decision" if "admission_decision" in leaderboard.columns else "status"
    counts = leaderboard[decision_col].fillna("unknown").value_counts().to_dict()
    for k, v in counts.items():
        summary[f"admission_{k}"] = int(v)
    score_col = "admission_score" if "admission_score" in leaderboard.columns else None
    if score_col:
        summary["top_admission_score"] = _float(pd.to_numeric(leaderboard[score_col], errors="coerce").max())

    snapshot_cols = [c for c in ["candidate_id", "candidate_name", "family", "admission_decision", "admission_score", "blockers", "warnings"] if c in leaderboard.columns]
    snapshot = leaderboard[snapshot_cols].copy() if snapshot_cols else leaderboard.head(0).copy()
    snapshot.insert(0, "snapshot_time", now)

    snap_path = resolve_path(ocfg.admission_snapshot_path)
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    old = _safe_read_csv(snap_path)
    combined = pd.concat([old, snapshot], ignore_index=True) if not old.empty else snapshot
    if not combined.empty:
        combined.to_csv(snap_path, index=False)

    changes = pd.DataFrame()
    if not old.empty and "candidate_id" in old.columns and "candidate_id" in snapshot.columns:
        last_time = old["snapshot_time"].dropna().max() if "snapshot_time" in old.columns else None
        prev = old[old["snapshot_time"] == last_time] if last_time is not None else old.tail(0)
        if not prev.empty and "admission_decision" in prev.columns and "admission_decision" in snapshot.columns:
            merged = snapshot.merge(
                prev[["candidate_id", "admission_decision"]].rename(columns={"admission_decision": "previous_decision"}),
                on="candidate_id",
                how="left",
            )
            changes = merged[merged["admission_decision"] != merged["previous_decision"]].copy()
    return summary, leaderboard, changes


def build_probability_drift(cfg: dict[str, Any] | None = None) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    ocfg = _ops_cfg(cfg)
    pred = _safe_read_csv(ocfg.confidence_dataset_path)
    if pred.empty:
        pred = _safe_read_csv(ocfg.fallback_confidence_dataset_path)
    if pred.empty:
        return {"probability_rows": 0}, pred, pd.DataFrame()

    pred = _timestamp_col(pred)
    prob_col = "prob_up_calibrated" if "prob_up_calibrated" in pred.columns else "prob_up_calibrated_wf"
    if prob_col not in pred.columns:
        prob_col = "prob_up_raw" if "prob_up_raw" in pred.columns else "prob_up_raw_wf"
    if prob_col not in pred.columns:
        return {"probability_rows": int(len(pred)), "probability_column": "missing"}, pred, pd.DataFrame()

    p = pd.to_numeric(pred[prob_col], errors="coerce")
    recent = pred.tail(int(ocfg.lookback_bars))
    rp = pd.to_numeric(recent[prob_col], errors="coerce")
    summary = {
        "probability_rows": int(len(pred)),
        "probability_column": prob_col,
        "probability_mean_all": _float(p.mean()),
        "probability_mean_recent": _float(rp.mean()),
        "probability_std_all": _float(p.std()),
        "probability_std_recent": _float(rp.std()),
        "probability_mean_drift": _float(rp.mean() - p.mean()),
    }
    if "signal" in pred.columns:
        summary["signal_rate_all"] = _float(pd.to_numeric(pred["signal"], errors="coerce").mean())
        summary["signal_rate_recent"] = _float(pd.to_numeric(recent["signal"], errors="coerce").mean())
    if "confidence_tier" in pred.columns:
        summary["latest_confidence_tier"] = str(pred["confidence_tier"].iloc[-1])
        tier_table = recent["confidence_tier"].fillna("unknown").value_counts().rename_axis("confidence_tier").reset_index(name="recent_count")
        all_tiers = pred["confidence_tier"].fillna("unknown").value_counts(normalize=True).rename_axis("confidence_tier").reset_index(name="all_fraction")
        tier_table = tier_table.merge(all_tiers, on="confidence_tier", how="left")
    else:
        tier_table = pd.DataFrame()
    return summary, pred, tier_table


def build_signal_hit_rate(cfg: dict[str, Any] | None = None) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    ocfg = _ops_cfg(cfg)
    pred = _safe_read_csv(ocfg.confidence_dataset_path)
    if pred.empty:
        pred = _safe_read_csv(ocfg.fallback_confidence_dataset_path)
    if pred.empty or "label_up" not in pred.columns:
        return {"hit_rate_rows": 0}, pred, pd.DataFrame()
    pred = _timestamp_col(pred)
    sig_col = "signal" if "signal" in pred.columns else None
    prob_col = "prob_up_calibrated" if "prob_up_calibrated" in pred.columns else "prob_up_calibrated_wf"
    if sig_col is None and prob_col in pred.columns:
        pred["signal"] = (pd.to_numeric(pred[prob_col], errors="coerce") >= 0.55).astype(int)
        sig_col = "signal"
    if sig_col is None:
        return {"hit_rate_rows": int(len(pred)), "signal_column": "missing"}, pred, pd.DataFrame()

    label = pd.to_numeric(pred["label_up"], errors="coerce")
    signal = pd.to_numeric(pred[sig_col], errors="coerce")
    mask = signal == 1
    summary = {
        "hit_rate_rows": int(len(pred)),
        "signal_count": int(mask.sum()),
        "overall_signal_hit_rate": _float(label[mask].mean()) if int(mask.sum()) else None,
        "base_up_rate": _float(label.mean()),
    }
    recent = pred.tail(int(ocfg.hit_rate_window_bars)).copy()
    rlabel = pd.to_numeric(recent["label_up"], errors="coerce")
    rsignal = pd.to_numeric(recent[sig_col], errors="coerce") == 1
    summary["recent_signal_count"] = int(rsignal.sum())
    summary["recent_signal_hit_rate"] = _float(rlabel[rsignal].mean()) if int(rsignal.sum()) else None

    if "confidence_tier" in pred.columns:
        rows = []
        for tier, g in pred.groupby("confidence_tier", dropna=False):
            gs = pd.to_numeric(g[sig_col], errors="coerce") == 1
            gl = pd.to_numeric(g["label_up"], errors="coerce")
            rows.append({
                "confidence_tier": tier,
                "rows": int(len(g)),
                "signals": int(gs.sum()),
                "base_up_rate": _float(gl.mean()),
                "signal_hit_rate": _float(gl[gs].mean()) if int(gs.sum()) else None,
            })
        tier_hit = pd.DataFrame(rows)
    else:
        tier_hit = pd.DataFrame()
    return summary, pred, tier_hit


def build_operations_daily_report(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    ocfg = _ops_cfg(cfg)
    out_dir = resolve_path(ocfg.output_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    paper_summary, equity, orders, target = summarize_paper_account(cfg)
    admission_summary, leaderboard, admission_changes = build_admission_snapshot(cfg)
    prob_summary, pred, tier_table = build_probability_drift(cfg)
    hit_summary, hit_pred, tier_hit = build_signal_hit_rate(cfg)
    failure = _safe_read_csv(ocfg.strategy_failure_path)
    live_gate = _safe_read_json("reports/live_safety/live_gate_report.json")
    shadow = _safe_read_json("reports/shadow_monitor/shadow_drift_report.json")
    data_quality = _safe_read_json("reports/data_quality/data_quality_report.json")

    summary: dict[str, Any] = {
        "generated_at": _now_iso(),
        "report_type": "v3_0_operations_daily_report",
        **{f"paper_{k}": v for k, v in paper_summary.items()},
        **{f"admission_{k}": v for k, v in admission_summary.items()},
        **{f"prob_{k}": v for k, v in prob_summary.items()},
        **{f"hit_{k}": v for k, v in hit_summary.items()},
        "strategy_failure_rows": int(len(failure)),
        "live_gate_status": live_gate.get("status", live_gate.get("decision", "not_generated")) if live_gate else "not_generated",
        "shadow_monitor_status": shadow.get("overall_status", shadow.get("status", "not_generated")) if shadow else "not_generated",
        "data_quality_status": data_quality.get("status", "not_generated") if data_quality else "not_generated",
    }

    # Human-oriented derived status.
    alerts: list[str] = []
    if paper_summary.get("max_drawdown") is not None and abs(float(paper_summary["max_drawdown"])) > 0.15:
        alerts.append(f"Paper max drawdown is high: {_pct(float(paper_summary['max_drawdown']))}.")
    if prob_summary.get("probability_mean_drift") is not None and abs(float(prob_summary["probability_mean_drift"])) > 0.08:
        alerts.append(f"Recent calibrated probability mean drift is notable: {float(prob_summary['probability_mean_drift']):.4f}.")
    if hit_summary.get("recent_signal_count", 0) and hit_summary.get("recent_signal_hit_rate") is not None:
        if float(hit_summary["recent_signal_hit_rate"]) < 0.45:
            alerts.append(f"Recent signal hit rate is weak: {_pct(float(hit_summary['recent_signal_hit_rate']))}.")
    if failure is not None and not failure.empty:
        bad_cols = [c for c in failure.columns if c.lower() in {"status", "failure_status"}]
        if bad_cols:
            bad = failure[failure[bad_cols[0]].astype(str).str.contains("fail|degrad|pause|inactive", case=False, na=False)]
            if not bad.empty:
                alerts.append(f"Strategy failure table contains {len(bad)} degraded/failed rows.")
    summary["alert_count"] = len(alerts)

    # Save component tables.
    if not equity.empty:
        equity.tail(ocfg.max_table_rows).to_csv(out_dir / "daily_equity_tail.csv", index=False)
    if not orders.empty:
        orders.tail(ocfg.max_table_rows).to_csv(out_dir / "daily_orders_tail.csv", index=False)
    if not target.empty:
        target.tail(ocfg.max_table_rows).to_csv(out_dir / "daily_target_exposure_tail.csv", index=False)
    if not leaderboard.empty:
        leaderboard.head(ocfg.max_table_rows).to_csv(out_dir / "daily_admission_leaderboard_top.csv", index=False)
    if not admission_changes.empty:
        admission_changes.to_csv(out_dir / "daily_admission_changes.csv", index=False)
    if not tier_table.empty:
        tier_table.to_csv(out_dir / "daily_confidence_tier_distribution.csv", index=False)
    if not tier_hit.empty:
        tier_hit.to_csv(out_dir / "daily_signal_hit_rate_by_tier.csv", index=False)
    if not failure.empty:
        failure.head(ocfg.max_table_rows).to_csv(out_dir / "daily_strategy_failure_status.csv", index=False)

    (out_dir / "daily_operations_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    pd.DataFrame({"alert": alerts}).to_csv(out_dir / "daily_operations_alerts.csv", index=False)

    images = build_equity_trend(equity, out_dir)
    tables = {
        "paper_orders_tail": orders.tail(20) if not orders.empty else pd.DataFrame(),
        "target_exposure_tail": target.tail(20) if not target.empty else pd.DataFrame(),
        "admission_leaderboard_top": leaderboard.head(20) if not leaderboard.empty else pd.DataFrame(),
        "admission_changes": admission_changes.head(30) if not admission_changes.empty else pd.DataFrame(),
        "confidence_tier_distribution": tier_table,
        "signal_hit_rate_by_tier": tier_hit,
        "strategy_failure_status": failure.head(30) if not failure.empty else pd.DataFrame(),
        "alerts": pd.DataFrame({"alert": alerts}) if alerts else pd.DataFrame(),
    }
    notes = [
        "This is an operations report for research, paper trading, and demo validation only.",
        "No live order execution is enabled by this report.",
        "Admission decisions only determine local paper-trading observation eligibility.",
    ]
    html_path = build_research_html_report(
        out_dir / "daily_operations_report.html",
        title="V3.0 Daily Operations Report",
        summary=summary,
        tables=tables,
        images=images,
        notes=notes,
    )
    summary["html_report"] = str(html_path)
    return summary


def build_v30_operations_report(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the V3.0 overview report from the latest daily report artifacts."""
    ocfg = _ops_cfg(cfg)
    out_dir = resolve_path((cfg or {}).get("v3_0_report", {}).get("output_path", "reports/v3_0_operations_report"))
    out_dir.mkdir(parents=True, exist_ok=True)
    daily = build_operations_daily_report(cfg)
    ops_dir = resolve_path(ocfg.output_path)

    tables = {
        "alerts": _safe_read_csv(ops_dir / "daily_operations_alerts.csv"),
        "admission_leaderboard_top": _safe_read_csv(ops_dir / "daily_admission_leaderboard_top.csv"),
        "signal_hit_rate_by_tier": _safe_read_csv(ops_dir / "daily_signal_hit_rate_by_tier.csv"),
        "confidence_tier_distribution": _safe_read_csv(ops_dir / "daily_confidence_tier_distribution.csv"),
        "target_exposure_tail": _safe_read_csv(ops_dir / "daily_target_exposure_tail.csv"),
    }
    image_paths = [p for p in [ops_dir / "paper_equity_curve.png", ops_dir / "paper_drawdown.png"] if p.exists()]
    for p in image_paths:
        target = out_dir / p.name
        try:
            target.write_bytes(p.read_bytes())
        except Exception:
            pass
    html = build_research_html_report(
        out_dir / "v3_0_operations_report.html",
        title="V3.0 Long-Run Paper Trading Operations Report",
        summary=daily,
        tables=tables,
        images=[out_dir / p.name for p in image_paths],
        notes=[
            "Use this report as a daily operating checklist for paper trading and research validation.",
            "The system remains non-live by default. This report does not authorize real-money trading.",
            "Pay particular attention to drawdown, probability drift, recent hit rate, and admission-pool changes.",
        ],
    )
    payload = {"generated_at": _now_iso(), "daily_summary": daily, "html_report": str(html)}
    (out_dir / "v3_0_operations_summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return payload
