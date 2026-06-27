from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from crypto_quant.config import project_root
from crypto_quant.utils.runtime_env import runtime_summary


def _check_port(host: str, port: int) -> dict[str, Any]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        code = sock.connect_ex((host, port))
    return {
        "host": host,
        "port": port,
        "available": code != 0,
        "detail": "available" if code != 0 else "already in use or already serving dashboard",
    }


def _powershell_execution_policy() -> dict[str, Any]:
    if os.name != "nt":
        return {"checked": False, "reason": "not_windows"}
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Get-ExecutionPolicy -List | ConvertTo-Json -Compress",
            ],
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
        return {
            "checked": True,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"checked": False, "reason": repr(exc)}


def _file_present(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists()}


def build_report(host: str = "localhost", port: int = 8501) -> dict[str, Any]:
    root = project_root()
    checks = []
    for rel in [
        "start_dashboard.cmd",
        "start_dashboard.bat",
        "start_dashboard.ps1",
        "scripts/run_dashboard.py",
        "frontend/app.py",
        ".venv/Scripts/python.exe",
        ".venv/bin/python",
    ]:
        checks.append({"category": "files", "name": rel, **_file_present(root / rel)})

    dependencies = []
    for module in ["streamlit", "pandas", "pyarrow", "yaml"]:
        dependencies.append(
            {
                "module": module,
                "importable": importlib.util.find_spec(module) is not None,
            }
        )

    return {
        "status": "pass" if importlib.util.find_spec("streamlit") is not None else "warn",
        "runtime": runtime_summary(root),
        "port": _check_port(host, port),
        "dependencies": dependencies,
        "files": checks,
        "powershell_execution_policy": _powershell_execution_policy(),
        "recommended_launchers": {
            "powershell_safe": r".\start_dashboard.cmd",
            "cmd": r"start_dashboard.cmd",
            "manual_after_venv_activation": r"python scripts\run_dashboard.py --open-browser",
            "ps1_bypass_if_needed": r"powershell -NoProfile -ExecutionPolicy Bypass -File .\start_dashboard.ps1",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose local dashboard startup prerequisites.")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report(args.host, args.port)
    out_dir = project_root() / "reports" / "runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dashboard_startup_diagnostics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"dashboard startup status: {report['status']}")
    print(f"python: {report['runtime']['python_executable']}")
    print(f"project .venv active: {report['runtime']['running_in_project_venv']}")
    print(f"port {args.port}: {report['port']['detail']}")
    for dep in report["dependencies"]:
        if not dep["importable"]:
            print(f"[warn] missing module: {dep['module']}")
    print("recommended launcher from PowerShell:")
    print(r"  .\start_dashboard.cmd")
    print("manual fallback after .venv activation:")
    print(r"  python scripts\run_dashboard.py --open-browser")


if __name__ == "__main__":
    main()
