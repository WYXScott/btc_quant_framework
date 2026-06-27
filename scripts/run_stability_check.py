from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, project_root, resolve_path


def _exists(path: str | Path) -> bool:
    return resolve_path(path).exists()


def _add(rows: list[dict[str, Any]], category: str, name: str, status: str, detail: str) -> None:
    rows.append({"category": category, "name": name, "status": status, "detail": detail})


def _check_required_files(rows: list[dict[str, Any]], version: str) -> None:
    required = [
        "README.md",
        "start_dashboard.bat",
        "config/config.yaml",
        "frontend/app.py",
        "docs/INDEX.md",
        "docs/SYSTEM_ARCHITECTURE.md",
        "docs/OPERATING_MODEL.md",
        "docs/EXTENSION_INTERFACES.md",
        "docs/ROADMAP.md",
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
        if script in seen:
            duplicates.add(str(script))
        seen.add(str(script))
        path = project_root() / "scripts" / str(script)
        _add(rows, "ui", str(script), "pass" if path.exists() else "fail", "allowed UI script exists")
    if duplicates:
        _add(rows, "ui", "duplicate_allowed_scripts", "warn", ", ".join(sorted(duplicates)))
    else:
        _add(rows, "ui", "duplicate_allowed_scripts", "pass", "no duplicates")


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
        "realtime_klines": {"exchange", "inst_id", "channel", "timestamp", "open", "high", "low", "close", "confirm"},
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
    _check_safety_switches(rows, cfg)
    _check_runtime_paths(rows, cfg)
    _check_realtime_schema(rows, cfg)
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
