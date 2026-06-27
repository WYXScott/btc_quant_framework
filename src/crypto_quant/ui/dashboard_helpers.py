from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from crypto_quant.config import project_root, resolve_path


@dataclass(frozen=True)
class FileStatus:
    path: str
    exists: bool
    size_bytes: int
    modified: str | None


def load_yaml(path: str | Path = "config/config.yaml") -> dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = project_root() / p
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def file_status(path: str | Path) -> FileStatus:
    p = Path(path)
    if not p.is_absolute():
        p = project_root() / p
    if not p.exists():
        return FileStatus(str(p.relative_to(project_root()) if p.is_relative_to(project_root()) else p), False, 0, None)
    stat = p.stat()
    modified = pd.Timestamp(stat.st_mtime, unit="s").strftime("%Y-%m-%d %H:%M:%S")
    return FileStatus(str(p.relative_to(project_root()) if p.is_relative_to(project_root()) else p), True, int(stat.st_size), modified)


def read_json(path: str | Path) -> dict[str, Any] | list[Any] | None:
    p = Path(path)
    if not p.is_absolute():
        p = project_root() / p
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_csv(path: str | Path, nrows: int | None = None) -> pd.DataFrame:
    p = Path(path)
    if not p.is_absolute():
        p = project_root() / p
    if not p.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(p, nrows=nrows)
    except Exception:
        return pd.DataFrame()


def read_parquet(path: str | Path, nrows: int | None = None) -> pd.DataFrame:
    p = Path(path)
    if not p.is_absolute():
        p = project_root() / p
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_parquet(p)
        if nrows is not None and len(df) > nrows:
            return df.tail(nrows)
        return df
    except Exception:
        return pd.DataFrame()


def sqlite_table_counts(db_path: str | Path) -> pd.DataFrame:
    p = Path(db_path)
    if not p.is_absolute():
        p = project_root() / p
    if not p.exists():
        return pd.DataFrame(columns=["table", "rows"])
    rows: list[dict[str, Any]] = []
    try:
        with sqlite3.connect(p) as conn:
            tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", conn)
            for name in tables["name"].tolist():
                try:
                    count = pd.read_sql_query(f'SELECT COUNT(*) AS n FROM "{name}"', conn)["n"].iloc[0]
                    rows.append({"table": name, "rows": int(count)})
                except Exception:
                    rows.append({"table": name, "rows": None})
    except Exception:
        pass
    return pd.DataFrame(rows)


def latest_sqlite_table(db_path: str | Path, table: str, limit: int = 100, order_by: str | None = None) -> pd.DataFrame:
    p = Path(db_path)
    if not p.is_absolute():
        p = project_root() / p
    if not p.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(p) as conn:
            cols = pd.read_sql_query(f'PRAGMA table_info("{table}")', conn)
            if cols.empty:
                return pd.DataFrame()
            col_names = set(cols["name"].tolist())
            if order_by is not None and order_by in col_names:
                order_clause = f' ORDER BY "{order_by}" DESC'
            elif "timestamp" in col_names:
                order_clause = ' ORDER BY "timestamp" DESC'
            elif "id" in col_names:
                order_clause = ' ORDER BY "id" DESC'
            else:
                order_clause = ""
            return pd.read_sql_query(f'SELECT * FROM "{table}"{order_clause} LIMIT {int(limit)}', conn)
    except Exception:
        return pd.DataFrame()


def collect_core_status(cfg: dict[str, Any]) -> pd.DataFrame:
    paths = [
        cfg.get("data", {}).get("raw_path", "data/raw/BTCUSDT_4h.parquet"),
        cfg.get("data", {}).get("feature_path", "data/processed/BTCUSDT_4h_features.parquet"),
        cfg.get("data", {}).get("dataset_path", "data/processed/BTCUSDT_4h_dataset.parquet"),
        cfg.get("model", {}).get("model_path", "models/btc_direction_model.joblib"),
        cfg.get("model", {}).get("feature_list_path", "models/btc_feature_columns.txt"),
        cfg.get("calibration", {}).get("calibrated_model_path", "models/btc_direction_model_calibrated.joblib"),
        "reports/calibration/calibration_metrics.json",
        "reports/signal_confidence/confidence_tier_table.csv",
        cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"),
        cfg.get("realtime", {}).get("database_path", "data/database/realtime_market.sqlite"),
        cfg.get("deployment", {}).get("health_report_path", "reports/deployment/health_report.json"),
        cfg.get("deployment", {}).get("status_report_path", "reports/deployment/runtime_status.json"),
        cfg.get("research", {}).get("research_report_path", "reports/research_report/research_report.html"),
        "reports/prelive_operator/prelive_operator_console.html",
        "reports/shadow_monitor/shadow_monitor_panel.html",
        "reports/operations/daily_operations_report.html",
        "reports/v3_0_operations_report/v3_0_operations_report.html",
    ]
    rows = [file_status(resolve_path(p)).__dict__ for p in paths]
    return pd.DataFrame(rows)


def safe_run_script(script_name: str, extra_args: list[str] | None = None, timeout_seconds: int = 900) -> tuple[int, str]:
    cfg = load_yaml()
    allowed = set(cfg.get("ui", {}).get("allowed_button_scripts", []))
    if script_name not in allowed:
        return 2, f"Blocked by UI safe-mode: {script_name} is not in ui.allowed_button_scripts."
    script_path = project_root() / "scripts" / script_name
    if not script_path.exists():
        return 2, f"Script not found: {script_path}"
    cmd = [sys.executable, str(script_path)] + list(extra_args or [])
    try:
        proc = subprocess.run(
            cmd,
            cwd=project_root(),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        stderr = exc.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        if stderr:
            output += "\n[stderr]\n" + stderr
        output += f"\n[ui]\nTimed out after {timeout_seconds} seconds: {' '.join(cmd)}"
        return 124, output.strip()
    except OSError as exc:
        return 125, f"Failed to start script: {exc!r}\nCommand: {' '.join(cmd)}"
    except Exception as exc:
        return 126, f"Unexpected UI runner error: {exc!r}\nCommand: {' '.join(cmd)}"
    output = (proc.stdout or "")
    if proc.stderr:
        output += "\n[stderr]\n" + proc.stderr
    return int(proc.returncode), output.strip()


def summarize_dataset(cfg: dict[str, Any]) -> dict[str, Any]:
    ds = read_parquet(cfg.get("data", {}).get("dataset_path", "data/processed/BTCUSDT_4h_dataset.parquet"))
    if ds.empty:
        return {"exists": False, "rows": 0, "columns": 0}
    out: dict[str, Any] = {"exists": True, "rows": int(len(ds)), "columns": int(len(ds.columns))}
    if isinstance(ds.index, pd.DatetimeIndex):
        out["start"] = str(ds.index.min())
        out["end"] = str(ds.index.max())
    if "label_up" in ds.columns:
        out["label_up_rate"] = float(ds["label_up"].mean())
    if "future_return" in ds.columns:
        out["future_return_mean"] = float(ds["future_return"].mean())
        out["future_return_std"] = float(ds["future_return"].std())
    return out


def summarize_model(cfg: dict[str, Any]) -> dict[str, Any]:
    model_status = file_status(resolve_path(cfg.get("model", {}).get("model_path", "models/btc_direction_model.joblib")))
    feature_status = file_status(resolve_path(cfg.get("model", {}).get("feature_list_path", "models/btc_feature_columns.txt")))
    out = {
        "model_exists": model_status.exists,
        "model_size_bytes": model_status.size_bytes,
        "model_modified": model_status.modified,
        "feature_list_exists": feature_status.exists,
        "feature_count": 0,
    }
    p = resolve_path(cfg.get("model", {}).get("feature_list_path", "models/btc_feature_columns.txt"))
    if p.exists():
        out["feature_count"] = len([line for line in p.read_text(encoding="utf-8").splitlines() if line.strip()])
    return out
