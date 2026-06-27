from __future__ import annotations

import csv
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, project_root, resolve_path
from crypto_quant.utils.runtime_env import runtime_summary


def _exists(path: str | Path) -> bool:
    return resolve_path(path).exists()


def _add(rows: list[dict[str, Any]], category: str, name: str, status: str, detail: str) -> None:
    rows.append({"category": category, "name": name, "status": status, "detail": detail})


def _script_path(script: str) -> Path:
    return (project_root() / "scripts" / str(script)).resolve()


def _is_script_under_scripts(script: str) -> bool:
    try:
        raw = Path(str(script))
        if raw.is_absolute():
            return False
        _script_path(str(script)).relative_to((project_root() / "scripts").resolve())
        return True
    except Exception:
        return False


def _check_required_files(rows: list[dict[str, Any]], version: str) -> None:
    required = [
        "README.md",
        "start_dashboard.cmd",
        "start_dashboard.bat",
        "start_dashboard.ps1",
        "config/config.yaml",
        "frontend/app.py",
        "docs/INDEX.md",
        "docs/SYSTEM_ARCHITECTURE.md",
        "docs/OPERATING_MODEL.md",
        "docs/EXTENSION_INTERFACES.md",
        "docs/SERVICE_OPERATIONS.md",
        "docs/ROADMAP.md",
        "scripts/manage_services.py",
        "scripts/check_runtime_env.py",
        "scripts/diagnose_dashboard_startup.py",
        "scripts/run_local_checks.bat",
        "scripts/run_local_checks.ps1",
        "docs/LOCAL_ENVIRONMENT.md",
        "docs/WINDOWS_STARTUP_TROUBLESHOOTING.md",
        f"RELEASE_NOTES_V{version.replace('.', '_')}.md",
    ]
    for path in required:
        _add(rows, "files", path, "pass" if _exists(path) else "fail", "required file")


def _check_allowed_scripts(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    allowed = cfg.get("ui", {}).get("allowed_button_scripts", []) or []
    if not allowed:
        _add(rows, "ui", "allowed_button_scripts", "fail", "UI safe-mode script whitelist is empty")
        return
    seen: set[str] = set()
    duplicates: set[str] = set()
    for script in allowed:
        script = str(script)
        if script in seen:
            duplicates.add(script)
        seen.add(script)
        if not _is_script_under_scripts(script):
            _add(rows, "ui", script, "fail", "script must be a relative path under scripts/")
            continue
        path = _script_path(script)
        _add(rows, "ui", script, "pass" if path.exists() else "fail", "allowed UI script exists")
    if duplicates:
        _add(rows, "ui", "duplicate_allowed_scripts", "warn", ", ".join(sorted(duplicates)))
    else:
        _add(rows, "ui", "duplicate_allowed_scripts", "pass", "no duplicates")


def _check_managed_services(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    service_cfg = cfg.get("managed_services", {}) or {}
    allowed = service_cfg.get("allowed", {}) or {}
    _add(rows, "services", "managed_services.enabled", "pass" if service_cfg.get("enabled") is True else "warn", "service console config")
    _add(rows, "services", "state_dir", "pass" if service_cfg.get("state_dir") else "fail", str(service_cfg.get("state_dir", "")))
    _add(rows, "services", "log_dir", "pass" if service_cfg.get("log_dir") else "fail", str(service_cfg.get("log_dir", "")))
    if not allowed:
        _add(rows, "services", "allowed", "warn", "no managed services configured")
        return
    for name, raw in allowed.items():
        item = raw if isinstance(raw, dict) else {}
        script = str(item.get("script", "")).strip()
        if not script:
            _add(rows, "services", str(name), "fail", "managed service is missing script")
            continue
        if not _is_script_under_scripts(script):
            _add(rows, "services", f"{name}.script_scope", "fail", f"must be relative under scripts/: {script}")
            continue
        script_path = _script_path(script)
        _add(rows, "services", f"{name}.script", "pass" if script_path.exists() else "fail", script)
        args = item.get("args", [])
        _add(rows, "services", f"{name}.args", "pass" if isinstance(args, list) else "fail", str(args))


def _check_safety_switches(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    expectations = [
        ("live_trading.master_enable", cfg.get("live_trading", {}).get("master_enable"), False),
        ("ui.allow_live_actions", cfg.get("ui", {}).get("allow_live_actions"), False),
        ("broker.safety.allow_live_trading", cfg.get("broker", {}).get("safety", {}).get("allow_live_trading"), False),
        ("broker.safety.default_dry_run", cfg.get("broker", {}).get("safety", {}).get("default_dry_run"), True),
        ("execution.execute_demo_orders", cfg.get("execution", {}).get("execute_demo_orders"), False),
        ("shadow_live.forbid_order_submission", cfg.get("shadow_live", {}).get("forbid_order_submission"), True),
    ]
    for name, current, expected in expectations:
        status = "pass" if current is expected else "fail"
        _add(rows, "safety", name, status, f"expected={expected} current={current}")


def _check_execution_provider(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    mode = str((cfg.get("execution", {}) or {}).get("mode", "local_paper"))
    provider = str((cfg.get("broker", {}) or {}).get("provider", (cfg.get("exchange", {}) or {}).get("name", "okx"))).lower()
    if mode == "local_paper":
        _add(rows, "execution", "provider_mode", "pass", f"mode={mode}; provider={provider}; no exchange orders will be sent")
    else:
        _add(
            rows,
            "execution",
            "provider_mode",
            "fail",
            f"execution.mode={mode} is outside the V3.2.1 OKX-first local-paper workflow; keep local_paper until a dedicated adapter is implemented",
        )

    if provider == "okx":
        passphrase_env = (cfg.get("broker", {}) or {}).get("passphrase_env")
        _add(rows, "execution", "okx_passphrase_env", "pass" if passphrase_env else "warn", str(passphrase_env or "missing"))


def _check_data_quality_gate(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    dq_cfg = cfg.get("data_quality", {}) or {}
    required = bool(dq_cfg.get("require_pass_before_training", False))
    _add(
        rows,
        "data_quality",
        "require_pass_before_training",
        "pass" if required else "fail",
        "must be true so training/feature generation are blocked by critical data-quality failures",
    )


def _check_runtime_environment(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    runtime_cfg = cfg.get("runtime", {}) or {}
    summary = runtime_summary(project_root())
    prefer_project_venv = bool(runtime_cfg.get("prefer_project_venv", True))
    require_venv = bool(runtime_cfg.get("require_venv_for_local_commands", True))
    _add(rows, "runtime", "prefer_project_venv", "pass" if prefer_project_venv else "warn", str(prefer_project_venv))
    # Running the stability check outside .venv is not source corruption, but it is
    # a common local setup cause of false failures. Keep this as a warning so CI
    # and source-only reviews can still pass. scripts/check_runtime_env.py --strict
    # is the hard local environment gate.
    if require_venv:
        status = "pass" if summary.get("running_in_project_venv") else "warn"
        detail = "project .venv active" if status == "pass" else "activate .venv before running local commands"
    else:
        status = "pass"
        detail = "venv not required by config"
    _add(rows, "runtime", "project_venv_active", status, detail)
    _add(
        rows,
        "runtime",
        "project_venv_python",
        "pass" if summary.get("project_venv_python") else "warn",
        str(summary.get("project_venv_python") or "missing .venv python"),
    )


def _check_runtime_paths(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    paths = [
        ("raw_ohlcv", cfg.get("data", {}).get("raw_path")),
        ("features", cfg.get("data", {}).get("feature_path")),
        ("dataset", cfg.get("data", {}).get("dataset_path")),
        ("model", cfg.get("model", {}).get("model_path")),
        ("feature_list", cfg.get("model", {}).get("feature_list_path")),
        ("paper_db", cfg.get("paper", {}).get("database_path")),
        ("realtime_db", cfg.get("realtime", {}).get("database_path")),
    ]
    for name, path in paths:
        if not path:
            _add(rows, "artifacts", name, "warn", "path is not configured")
            continue
        p = resolve_path(path)
        _add(rows, "artifacts", name, "pass" if p.exists() else "warn", str(p))


def _check_realtime_schema(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    db_path = resolve_path(cfg.get("realtime", {}).get("database_path", "data/database/realtime_market.sqlite"))
    if not db_path.exists():
        _add(rows, "realtime", "sqlite_database", "warn", f"missing: {db_path}")
        return
    expected = {
        "realtime_klines": {"exchange", "inst_id", "channel", "timeframe", "timestamp", "open", "high", "low", "close", "volume", "confirm"},
        "realtime_status": {"component", "status", "last_error", "message_count", "kline_count", "details_json"},
    }
    try:
        with sqlite3.connect(db_path) as conn:
            for table, columns in expected.items():
                found = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
                missing = sorted(columns - found)
                status = "pass" if not missing else "fail"
                detail = "schema ok" if not missing else f"missing columns: {missing}"
                _add(rows, "realtime", table, status, detail)
    except Exception as exc:
        _add(rows, "realtime", "sqlite_schema", "fail", repr(exc))


def _check_dependency_imports(rows: list[dict[str, Any]]) -> None:
    # Missing Python packages are environment/setup issues rather than source-code
    # corruption, so this check warns instead of failing the source stability gate.
    for package in ["pandas", "numpy", "pyarrow", "yaml", "sklearn", "joblib", "requests", "websocket", "streamlit"]:
        present = importlib.util.find_spec(package) is not None
        _add(rows, "dependencies", package, "pass" if present else "warn", "importable" if present else "install from requirements.txt")


def _check_version_docs(rows: list[dict[str, Any]], version: str) -> None:
    readme = (project_root() / "README.md").read_text(encoding="utf-8")
    release_path = project_root() / f"RELEASE_NOTES_V{version.replace('.', '_')}.md"
    _add(rows, "version", "README current version", "pass" if f"V{version}" in readme else "fail", version)
    _add(rows, "version", release_path.name, "pass" if release_path.exists() else "fail", "release notes for current version")


def main() -> None:
    cfg = load_config()
    version = str(cfg.get("project", {}).get("version", "unknown"))
    rows: list[dict[str, Any]] = []

    _check_required_files(rows, version)
    _check_allowed_scripts(rows, cfg)
    _check_managed_services(rows, cfg)
    _check_safety_switches(rows, cfg)
    _check_execution_provider(rows, cfg)
    _check_data_quality_gate(rows, cfg)
    _check_runtime_environment(rows, cfg)
    _check_runtime_paths(rows, cfg)
    _check_realtime_schema(rows, cfg)
    _check_dependency_imports(rows)
    _check_version_docs(rows, version)

    counts = {
        "pass": sum(1 for row in rows if row["status"] == "pass"),
        "warn": sum(1 for row in rows if row["status"] == "warn"),
        "fail": sum(1 for row in rows if row["status"] == "fail"),
    }
    status = "fail" if counts["fail"] else "pass"
    output_dir = project_root() / "reports" / "stability"
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": status,
        "version": version,
        "counts": counts,
        "checks": rows,
    }
    json_path = output_dir / "stability_report.json"
    csv_path = output_dir / "stability_checks.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "name", "status", "detail"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if status == "pass" else 1)


if __name__ == "__main__":
    main()
