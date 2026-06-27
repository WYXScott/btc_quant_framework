from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.data.quality import run_ohlcv_quality_checks, save_quality_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Run strict OHLCV data quality checks.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when the data quality status is fail.")
    parser.add_argument("--no-strict", action="store_true", help="Do not exit non-zero even if config requires the quality gate.")
    args = parser.parse_args()

    cfg = load_config()
    dq_cfg = cfg.get("data_quality", {})
    raw_path = resolve_path(cfg["data"]["raw_path"])
    out_dir = resolve_path(dq_cfg.get("output_path", "reports/data_quality"))
    df = load_parquet(raw_path)
    report, issues = run_ohlcv_quality_checks(
        df,
        timeframe=cfg["data"]["timeframe"],
        max_abs_log_return=float(dq_cfg.get("max_abs_log_return", 0.20)),
        zscore_threshold=float(dq_cfg.get("zscore_threshold", 8.0)),
        max_range_pct=float(dq_cfg.get("max_range_pct", 0.35)),
        max_zero_volume_fraction=float(dq_cfg.get("max_zero_volume_fraction", 0.01)),
        allow_incomplete_latest_bar=bool(dq_cfg.get("allow_incomplete_latest_bar", True)),
    )
    report["context"] = "run_data_quality_check"
    paths = save_quality_artifacts(report, issues, out_dir)
    print("Data quality status:", report.get("status"))
    print("Rows:", report.get("rows"), "Issues:", report.get("issue_count"), "Critical:", report.get("critical_count"))
    for key, value in paths.items():
        print(f"{key}: {value}")
    if not issues.empty:
        print(issues[["severity", "category", "count", "message"]].head(20).to_string(index=False))

    strict = (args.strict or bool(dq_cfg.get("require_pass_before_training", False))) and not args.no_strict
    if strict and report.get("status") != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
