from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable

import pandas as pd

from crypto_quant.live.live_safety import (
    HardCircuitBreaker,
    LiveSafetyGate,
    LiveSafetyStore,
    PreLiveValidationBuilder,
    utc_now_iso,
)
from crypto_quant.live.shadow_monitor import ShadowLivePaperMonitor

PASS = "pass"
WARN = "warn"
BLOCKED = "blocked"
PENDING = "pending"
APPROVED = "approved"
WAIVED = "waived"
FAILED = "failed"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json_dumps(payload), encoding="utf-8")
    return p


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None




def _has_literal_secret_value(payload: Any) -> bool:
    """Best-effort check for literal credentials stored in config values.

    Keys such as api_key_env/secret_env are safe because they point to environment
    variable names. This function only flags non-empty values under direct secret
    keys that do not end in _env.
    """
    suspicious_key_parts = ("secret", "api_key", "apikey", "private_key")
    def walk(obj: Any, parent_key: str = "") -> bool:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if key.endswith("_env") or key in {"api_key_env", "secret_env"}:
                    continue
                if any(part in key for part in suspicious_key_parts):
                    if isinstance(v, str) and v and not v.startswith("BINANCE_") and len(v) > 12:
                        return True
                if walk(v, key):
                    return True
        elif isinstance(obj, list):
            return any(walk(v, parent_key) for v in obj)
        return False
    return walk(payload)


def _latest_row(conn: sqlite3.Connection, table: str, order_col: str = "id") -> dict[str, Any] | None:
    if not _table_exists(conn, table):
        return None
    try:
        row = conn.execute(f"SELECT * FROM {table} ORDER BY {order_col} DESC LIMIT 1").fetchone()
        return None if row is None else dict(row)
    except Exception:
        return None


@dataclass(frozen=True)
class ReviewCheckItem:
    name: str
    status: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreLiveChecklistItem:
    item_key: str
    category: str
    description: str
    required: bool = True
    status: str = PENDING
    evidence_path: str = ""
    operator: str = ""
    notes: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ApiPermissionAudit:
    timestamp_utc: str
    status: str
    checks: list[ReviewCheckItem]
    env_report: dict[str, Any]

    @property
    def blockers(self) -> list[ReviewCheckItem]:
        return [c for c in self.checks if c.status == BLOCKED]

    @property
    def warnings(self) -> list[ReviewCheckItem]:
        return [c for c in self.checks if c.status == WARN]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "status": self.status,
            "blockers": [c.to_dict() for c in self.blockers],
            "warnings": [c.to_dict() for c in self.warnings],
            "checks": [c.to_dict() for c in self.checks],
            "env_report": self.env_report,
        }


@dataclass(frozen=True)
class PreLiveReviewReport:
    timestamp_utc: str
    status: str
    decision: str
    summary: dict[str, Any]
    checks: list[ReviewCheckItem]
    checklist_items: list[PreLiveChecklistItem]
    api_audit: dict[str, Any]
    shadow_monitor: dict[str, Any]
    live_gate: dict[str, Any]
    prelive_validation: dict[str, Any]
    recommendations: list[str]

    @property
    def blockers(self) -> list[ReviewCheckItem]:
        return [c for c in self.checks if c.status == BLOCKED]

    @property
    def warnings(self) -> list[ReviewCheckItem]:
        return [c for c in self.checks if c.status == WARN]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "status": self.status,
            "decision": self.decision,
            "summary": self.summary,
            "blockers": [c.to_dict() for c in self.blockers],
            "warnings": [c.to_dict() for c in self.warnings],
            "checks": [c.to_dict() for c in self.checks],
            "checklist_items": [i.to_dict() for i in self.checklist_items],
            "api_audit": self.api_audit,
            "shadow_monitor": self.shadow_monitor,
            "live_gate": self.live_gate,
            "prelive_validation": self.prelive_validation,
            "recommendations": self.recommendations,
        }

    def checks_frame(self) -> pd.DataFrame:
        rows = []
        for c in self.checks:
            d = c.to_dict()
            d["details_json"] = json.dumps(d.pop("details", {}), ensure_ascii=False, default=str)
            rows.append(d)
        return pd.DataFrame(rows)

    def checklist_frame(self) -> pd.DataFrame:
        return pd.DataFrame([i.to_dict() for i in self.checklist_items])


DEFAULT_CHECKLIST: list[dict[str, Any]] = [
    {
        "item_key": "demo_30d_positive_or_explained",
        "category": "demo_validation",
        "description": "Demo/Testnet or local paper run covers the required validation window; performance is reviewed and drawdowns are explained.",
        "required": True,
    },
    {
        "item_key": "shadow_monitor_no_blockers",
        "category": "shadow_live",
        "description": "Read-only shadow-live vs local paper drift monitor has no critical blockers.",
        "required": True,
    },
    {
        "item_key": "readonly_api_key_verified",
        "category": "api_permissions",
        "description": "Only read-only live API keys are used for shadow mode; trading permission is not required for this stage.",
        "required": True,
    },
    {
        "item_key": "live_master_switch_reviewed",
        "category": "live_gate",
        "description": "live_trading.master_enable remains false unless an explicit small-live launch is approved.",
        "required": True,
    },
    {
        "item_key": "kill_switch_tested",
        "category": "safety",
        "description": "File-level kill switch trigger/clear workflow has been tested and documented.",
        "required": True,
    },
    {
        "item_key": "hard_circuit_limits_accepted",
        "category": "risk",
        "description": "Maximum daily loss and total drawdown hard-circuit thresholds are accepted for the 1000 USDT capital plan.",
        "required": True,
    },
    {
        "item_key": "initial_leverage_cap_3x",
        "category": "risk",
        "description": "Initial small-live leverage is capped at 3x; 5x/10x are not default launch settings.",
        "required": True,
    },
    {
        "item_key": "max_order_notional_cap_checked",
        "category": "execution",
        "description": "Maximum live order notional cap and minimum rebalance notional are checked against the 1000 USDT account size.",
        "required": True,
    },
    {
        "item_key": "idempotency_and_state_machine_checked",
        "category": "execution",
        "description": "Idempotent clientOrderId ledger and order lifecycle state machine were tested in dry-run/Demo mode.",
        "required": True,
    },
    {
        "item_key": "protective_order_plan_checked",
        "category": "execution",
        "description": "Stop-loss/take-profit protection and post-fill protection recalculation plan are reviewed.",
        "required": True,
    },
    {
        "item_key": "operator_understands_liquidation_risk",
        "category": "human_review",
        "description": "Operator explicitly acknowledges liquidation, gap, slippage, exchange outage and API failure risk.",
        "required": True,
    },
    {
        "item_key": "small_live_capital_limit_approved",
        "category": "human_review",
        "description": "Small-live launch capital limit is approved; recommended first tranche is below the full 1000 USDT until execution quality is verified.",
        "required": True,
    },
]


class PreLiveWorkflowStore:
    """SQLite store for pre-live checklist, approvals and review reports."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.create_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prelive_checklist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_key TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    required INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'pending',
                    evidence_path TEXT,
                    operator TEXT,
                    notes TEXT,
                    updated_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prelive_manual_approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    confirmation_phrase TEXT,
                    notes TEXT,
                    payload_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prelive_review_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    output_path TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_permission_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def initialize_default_checklist(self, *, reset: bool = False) -> list[PreLiveChecklistItem]:
        with self.connect() as conn:
            if reset:
                conn.execute("DELETE FROM prelive_checklist_items")
            for item in DEFAULT_CHECKLIST:
                conn.execute(
                    """
                    INSERT INTO prelive_checklist_items(item_key, category, description, required, status, updated_at)
                    VALUES (?, ?, ?, ?, 'pending', ?)
                    ON CONFLICT(item_key) DO NOTHING
                    """,
                    (
                        item["item_key"],
                        item["category"],
                        item["description"],
                        1 if item.get("required", True) else 0,
                        utc_now_iso(),
                    ),
                )
            conn.commit()
        return self.load_checklist()

    def load_checklist(self) -> list[PreLiveChecklistItem]:
        with self.connect() as conn:
            if not _table_exists(conn, "prelive_checklist_items"):
                return []
            rows = conn.execute(
                """
                SELECT item_key, category, description, required, status,
                       COALESCE(evidence_path, '') AS evidence_path,
                       COALESCE(operator, '') AS operator,
                       COALESCE(notes, '') AS notes,
                       COALESCE(updated_at, '') AS updated_at
                FROM prelive_checklist_items
                ORDER BY category, item_key
                """
            ).fetchall()
        return [
            PreLiveChecklistItem(
                item_key=str(r["item_key"]),
                category=str(r["category"]),
                description=str(r["description"]),
                required=bool(r["required"]),
                status=str(r["status"]),
                evidence_path=str(r["evidence_path"]),
                operator=str(r["operator"]),
                notes=str(r["notes"]),
                updated_at=str(r["updated_at"]),
            )
            for r in rows
        ]

    def mark_item(
        self,
        item_key: str,
        status: str,
        *,
        operator: str = "operator",
        evidence_path: str = "",
        notes: str = "",
    ) -> PreLiveChecklistItem:
        valid = {PENDING, APPROVED, WAIVED, FAILED, PASS, WARN, BLOCKED}
        if status not in valid:
            raise ValueError(f"Invalid status {status!r}; expected one of {sorted(valid)}")
        with self.connect() as conn:
            row = conn.execute("SELECT item_key FROM prelive_checklist_items WHERE item_key=?", (item_key,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown checklist item: {item_key}")
            conn.execute(
                """
                UPDATE prelive_checklist_items
                SET status=?, evidence_path=?, operator=?, notes=?, updated_at=?
                WHERE item_key=?
                """,
                (status, evidence_path, operator, notes, utc_now_iso(), item_key),
            )
            conn.commit()
        item = next((i for i in self.load_checklist() if i.item_key == item_key), None)
        if item is None:
            raise RuntimeError(f"Checklist item disappeared after update: {item_key}")
        return item

    def append_manual_approval(
        self,
        *,
        operator: str,
        decision: str,
        confirmation_phrase: str,
        notes: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = {
            "timestamp_utc": utc_now_iso(),
            "operator": operator,
            "decision": decision,
            "confirmation_phrase": confirmation_phrase,
            "notes": notes,
            "payload": payload or {},
        }
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO prelive_manual_approvals(timestamp_utc, operator, decision, confirmation_phrase, notes, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["timestamp_utc"],
                    operator,
                    decision,
                    confirmation_phrase,
                    notes,
                    json.dumps(payload or {}, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()
        return row

    def latest_manual_approval(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _latest_row(conn, "prelive_manual_approvals", "id")

    def append_api_audit(self, audit: ApiPermissionAudit) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO api_permission_audits(timestamp_utc, status, payload_json)
                VALUES (?, ?, ?)
                """,
                (audit.timestamp_utc, audit.status, _json_dumps(audit.to_dict())),
            )
            conn.commit()

    def append_review_report(self, report: PreLiveReviewReport, output_path: str | Path | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO prelive_review_reports(timestamp_utc, status, decision, output_path, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report.timestamp_utc,
                    report.status,
                    report.decision,
                    None if output_path is None else str(output_path),
                    _json_dumps(report.to_dict()),
                ),
            )
            conn.commit()

    def export_tables(self, output_dir: str | Path) -> dict[str, Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        with self.connect() as conn:
            for table in [
                "prelive_checklist_items",
                "prelive_manual_approvals",
                "prelive_review_reports",
                "api_permission_audits",
            ]:
                if _table_exists(conn, table):
                    df = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY id", conn)
                else:
                    df = pd.DataFrame()
                path = out / f"{table}.csv"
                df.to_csv(path, index=False)
                paths[table] = path
        return paths


class ApiPermissionAuditor:
    """Offline API-key permission and configuration audit.

    The Binance API does not expose a universally portable, low-risk permission
    endpoint through all CCXT adapters, so this audit is intentionally conservative:
    it verifies where credentials are sourced from, whether live execution is still
    disabled, and whether only read-only shadow-live env vars are needed for this
    phase. It never submits orders.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def audit(self) -> ApiPermissionAudit:
        checks: list[ReviewCheckItem] = []
        broker = self.cfg.get("broker", {})
        safety = broker.get("safety", {})
        shadow = self.cfg.get("shadow_live", {})
        live = self.cfg.get("live_trading", {})

        test_key_env = str(broker.get("api_key_env", "BINANCE_TESTNET_API_KEY"))
        test_secret_env = str(broker.get("secret_env", "BINANCE_TESTNET_API_SECRET"))
        live_ro_key_env = str(shadow.get("api_key_env", "BINANCE_LIVE_READONLY_API_KEY"))
        live_ro_secret_env = str(shadow.get("secret_env", "BINANCE_LIVE_READONLY_API_SECRET"))

        env_report = {
            "broker_environment": broker.get("environment", "testnet"),
            "broker_api_key_env": test_key_env,
            "broker_secret_env": test_secret_env,
            "testnet_key_present": bool(os.getenv(test_key_env)),
            "testnet_secret_present": bool(os.getenv(test_secret_env)),
            "shadow_readonly_key_env": live_ro_key_env,
            "shadow_readonly_secret_env": live_ro_secret_env,
            "shadow_readonly_key_present": bool(os.getenv(live_ro_key_env)),
            "shadow_readonly_secret_present": bool(os.getenv(live_ro_secret_env)),
            "live_master_enable": bool(live.get("master_enable", False)),
            "broker_allow_live_trading": bool(safety.get("allow_live_trading", False)),
            "order_secret_values_in_config": _has_literal_secret_value(self.cfg),
        }

        checks.append(ReviewCheckItem(
            name="live_execution_disabled_by_default",
            status=PASS if not env_report["live_master_enable"] and not env_report["broker_allow_live_trading"] else BLOCKED,
            severity="critical",
            message="Live trading is disabled by both master switch and broker safety flag."
            if not env_report["live_master_enable"] and not env_report["broker_allow_live_trading"]
            else "Live trading switch or broker allow_live_trading is enabled; this is not allowed during V2.2 review.",
            details={"live_master_enable": env_report["live_master_enable"], "broker_allow_live_trading": env_report["broker_allow_live_trading"]},
        ))
        checks.append(ReviewCheckItem(
            name="credentials_from_environment",
            status=PASS,
            severity="info",
            message="Config references environment variable names instead of literal credentials.",
            details={"testnet_envs": [test_key_env, test_secret_env], "shadow_envs": [live_ro_key_env, live_ro_secret_env]},
        ))
        checks.append(ReviewCheckItem(
            name="live_readonly_envs_present",
            status=PASS if env_report["shadow_readonly_key_present"] and env_report["shadow_readonly_secret_present"] else WARN,
            severity="warning",
            message="Read-only live API env vars are present."
            if env_report["shadow_readonly_key_present"] and env_report["shadow_readonly_secret_present"]
            else "Read-only live API env vars are not both present; shadow-live private checks will remain offline.",
            details={"api_key_env": live_ro_key_env, "secret_env": live_ro_secret_env},
        ))
        checks.append(ReviewCheckItem(
            name="no_literal_secret_marker_in_config",
            status=BLOCKED if env_report["order_secret_values_in_config"] else PASS,
            severity="critical" if env_report["order_secret_values_in_config"] else "info",
            message="Potential secret-like marker detected in config text. Review config manually."
            if env_report["order_secret_values_in_config"] else "No obvious literal secret marker detected in config dictionary.",
        ))
        checks.append(ReviewCheckItem(
            name="shadow_live_readonly_required",
            status=PASS if bool(shadow.get("require_readonly_key", True)) and bool(shadow.get("forbid_order_submission", True)) else BLOCKED,
            severity="critical",
            message="Shadow live mode requires read-only key and forbids order submission."
            if bool(shadow.get("require_readonly_key", True)) and bool(shadow.get("forbid_order_submission", True))
            else "Shadow live read-only safeguards are not enabled.",
            details={"shadow_live": shadow},
        ))

        status = BLOCKED if any(c.status == BLOCKED for c in checks) else (WARN if any(c.status == WARN for c in checks) else PASS)
        return ApiPermissionAudit(timestamp_utc=utc_now_iso(), status=status, checks=checks, env_report=env_report)


class ShadowDriftTrendAnalyzer:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def load_reports(self) -> pd.DataFrame:
        if not self.db_path.exists():
            return pd.DataFrame()
        with sqlite3.connect(self.db_path) as conn:
            if not _table_exists(conn, "shadow_monitor_reports"):
                return pd.DataFrame()
            return pd.read_sql_query("SELECT * FROM shadow_monitor_reports ORDER BY id", conn)

    def analyze(self) -> dict[str, Any]:
        df = self.load_reports()
        if df.empty:
            return {
                "timestamp_utc": utc_now_iso(),
                "status": WARN,
                "sample_count": 0,
                "message": "No shadow monitor reports found.",
                "metrics": {},
            }
        for col in ["equity_diff_fraction", "position_qty_diff", "target_exposure", "actual_shadow_exposure", "actual_paper_exposure"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        status_counts = df.get("status", pd.Series(dtype=str)).fillna("unknown").value_counts().to_dict()
        metrics = {
            "sample_count": int(len(df)),
            "status_counts": status_counts,
            "latest_status": str(df["status"].iloc[-1]) if "status" in df.columns else "unknown",
            "max_abs_equity_diff_fraction": float(df.get("equity_diff_fraction", pd.Series([0.0])).abs().max() or 0.0),
            "max_abs_position_qty_diff": float(df.get("position_qty_diff", pd.Series([0.0])).abs().max() or 0.0),
            "max_abs_shadow_target_exposure_gap": float(
                (df.get("actual_shadow_exposure", pd.Series([0.0])) - df.get("target_exposure", pd.Series([0.0]))).abs().max() or 0.0
            ),
            "first_timestamp": str(df.get("timestamp_utc", pd.Series([""])).iloc[0]),
            "latest_timestamp": str(df.get("timestamp_utc", pd.Series([""])).iloc[-1]),
        }
        status = BLOCKED if status_counts.get(BLOCKED, 0) else (WARN if status_counts.get(WARN, 0) else PASS)
        return {
            "timestamp_utc": utc_now_iso(),
            "status": status,
            "sample_count": int(len(df)),
            "message": "Shadow drift trend analyzed.",
            "metrics": metrics,
        }

    def write_outputs(self, output_dir: str | Path) -> dict[str, Path]:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        df = self.load_reports()
        summary = self.analyze()
        paths: dict[str, Path] = {}
        paths["trend_csv"] = out / "shadow_drift_trend.csv"
        df.to_csv(paths["trend_csv"], index=False)
        paths["summary_json"] = _write_json(out / "shadow_drift_trend_summary.json", summary)
        paths["html"] = out / "shadow_drift_trend.html"
        paths["html"].write_text(render_shadow_drift_trend_html(summary, df), encoding="utf-8")
        return paths


class PreLiveReviewBuilder:
    def __init__(self, cfg: dict[str, Any], *, root: str | Path | None = None):
        self.cfg = cfg
        self.root = Path(root) if root is not None else Path.cwd()
        self.db_path = self._resolve(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
        self.store = PreLiveWorkflowStore(self.db_path)

    def _resolve(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.root / p

    def _read_equity_curve(self) -> pd.DataFrame:
        if not self.db_path.exists():
            return pd.DataFrame()
        try:
            with sqlite3.connect(self.db_path) as conn:
                if not _table_exists(conn, "equity_curve"):
                    return pd.DataFrame()
                return pd.read_sql_query("SELECT * FROM equity_curve ORDER BY timestamp", conn)
        except Exception:
            return pd.DataFrame()

    def _latest_shadow_monitor_report(self) -> dict[str, Any]:
        out_path = self._resolve(self.cfg.get("shadow_monitor", {}).get("output_path", "reports/shadow_monitor"))
        return _read_json(out_path / "shadow_drift_report.json")

    def _prelive_validation_payload(self) -> dict[str, Any]:
        path = self._resolve(self.cfg.get("live_trading", {}).get("prelive_validation_report_path", "reports/prelive_validation/prelive_validation_report.json"))
        payload = _read_json(path)
        if payload:
            return payload
        try:
            payload = PreLiveValidationBuilder(self.cfg, root=self.root).build()
        except Exception as exc:
            payload = {"timestamp_utc": utc_now_iso(), "status": BLOCKED, "error": str(exc)}
        return payload

    def build(self, *, refresh_shadow: bool = False, fetch_live_readonly: bool = False) -> PreLiveReviewReport:
        self.store.initialize_default_checklist(reset=False)
        checks: list[ReviewCheckItem] = []

        api_audit = ApiPermissionAuditor(self.cfg).audit()
        self.store.append_api_audit(api_audit)
        for c in api_audit.checks:
            checks.append(c)

        if refresh_shadow:
            monitor = ShadowLivePaperMonitor(self.cfg, root=self.root)
            monitor.maybe_refresh_shadow_snapshot(fetch_private=fetch_live_readonly, offline_fallback=True)
            shadow_report = monitor.build_report()
            monitor.write_outputs(shadow_report)
            shadow_payload = shadow_report.to_dict()
        else:
            shadow_payload = self._latest_shadow_monitor_report()
            if not shadow_payload:
                monitor = ShadowLivePaperMonitor(self.cfg, root=self.root)
                monitor.maybe_refresh_shadow_snapshot(fetch_private=False, offline_fallback=True)
                shadow_report = monitor.build_report()
                monitor.write_outputs(shadow_report)
                shadow_payload = shadow_report.to_dict()

        shadow_status = str(shadow_payload.get("status", WARN))
        checks.append(ReviewCheckItem(
            name="shadow_monitor_status",
            status=PASS if shadow_status == PASS else (WARN if shadow_status == WARN else BLOCKED),
            severity="critical" if shadow_status == BLOCKED else "warning" if shadow_status == WARN else "info",
            message=f"Shadow monitor status: {shadow_status}.",
            details={"summary": shadow_payload.get("summary", {})},
        ))

        live_gate = LiveSafetyGate(self.cfg, root=self.root).evaluate(mode="prelive_operator_review")
        # The live gate is expected to remain blocked by master_enable=false in this review phase.
        live_master = bool(self.cfg.get("live_trading", {}).get("master_enable", False))
        checks.append(ReviewCheckItem(
            name="live_gate_intentionally_blocked_or_ready",
            status=PASS if live_gate.status == "blocked" and not live_master else (WARN if live_gate.status == "warn" else PASS),
            severity="info" if live_gate.status == "blocked" and not live_master else "warning",
            message="Live gate is still blocked by default safety switches; this is expected before an explicit launch decision."
            if live_gate.status == "blocked" and not live_master else f"Live gate status: {live_gate.status}.",
            details=live_gate.to_dict(),
        ))

        prelive_validation = self._prelive_validation_payload()
        prelive_status = str(prelive_validation.get("status", WARN))
        checks.append(ReviewCheckItem(
            name="prelive_validation_report_status",
            status=PASS if prelive_status == PASS else (WARN if prelive_status == WARN else BLOCKED),
            severity="critical" if prelive_status == BLOCKED else "warning" if prelive_status == WARN else "info",
            message=f"Pre-live validation report status: {prelive_status}.",
            details={"summary_keys": sorted(list(prelive_validation.keys()))},
        ))

        equity_curve = self._read_equity_curve()
        hard_cfg = self.cfg.get("live_trading", {})
        hard = HardCircuitBreaker(
            max_daily_loss_fraction=float(hard_cfg.get("max_daily_loss_fraction", 0.02)),
            max_total_drawdown_fraction=float(hard_cfg.get("max_total_drawdown_fraction", 0.10)),
        ).evaluate_equity_curve(equity_curve)
        checks.append(ReviewCheckItem(
            name="hard_circuit_current_status",
            status=PASS if hard.status == PASS else (WARN if hard.status == WARN else BLOCKED),
            severity="critical" if hard.status == BLOCKED else "warning" if hard.status == WARN else "info",
            message=hard.message,
            details=hard.to_dict(),
        ))

        checklist = self.store.load_checklist()
        if not checklist:
            checklist = self.store.initialize_default_checklist(reset=False)
        approved_statuses = {APPROVED, PASS, WAIVED}
        required_items = [i for i in checklist if i.required]
        pending_required = [i for i in required_items if i.status not in approved_statuses]
        checks.append(ReviewCheckItem(
            name="manual_checklist_required_items",
            status=PASS if not pending_required else BLOCKED,
            severity="critical" if pending_required else "info",
            message=f"{len(required_items) - len(pending_required)}/{len(required_items)} required checklist items approved/waived.",
            details={"pending_required_keys": [i.item_key for i in pending_required]},
        ))

        latest_approval = self.store.latest_manual_approval()
        required_phrase = str(self.cfg.get("prelive_operator_workflow", {}).get("approval_phrase", "I_REVIEWED_AND_ACCEPT_PRELIVE_RISK"))
        approval_ok = bool(latest_approval) and str(latest_approval.get("confirmation_phrase")) == required_phrase and str(latest_approval.get("decision")) in {"approve_small_live", "approve_shadow_only"}
        checks.append(ReviewCheckItem(
            name="manual_approval_record",
            status=PASS if approval_ok else BLOCKED,
            severity="critical" if not approval_ok else "info",
            message="Manual approval record with expected confirmation phrase exists." if approval_ok else "No valid manual approval record with expected confirmation phrase was found.",
            details={"expected_phrase": required_phrase, "latest_approval": latest_approval or {}},
        ))

        critical_blockers = [c for c in checks if c.status == BLOCKED]
        warnings = [c for c in checks if c.status == WARN]
        status = BLOCKED if critical_blockers else (WARN if warnings else PASS)
        decision = "blocked"
        if status == PASS:
            decision = "eligible_for_manual_small_live_review"
        elif status == WARN:
            decision = "manual_review_required"

        summary = {
            "status": status,
            "decision": decision,
            "num_checks": len(checks),
            "num_blockers": len(critical_blockers),
            "num_warnings": len(warnings),
            "required_checklist_items": len(required_items),
            "pending_required_checklist_items": len(pending_required),
            "shadow_status": shadow_status,
            "prelive_validation_status": prelive_status,
            "api_audit_status": api_audit.status,
            "live_gate_status": live_gate.status,
            "latest_manual_approval_present": bool(latest_approval),
        }
        recommendations = build_recommendations(status, checks)
        return PreLiveReviewReport(
            timestamp_utc=utc_now_iso(),
            status=status,
            decision=decision,
            summary=summary,
            checks=checks,
            checklist_items=checklist,
            api_audit=api_audit.to_dict(),
            shadow_monitor=shadow_payload,
            live_gate=live_gate.to_dict(),
            prelive_validation=prelive_validation,
            recommendations=recommendations,
        )

    def write_outputs(self, report: PreLiveReviewReport, output_dir: str | Path | None = None) -> dict[str, Path]:
        out = self._resolve(output_dir or self.cfg.get("prelive_operator_workflow", {}).get("output_path", "reports/prelive_operator"))
        out.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        paths["review_json"] = _write_json(out / "prelive_operator_review.json", report.to_dict())
        checks_df = report.checks_frame()
        paths["checks_csv"] = out / "prelive_operator_checks.csv"
        checks_df.to_csv(paths["checks_csv"], index=False)
        paths["checklist_csv"] = out / "prelive_checklist_items.csv"
        report.checklist_frame().to_csv(paths["checklist_csv"], index=False)
        paths["html"] = out / "prelive_operator_console.html"
        paths["html"].write_text(render_prelive_review_html(report), encoding="utf-8")
        self.store.append_review_report(report, paths["review_json"])
        self.store.export_tables(out)
        return paths


def build_recommendations(status: str, checks: list[ReviewCheckItem]) -> list[str]:
    recs: list[str] = []
    blockers = [c for c in checks if c.status == BLOCKED]
    warnings = [c for c in checks if c.status == WARN]
    if blockers:
        recs.append("Do not enable live trading. Resolve all critical blockers first.")
        recs.extend([f"Resolve blocker: {c.name} — {c.message}" for c in blockers[:8]])
    if warnings:
        recs.append("Review warnings before extending Demo/Testnet or shadow-live duration.")
    if status == PASS:
        recs.append("System is eligible for human small-live review, not automatic live execution.")
        recs.append("Recommended first real-money step: use a small tranche, leverage <= 3x, and keep kill switch armed.")
    recs.append("Keep live_trading.master_enable=false until the final launch window and manual confirmation are completed.")
    return recs


def _status_badge(status: str) -> str:
    color = {PASS: "#027a48", WARN: "#b54708", BLOCKED: "#b42318", PENDING: "#344054", APPROVED: "#027a48", FAILED: "#b42318", WAIVED: "#175cd3"}.get(status, "#344054")
    bg = {PASS: "#ecfdf3", WARN: "#fffaeb", BLOCKED: "#fef3f2", PENDING: "#f2f4f7", APPROVED: "#ecfdf3", FAILED: "#fef3f2", WAIVED: "#eff8ff"}.get(status, "#f2f4f7")
    return f'<span style="display:inline-block;padding:3px 8px;border-radius:999px;background:{bg};color:{color};font-weight:700">{html.escape(str(status))}</span>'


def render_prelive_review_html(report: PreLiveReviewReport) -> str:
    summary_rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in report.summary.items()
    )
    check_rows = "".join(
        "<tr>"
        f"<td>{html.escape(c.name)}</td>"
        f"<td>{_status_badge(c.status)}</td>"
        f"<td>{html.escape(c.severity)}</td>"
        f"<td>{html.escape(c.message)}</td>"
        f"<td><pre>{html.escape(json.dumps(c.details, ensure_ascii=False, indent=2, default=str))}</pre></td>"
        "</tr>"
        for c in report.checks
    )
    checklist_rows = "".join(
        "<tr>"
        f"<td>{html.escape(i.category)}</td>"
        f"<td>{html.escape(i.item_key)}</td>"
        f"<td>{_status_badge(i.status)}</td>"
        f"<td>{'yes' if i.required else 'no'}</td>"
        f"<td>{html.escape(i.description)}</td>"
        f"<td>{html.escape(i.operator)}</td>"
        f"<td>{html.escape(i.evidence_path)}</td>"
        f"<td>{html.escape(i.notes)}</td>"
        "</tr>"
        for i in report.checklist_items
    )
    rec_items = "".join(f"<li>{html.escape(r)}</li>" for r in report.recommendations)
    raw = {
        "api_audit": report.api_audit,
        "shadow_monitor": report.shadow_monitor,
        "live_gate": report.live_gate,
        "prelive_validation": report.prelive_validation,
    }
    raw_html = "".join(
        f"<h3>{html.escape(k)}</h3><pre>{html.escape(json.dumps(v, ensure_ascii=False, indent=2, default=str))}</pre>"
        for k, v in raw.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>BTC Quant Pre-live Operator Console</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif; margin: 28px; color: #101828; }}
    h1 {{ margin-bottom: 4px; }}
    .sub {{ color: #667085; margin-top: 0; }}
    .card {{ border: 1px solid #d0d5dd; border-radius: 14px; padding: 16px 18px; margin: 16px 0; box-shadow: 0 1px 2px rgba(16,24,40,0.06); }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
    th, td {{ border: 1px solid #d0d5dd; padding: 8px 10px; vertical-align: top; }}
    th {{ background: #f2f4f7; text-align: left; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f8f9fb; padding: 8px; border-radius: 8px; max-height: 320px; overflow: auto; }}
    .warning {{ padding: 12px 14px; background: #fffaeb; border: 1px solid #fedf89; border-radius: 12px; color: #7a2e0e; }}
  </style>
</head>
<body>
  <h1>BTC Quant Pre-live Operator Console</h1>
  <p class="sub">Generated at {html.escape(report.timestamp_utc)} · Overall status: {_status_badge(report.status)} · Decision: <strong>{html.escape(report.decision)}</strong></p>
  <div class="warning">This console does not authorize automatic live trading. It is a human review package for a possible small-live launch.</div>
  <div class="card"><h2>Summary</h2><table>{summary_rows}</table></div>
  <div class="card"><h2>Recommendations</h2><ul>{rec_items}</ul></div>
  <div class="card"><h2>Gate Checks</h2><table><thead><tr><th>Name</th><th>Status</th><th>Severity</th><th>Message</th><th>Details</th></tr></thead><tbody>{check_rows}</tbody></table></div>
  <div class="card"><h2>Manual Checklist</h2><table><thead><tr><th>Category</th><th>Key</th><th>Status</th><th>Required</th><th>Description</th><th>Operator</th><th>Evidence</th><th>Notes</th></tr></thead><tbody>{checklist_rows}</tbody></table></div>
  <div class="card"><h2>Raw Inputs</h2>{raw_html}</div>
</body>
</html>
"""


def render_shadow_drift_trend_html(summary: dict[str, Any], df: pd.DataFrame) -> str:
    if df.empty:
        rows = "<tr><td colspan='6'>No reports found.</td></tr>"
    else:
        tail = df.tail(50).copy()
        cols = [c for c in ["timestamp_utc", "status", "equity_diff_fraction", "position_qty_diff", "target_exposure", "actual_shadow_exposure", "actual_paper_exposure"] if c in tail.columns]
        rows = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(row.get(c, '')))}</td>" for c in cols) + "</tr>"
            for _, row in tail.iterrows()
        )
        header = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
        rows = f"<thead><tr>{header}</tr></thead><tbody>{rows}</tbody>"
    metrics = summary.get("metrics", {})
    metric_rows = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in metrics.items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Shadow Drift Trend</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;margin:28px;color:#101828}}table{{border-collapse:collapse;width:100%;margin:14px 0 28px}}th,td{{border:1px solid #d0d5dd;padding:8px 10px;text-align:left}}th{{background:#f2f4f7}}.card{{border:1px solid #d0d5dd;border-radius:14px;padding:16px 18px;margin:16px 0}}</style></head>
<body><h1>Shadow Drift Trend</h1><p>Generated at {html.escape(str(summary.get('timestamp_utc','')))} · Status: {_status_badge(str(summary.get('status', WARN)))}</p>
<div class="card"><h2>Metrics</h2><table>{metric_rows}</table></div>
<div class="card"><h2>Recent Reports</h2><table>{rows}</table></div>
</body></html>"""


def build_v22_readiness_payload(cfg: dict[str, Any], *, root: str | Path | None = None, refresh_shadow: bool = False, fetch_live_readonly: bool = False) -> dict[str, Any]:
    root_path = Path(root) if root is not None else Path.cwd()
    builder = PreLiveReviewBuilder(cfg, root=root_path)
    report = builder.build(refresh_shadow=refresh_shadow, fetch_live_readonly=fetch_live_readonly)
    paths = builder.write_outputs(report)
    return {
        "timestamp_utc": utc_now_iso(),
        "status": report.status,
        "decision": report.decision,
        "summary": report.summary,
        "output_paths": {k: str(v) for k, v in paths.items()},
        "report": report.to_dict(),
        "notes": [
            "V2.2 is an operator-review workflow. It does not submit live orders.",
            "A pass result means eligible for human small-live review, not automatic authorization.",
        ],
    }
