from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import _bootstrap  # noqa: F401

from crypto_quant.config import project_root

SAFE_STEPS = [
    "deploy_check.py",
    "run_data_quality_check.py",
    "build_features.py",
    "train_model.py",
    "run_model_diagnostics.py",
    "train_calibrated_model.py",
    "run_signal_confidence_report.py",
    "run_calibrated_ml_backtest.py",
    "run_walk_forward_calibration.py",
    "check_model_backends.py",
    "run_enhanced_model_library.py",
    "run_wf_calibration_model_library.py",
    "build_v27_research_report.py",
    "check_sequence_model_backends.py",
    "run_sequence_model_experiments.py",
    "run_sequence_walk_forward.py",
    "build_v28_sequence_report.py",
    "run_model_strategy_admission.py",
    "build_v29_admission_report.py",
    "run_paper_health_check.py",
    "run_signal_hit_rate_report.py",
    "run_daily_operations_report.py",
    "build_v30_operations_report.py",
    "build_v26_research_report.py",
    "run_purged_embargo_cv.py",
    "run_strategy_library_backtest.py",
    "run_strategy_parameter_search.py",
    "run_ensemble_strategy.py",
    "run_market_realism_report.py",
    "audit_package.py",
]


def run_script(script_name: str) -> int:
    script = project_root() / "scripts" / script_name
    print(f"\n=== Running {script_name} ===")
    proc = subprocess.run([sys.executable, str(script)], cwd=project_root())
    return int(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a safe research-only pipeline. No live orders are submitted.")
    parser.add_argument("--include-download", action="store_true", help="Also run public OHLCV download first. Requires internet.")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    steps = (["download_ohlcv.py"] if args.include_download else []) + SAFE_STEPS
    for step in steps:
        code = run_script(step)
        if code != 0 and not args.continue_on_error:
            raise SystemExit(code)
    print("\nSafe research pipeline finished.")


if __name__ == "__main__":
    main()
