from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from _bootstrap import ROOT
from crypto_quant.research.model_admission import AdmissionPolicy, apply_admission_policy, save_admission_outputs


def main() -> None:
    out_dir = ROOT / "reports" / "model_admission_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)
    candidates = pd.DataFrame([
        {
            "candidate_id": "model_wf_calibrated::extra_trees",
            "candidate_name": "WF calibrated model: extra_trees",
            "family": "walk_forward_calibrated_model",
            "source": "smoke",
            "status": "ok",
            "model": "extra_trees",
            "strategy": "",
            "variant": "",
            "calibrated_auc": 0.57,
            "calibrated_brier": 0.238,
            "calibrated_ece": 0.08,
            "sharpe": 0.65,
            "calmar": 0.38,
            "max_drawdown": -0.18,
            "trades": 30,
            "folds": 5,
            "reason": "",
            "evidence_path": "smoke",
        },
        {
            "candidate_id": "sequence_fixed::lstm",
            "candidate_name": "Sequence fixed split: lstm",
            "family": "sequence_model_fixed_split",
            "source": "smoke",
            "status": "ok",
            "model": "lstm",
            "strategy": "",
            "variant": "",
            "auc": 0.61,
            "brier": 0.235,
            "ece": 0.11,
            "reason": "",
            "evidence_path": "smoke",
        },
        {
            "candidate_id": "strategy_param::bad",
            "candidate_name": "Bad strategy",
            "family": "rule_strategy_parameter_set",
            "source": "smoke",
            "status": "ok",
            "model": "",
            "strategy": "bad",
            "variant": "",
            "sharpe": -0.2,
            "calmar": -0.1,
            "max_drawdown": -0.55,
            "trades": 3,
            "overfit_risk_score": 0.9,
            "reason": "",
            "evidence_path": "smoke",
        },
    ])
    ranked = apply_admission_policy(candidates, AdmissionPolicy())
    summary = save_admission_outputs(ranked, candidates, out_dir, AdmissionPolicy())
    (out_dir / "model_admission_smoke_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    assert len(ranked) == 3
    assert "admission_decision" in ranked.columns
    assert (out_dir / "model_strategy_admission_report.html").exists()
    print("model_admission_smoke passed")


if __name__ == "__main__":
    main()
