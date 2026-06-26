from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT

from crypto_quant.config import load_config
from crypto_quant.deploy.health import DeploymentHealthChecker


def print_text(report) -> None:
    print(f"Deployment health: {report.overall_status.upper()}")
    print(f"Project root: {report.project_root}")
    print(f"Timestamp UTC: {report.timestamp_utc}")
    print("-" * 72)
    for check in report.checks:
        print(f"[{check.status.upper():4}] {check.name}: {check.message}")
        if check.details and check.status in {"warn", "fail"}:
            print(json.dumps(check.details, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run V1.0 deployment pre-flight checks.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--no-write", action="store_true", help="Do not write reports/deployment/health_report.json.")
    args = parser.parse_args()

    cfg = load_config()
    checker = DeploymentHealthChecker(cfg, root=ROOT)
    report = checker.run()
    if not args.no_write:
        path = checker.write_report(report)
        print(f"Report written: {path}")
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print_text(report)
    raise SystemExit(1 if report.has_failures else 0)


if __name__ == "__main__":
    main()
