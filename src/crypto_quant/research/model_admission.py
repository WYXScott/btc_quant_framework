from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from crypto_quant.config import resolve_path
from crypto_quant.reporting.html_report import build_research_html_report


@dataclass
class AdmissionPolicy:
    """Conservative research-stage model/strategy admission thresholds.

    These thresholds do not authorize live trading. They only decide whether a
    candidate is good enough to enter local paper-trading observation.
    """

    min_auc: float = 0.52
    min_calibrated_auc: float = 0.52
    max_brier: float = 0.255
    max_ece: float = 0.12
    min_sharpe: float = 0.20
    min_calmar: float = 0.10
    max_drawdown_abs: float = 0.35
    min_trades: int = 8
    min_folds: int = 3
    max_overfit_risk_score: float = 0.65
    min_segment_positive_rate: float = 0.45
    paper_score_threshold: float = 60.0
    watch_score_threshold: float = 42.0
    reject_score_threshold: float = 20.0


def _to_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int | None = None) -> int | None:
    v = _to_float(value, None)
    if v is None or not math.isfinite(v):
        return default
    return int(v)


def _first(row: pd.Series | dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        if name in row:
            val = row[name]
            try:
                if pd.isna(val):
                    continue
            except Exception:
                pass
            return val
    return default


def _safe_read_csv(path: str | Path) -> pd.DataFrame:
    p = resolve_path(path)
    if not p.exists():
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


def _candidate_id(prefix: str, *parts: object) -> str:
    clean = [str(p).strip().replace(" ", "_").replace("/", "_") for p in parts if str(p).strip()]
    return "::".join([prefix, *clean])


def _append_candidate(rows: list[dict[str, Any]], **kwargs: Any) -> None:
    base = {
        "candidate_id": "",
        "candidate_name": "",
        "family": "",
        "source": "",
        "status": "unknown",
        "model": "",
        "strategy": "",
        "variant": "",
        "auc": None,
        "calibrated_auc": None,
        "brier": None,
        "calibrated_brier": None,
        "ece": None,
        "calibrated_ece": None,
        "log_loss": None,
        "total_return": None,
        "cagr": None,
        "sharpe": None,
        "calmar": None,
        "max_drawdown": None,
        "trades": None,
        "folds": None,
        "bars": None,
        "segment_positive_rate": None,
        "worst_segment_return": None,
        "overfit_risk_score": None,
        "robust_rank_score": None,
        "reason": "",
        "evidence_path": "",
    }
    base.update(kwargs)
    rows.append(base)


def collect_candidate_universe(cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """Collect candidate models/strategies from all research reports.

    Missing reports are tolerated. The output is a normalized table suitable for
    ranking and admission decisions.
    """
    rows: list[dict[str, Any]] = []

    # Fixed-split enhanced model library.
    p = "reports/enhanced_model_library/model_library_summary.csv"
    df = _safe_read_csv(p)
    for _, r in df.iterrows():
        model = str(_first(r, ["model", "model_name"], "unknown_model"))
        _append_candidate(
            rows,
            candidate_id=_candidate_id("model_fixed", model),
            candidate_name=f"Fixed split model: {model}",
            family="tabular_model_fixed_split",
            source="enhanced_model_library",
            status=str(_first(r, ["status"], "ok")),
            model=model,
            auc=_to_float(_first(r, ["valid_auc", "roc_auc", "auc", "test_auc"])),
            brier=_to_float(_first(r, ["valid_brier", "brier", "brier_score"])),
            ece=_to_float(_first(r, ["valid_ece", "ece"])),
            log_loss=_to_float(_first(r, ["valid_log_loss", "log_loss"])),
            evidence_path=p,
        )

    # Walk-forward calibrated model library.
    p = "reports/walk_forward_calibration_model_library/walk_forward_calibration_model_library_summary.csv"
    df = _safe_read_csv(p)
    for _, r in df.iterrows():
        model = str(_first(r, ["model"], "unknown_model"))
        _append_candidate(
            rows,
            candidate_id=_candidate_id("model_wf_calibrated", model),
            candidate_name=f"WF calibrated model: {model}",
            family="walk_forward_calibrated_model",
            source="walk_forward_calibration_model_library",
            status=str(_first(r, ["status"], "unknown")),
            model=model,
            auc=_to_float(_first(r, ["raw_auc"])),
            calibrated_auc=_to_float(_first(r, ["calibrated_auc"])),
            brier=_to_float(_first(r, ["raw_brier"])),
            calibrated_brier=_to_float(_first(r, ["calibrated_brier"])),
            ece=_to_float(_first(r, ["raw_ece"])),
            calibrated_ece=_to_float(_first(r, ["calibrated_ece"])),
            total_return=_to_float(_first(r, ["backtest_total_return"])),
            cagr=_to_float(_first(r, ["backtest_cagr"])),
            sharpe=_to_float(_first(r, ["backtest_sharpe"])),
            calmar=_to_float(_first(r, ["backtest_calmar"])),
            max_drawdown=_to_float(_first(r, ["backtest_max_drawdown"])),
            trades=_to_int(_first(r, ["backtest_trades"])),
            folds=_to_int(_first(r, ["folds"])),
            bars=_to_int(_first(r, ["bars"])),
            reason=str(_first(r, ["reason"], "")),
            evidence_path=p,
        )

    # Single walk-forward calibrated default model summary.
    p = "reports/walk_forward_calibration/walk_forward_calibration_summary.json"
    obj = _safe_read_json(p)
    if obj:
        raw = obj.get("raw", {}) if isinstance(obj.get("raw"), dict) else {}
        cal = obj.get("calibrated", {}) if isinstance(obj.get("calibrated"), dict) else {}
        bt = obj.get("backtest", {}) if isinstance(obj.get("backtest"), dict) else {}
        model = str((cfg or {}).get("walk_forward_calibration", {}).get("model_type", "default_wf_model"))
        _append_candidate(
            rows,
            candidate_id=_candidate_id("model_wf_calibrated", model, "default_report"),
            candidate_name=f"Default WF calibrated model: {model}",
            family="walk_forward_calibrated_model",
            source="walk_forward_calibration",
            status="ok",
            model=model,
            auc=_to_float(raw.get("roc_auc")),
            calibrated_auc=_to_float(cal.get("roc_auc")),
            brier=_to_float(raw.get("brier_score")),
            calibrated_brier=_to_float(cal.get("brier_score")),
            ece=_to_float(raw.get("ece")),
            calibrated_ece=_to_float(cal.get("ece")),
            total_return=_to_float(bt.get("total_return")),
            cagr=_to_float(bt.get("cagr")),
            sharpe=_to_float(bt.get("sharpe")),
            calmar=_to_float(bt.get("calmar")),
            max_drawdown=_to_float(bt.get("max_drawdown")),
            trades=_to_int(bt.get("trades")),
            folds=_to_int(obj.get("folds")),
            bars=_to_int(obj.get("bars")),
            evidence_path=p,
        )

    # Sequence model fixed split.
    p = "reports/sequence_models/sequence_model_summary.csv"
    df = _safe_read_csv(p)
    for _, r in df.iterrows():
        model = str(_first(r, ["model"], "sequence_model"))
        _append_candidate(
            rows,
            candidate_id=_candidate_id("sequence_fixed", model),
            candidate_name=f"Sequence fixed split: {model}",
            family="sequence_model_fixed_split",
            source="sequence_models",
            status=str(_first(r, ["status"], "ok")),
            model=model,
            auc=_to_float(_first(r, ["roc_auc", "auc"])),
            brier=_to_float(_first(r, ["brier_score", "brier"])),
            ece=_to_float(_first(r, ["ece"])),
            log_loss=_to_float(_first(r, ["log_loss"])),
            evidence_path=p,
        )

    # Sequence walk-forward.
    p = "reports/sequence_walk_forward/sequence_walk_forward_summary.csv"
    df = _safe_read_csv(p)
    for _, r in df.iterrows():
        model = str(_first(r, ["model"], "sequence_model"))
        _append_candidate(
            rows,
            candidate_id=_candidate_id("sequence_wf", model),
            candidate_name=f"Sequence walk-forward: {model}",
            family="sequence_model_walk_forward",
            source="sequence_walk_forward",
            status=str(_first(r, ["status"], "ok")),
            model=model,
            auc=_to_float(_first(r, ["mean_auc", "roc_auc", "auc"])),
            brier=_to_float(_first(r, ["mean_brier", "brier_score", "brier"])),
            ece=_to_float(_first(r, ["mean_ece", "ece"])),
            folds=_to_int(_first(r, ["folds", "n_folds"])),
            reason=str(_first(r, ["reason"], "")),
            evidence_path=p,
        )

    # Strategy parameter search candidates.
    p = "reports/robustness/parameter_search/strategy_parameter_search_summary.csv"
    df = _safe_read_csv(p)
    for idx, r in df.iterrows():
        strategy = str(_first(r, ["strategy", "strategy_name"], f"strategy_{idx}"))
        variant = str(_first(r, ["params", "parameter_set", "variant"], idx))
        _append_candidate(
            rows,
            candidate_id=_candidate_id("strategy_param", strategy, variant),
            candidate_name=f"Strategy param: {strategy} #{idx}",
            family="rule_strategy_parameter_set",
            source="strategy_parameter_search",
            status="ok",
            strategy=strategy,
            variant=variant,
            total_return=_to_float(_first(r, ["total_return", "return"])),
            cagr=_to_float(_first(r, ["cagr"])),
            sharpe=_to_float(_first(r, ["sharpe"])),
            calmar=_to_float(_first(r, ["calmar"])),
            max_drawdown=_to_float(_first(r, ["max_drawdown", "mdd"])),
            trades=_to_int(_first(r, ["trades", "num_trades"])),
            segment_positive_rate=_to_float(_first(r, ["segment_positive_rate"])),
            worst_segment_return=_to_float(_first(r, ["worst_segment_return"])),
            overfit_risk_score=_to_float(_first(r, ["overfit_risk_score"])),
            robust_rank_score=_to_float(_first(r, ["robust_rank_score"])),
            evidence_path=p,
        )

    # Ensemble dynamic strategy.
    p = "reports/ensemble/ensemble_summary.csv"
    df = _safe_read_csv(p)
    if not df.empty:
        r = df.iloc[0]
        _append_candidate(
            rows,
            candidate_id=_candidate_id("ensemble", "dynamic_weighted_strategy"),
            candidate_name="Ensemble dynamic strategy",
            family="ensemble_strategy",
            source="ensemble",
            status="ok",
            strategy="ensemble_dynamic",
            total_return=_to_float(_first(r, ["total_return", "return"])),
            cagr=_to_float(_first(r, ["cagr"])),
            sharpe=_to_float(_first(r, ["sharpe"])),
            calmar=_to_float(_first(r, ["calmar"])),
            max_drawdown=_to_float(_first(r, ["max_drawdown", "mdd"])),
            trades=_to_int(_first(r, ["trades", "num_trades"])),
            evidence_path=p,
        )

    # Calibrated ML confidence strategy backtest.
    p = "reports/calibrated_ml_backtest/calibrated_ml_summary.csv"
    df = _safe_read_csv(p)
    if not df.empty:
        r = df.iloc[0]
        _append_candidate(
            rows,
            candidate_id=_candidate_id("strategy_calibrated_ml", "confidence_target_exposure"),
            candidate_name="Calibrated ML confidence strategy",
            family="calibrated_ml_strategy",
            source="calibrated_ml_backtest",
            status="ok",
            strategy="calibrated_ml_confidence",
            total_return=_to_float(_first(r, ["total_return", "return"])),
            cagr=_to_float(_first(r, ["cagr"])),
            sharpe=_to_float(_first(r, ["sharpe"])),
            calmar=_to_float(_first(r, ["calmar"])),
            max_drawdown=_to_float(_first(r, ["max_drawdown", "mdd"])),
            trades=_to_int(_first(r, ["trades", "num_trades"])),
            evidence_path=p,
        )

    table = pd.DataFrame(rows)
    if table.empty:
        return table
    # Deduplicate exact candidate ids, keeping the latest/higher evidence row.
    table = table.drop_duplicates(subset=["candidate_id"], keep="last").reset_index(drop=True)
    return table


def _clip_score(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if not math.isfinite(v):
        return 0.0
    return max(lo, min(hi, v))


def _metric_score(row: pd.Series, policy: AdmissionPolicy) -> tuple[float, list[str], list[str]]:
    score = 35.0
    reasons: list[str] = []
    blockers: list[str] = []

    status = str(row.get("status", "unknown")).lower()
    if status not in {"ok", "runnable", "success", "unknown"}:
        score -= 45
        blockers.append(f"status={status}")

    auc = _to_float(row.get("calibrated_auc"), _to_float(row.get("auc")))
    if auc is not None:
        if auc >= 0.60:
            score += 18
        elif auc >= 0.55:
            score += 10
        elif auc >= policy.min_auc:
            score += 4
        else:
            score -= 10
            reasons.append(f"auc below threshold ({auc:.3f})")
    elif row.get("family") in {"tabular_model_fixed_split", "walk_forward_calibrated_model", "sequence_model_fixed_split", "sequence_model_walk_forward"}:
        score -= 8
        reasons.append("missing auc")

    brier = _to_float(row.get("calibrated_brier"), _to_float(row.get("brier")))
    if brier is not None:
        if brier <= 0.22:
            score += 10
        elif brier <= policy.max_brier:
            score += 4
        else:
            score -= 8
            reasons.append(f"brier high ({brier:.3f})")

    ece = _to_float(row.get("calibrated_ece"), _to_float(row.get("ece")))
    if ece is not None:
        if ece <= 0.06:
            score += 10
        elif ece <= policy.max_ece:
            score += 4
        else:
            score -= 8
            reasons.append(f"ece high ({ece:.3f})")

    sharpe = _to_float(row.get("sharpe"))
    if sharpe is not None:
        if sharpe >= 1.0:
            score += 16
        elif sharpe >= 0.5:
            score += 10
        elif sharpe >= policy.min_sharpe:
            score += 4
        else:
            score -= 5
            reasons.append(f"sharpe weak ({sharpe:.2f})")

    calmar = _to_float(row.get("calmar"))
    if calmar is not None:
        if calmar >= 1.0:
            score += 16
        elif calmar >= 0.4:
            score += 9
        elif calmar >= policy.min_calmar:
            score += 3
        else:
            score -= 6
            reasons.append(f"calmar weak ({calmar:.2f})")

    mdd = _to_float(row.get("max_drawdown"))
    if mdd is not None:
        mdd_abs = abs(mdd)
        if mdd_abs <= 0.12:
            score += 12
        elif mdd_abs <= 0.22:
            score += 6
        elif mdd_abs <= policy.max_drawdown_abs:
            score -= 2
            reasons.append(f"drawdown elevated ({mdd:.2%})")
        else:
            score -= 20
            blockers.append(f"drawdown too large ({mdd:.2%})")

    trades = _to_int(row.get("trades"))
    family = str(row.get("family", ""))
    if trades is not None:
        if trades >= 40:
            score += 7
        elif trades >= policy.min_trades:
            score += 2
        elif family in {"rule_strategy_parameter_set", "ensemble_strategy", "calibrated_ml_strategy", "walk_forward_calibrated_model"}:
            score -= 12
            blockers.append(f"too few trades ({trades})")

    folds = _to_int(row.get("folds"))
    if folds is not None:
        if folds >= 6:
            score += 6
        elif folds >= policy.min_folds:
            score += 2
        else:
            score -= 8
            reasons.append(f"few folds ({folds})")
    elif "walk_forward" in family:
        score -= 8
        reasons.append("missing fold count")

    pos_rate = _to_float(row.get("segment_positive_rate"))
    if pos_rate is not None:
        if pos_rate >= 0.70:
            score += 10
        elif pos_rate >= policy.min_segment_positive_rate:
            score += 4
        else:
            score -= 10
            reasons.append(f"segment positive rate low ({pos_rate:.2f})")

    overfit = _to_float(row.get("overfit_risk_score"))
    if overfit is not None:
        if overfit <= 0.25:
            score += 8
        elif overfit <= policy.max_overfit_risk_score:
            score += 2
        else:
            score -= 16
            blockers.append(f"overfit risk high ({overfit:.2f})")

    robust = _to_float(row.get("robust_rank_score"))
    if robust is not None:
        # Robust scores can be arbitrary scale in older reports; squash gently.
        score += max(-10, min(15, robust / 10.0))

    return _clip_score(score), reasons, blockers


def apply_admission_policy(candidates: pd.DataFrame, policy: AdmissionPolicy | None = None) -> pd.DataFrame:
    policy = policy or AdmissionPolicy()
    if candidates.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for _, r in candidates.iterrows():
        score, reasons, blockers = _metric_score(r, policy)
        family = str(r.get("family", ""))
        missing_perf = pd.isna(r.get("sharpe")) and pd.isna(r.get("calmar")) and pd.isna(r.get("total_return"))
        missing_model_quality = pd.isna(r.get("auc")) and pd.isna(r.get("calibrated_auc"))
        extra_reasons = list(reasons)
        if family.endswith("fixed_split"):
            extra_reasons.append("fixed split evidence only; require walk-forward before paper pool")
            score = min(score, policy.watch_score_threshold + 10)
        if "sequence" in family:
            extra_reasons.append("sequence model is research-only until it beats calibrated tabular models")
            score = min(score, policy.watch_score_threshold + 8)
        if missing_perf and missing_model_quality:
            blockers.append("insufficient metrics")
            score = min(score, policy.reject_score_threshold)

        if blockers:
            decision = "rejected"
        elif score >= policy.paper_score_threshold and "fixed_split" not in family and "sequence" not in family:
            decision = "paper_candidate_pool"
        elif score >= policy.watch_score_threshold:
            decision = "watchlist"
        elif score >= policy.reject_score_threshold:
            decision = "research_only"
        else:
            decision = "rejected"

        row = r.to_dict()
        row.update({
            "admission_score": round(score, 3),
            "admission_decision": decision,
            "blockers": "; ".join(blockers),
            "warnings": "; ".join(extra_reasons),
            "policy_min_auc": policy.min_auc,
            "policy_max_drawdown_abs": policy.max_drawdown_abs,
            "policy_min_trades": policy.min_trades,
        })
        rows.append(row)

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["admission_decision", "admission_score"], ascending=[True, False]).reset_index(drop=True)
    return out


def summarize_admissions(ranked: pd.DataFrame) -> dict[str, Any]:
    if ranked.empty:
        return {"status": "no_candidates", "total_candidates": 0}
    counts = ranked["admission_decision"].value_counts().to_dict() if "admission_decision" in ranked else {}
    best = ranked.sort_values("admission_score", ascending=False).iloc[0].to_dict()
    return {
        "status": "ok",
        "total_candidates": int(len(ranked)),
        "paper_candidate_pool": int(counts.get("paper_candidate_pool", 0)),
        "watchlist": int(counts.get("watchlist", 0)),
        "research_only": int(counts.get("research_only", 0)),
        "rejected": int(counts.get("rejected", 0)),
        "best_candidate_id": best.get("candidate_id"),
        "best_candidate_name": best.get("candidate_name"),
        "best_family": best.get("family"),
        "best_score": float(best.get("admission_score", 0.0)),
        "live_trading_enabled": False,
        "note": "Admission decisions are for research/paper-trading candidate selection only; live trading remains disabled.",
    }


def save_admission_outputs(
    ranked: pd.DataFrame,
    candidates: pd.DataFrame,
    output_dir: str | Path,
    policy: AdmissionPolicy | None = None,
) -> dict[str, Any]:
    out_dir = resolve_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    policy = policy or AdmissionPolicy()
    summary = summarize_admissions(ranked)
    summary["policy"] = asdict(policy)

    candidates.to_csv(out_dir / "candidate_universe.csv", index=False, encoding="utf-8-sig")
    ranked.to_csv(out_dir / "model_strategy_leaderboard.csv", index=False, encoding="utf-8-sig")
    if ranked.empty:
        admission = pd.DataFrame(columns=["admission_decision", "count"])
    else:
        admission = ranked["admission_decision"].value_counts().rename_axis("admission_decision").reset_index(name="count")
    admission.to_csv(out_dir / "admission_summary.csv", index=False, encoding="utf-8-sig")
    (out_dir / "model_strategy_admission_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # Plot top scores if matplotlib is installed.
    try:
        import matplotlib.pyplot as plt

        top = ranked.sort_values("admission_score", ascending=False).head(20).iloc[::-1]
        if not top.empty:
            fig, ax = plt.subplots(figsize=(10, max(4, len(top) * 0.35)))
            ax.barh(top["candidate_name"].astype(str), top["admission_score"].astype(float))
            ax.set_xlabel("Admission score")
            ax.set_title("Top model/strategy candidates")
            fig.tight_layout()
            fig.savefig(out_dir / "leaderboard_top_scores.png", dpi=160)
            plt.close(fig)
    except Exception:
        pass

    notes = [
        "paper_candidate_pool means the candidate is allowed into local paper-trading observation only.",
        "watchlist candidates need more evidence or better calibration before being used in the paper pool.",
        "fixed-split and sequence-only evidence is intentionally capped to avoid overconfidence.",
        "live trading remains disabled by design in this package version.",
    ]
    tables = {
        "admission_summary": admission,
        "leaderboard_top_30": ranked.sort_values("admission_score", ascending=False).head(30) if not ranked.empty else ranked,
    }
    images = []
    if (out_dir / "leaderboard_top_scores.png").exists():
        images.append(out_dir / "leaderboard_top_scores.png")
    build_research_html_report(
        out_dir / "model_strategy_admission_report.html",
        "BTC V2.9 Unified Model & Strategy Admission Report",
        summary=summary,
        tables=tables,
        images=images,
        notes=notes,
    )
    return summary


def run_model_strategy_admission(cfg: dict[str, Any] | None = None, output_dir: str | Path = "reports/model_admission") -> dict[str, Any]:
    cfg = cfg or {}
    section = cfg.get("model_admission", {}) if isinstance(cfg, dict) else {}
    thresholds = section.get("policy", {}) if isinstance(section, dict) else {}
    policy = AdmissionPolicy(**{k: v for k, v in thresholds.items() if k in AdmissionPolicy.__dataclass_fields__})
    out = section.get("output_path", output_dir) if isinstance(section, dict) else output_dir
    candidates = collect_candidate_universe(cfg)
    ranked = apply_admission_policy(candidates, policy)
    return save_admission_outputs(ranked, candidates, out, policy)
