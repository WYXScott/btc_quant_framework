from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, project_root
from crypto_quant.utils.runtime_env import runtime_summary

PACKAGE_IMPORTS = {
    "pandas": "pandas",
    "numpy": "numpy",
    "pyarrow": "pyarrow",
    "PyYAML": "yaml",
    "ccxt": "ccxt",
    "requests": "requests",
    "scikit-learn": "sklearn",
    "joblib": "joblib",
    "matplotlib": "matplotlib",
    "websocket-client": "websocket",
    "streamlit": "streamlit",
}


def _add(rows: list[dict[str, Any]], category: str, name: str, status: str, detail: str) -> None:
    rows.append({"category": category, "name": name, "status": status, "detail": detail})


def _package_present(import_name: str) -> bool:
    return importlib.util.find_spec(import_name) is not None


def build_report(strict: bool = False) -> dict[str, Any]:
    root = project_root()
    cfg = load_config()
    runtime_cfg = cfg.get("runtime", {}) or {}
    summary = runtime_summary(root)
    rows: list[dict[str, Any]] = []

    py_ok = sys.version_info >= (3, 10)
    _add(rows, "python", "version", "pass" if py_ok else "fail", summary["python_version"])

    require_venv = bool(runtime_cfg.get("require_venv_for_local_commands", True)) or strict
    if require_venv:
        status = "pass" if summary["running_in_project_venv"] else "fail"
        detail = "running inside project .venv" if status == "pass" else "activate .venv before local checks"
    else:
        status = "pass" if summary["virtualenv_active"] else "warn"
        detail = "venv active" if summary["virtualenv_active"] else "venv is recommended"
    _add(rows, "python", "project_venv_active", status, detail)

    prefer_project_venv = bool(runtime_cfg.get("prefer_project_venv", True))
    _add(
        rows,
        "python",
        "prefer_project_venv",
        "pass" if prefer_project_venv else "warn",
        f"prefer_project_venv={prefer_project_venv}; project_venv_python={summary['project_venv_python'] or 'missing'}",
    )

    for package, import_name in PACKAGE_IMPORTS.items():
        present = _package_present(import_name)
        _add(rows, "dependencies", package, "pass" if present else "fail", "importable" if present else "missing; run python -m pip install -r requirements.txt")

    for rel in ["data/raw", "data/processed", "data/database", "models", "reports", "logs"]:
        path = root / rel
        _add(rows, "paths", rel, "pass" if path.exists() else "warn", str(path))

    counts = {
        "pass": sum(1 for row in rows if row["status"] == "pass"),
        "warn": sum(1 for row in rows if row["status"] == "warn"),
        "fail": sum(1 for row in rows if row["status"] == "fail"),
    }
    return {
        "status": "fail" if counts["fail"] else "pass",
        "runtime": summary,
        "counts": counts,
        "checks": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the local Python virtual environment and required dependencies.")
    parser.add_argument("--strict", action="store_true", help="Fail if the project-local .venv is not active.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report only.")
    parser.add_argument("--no-write-report", action="store_true", help="Do not write reports/runtime_env/runtime_env_report.json.")
    args = parser.parse_args()

    report = build_report(strict=args.strict)
    if not args.no_write_report:
        out_dir = project_root() / "reports" / "runtime_env"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "runtime_env_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"runtime status: {report['status']}  counts={report['counts']}")
        print(f"python: {report['runtime']['python_executable']}")
        print(f"project .venv active: {report['runtime']['running_in_project_venv']}")
        for row in report["checks"]:
            if row["status"] != "pass":
                print(f"[{row['status']}] {row['category']}.{row['name']}: {row['detail']}")

    raise SystemExit(0 if report["status"] == "pass" else 1)


if __name__ == "__main__":
    main()
