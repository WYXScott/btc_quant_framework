from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from crypto_quant.config import resolve_path
from crypto_quant.live.live_safety import LiveSafetyGate, LiveSafetyStore, ShadowLiveReadOnlyClient, utc_now_iso


PASS = "pass"
WARN = "warn"
BLOCKED = "blocked"


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


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=True)
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except Exception:
        return None


def _age_minutes(value: Any) -> float | None:
    ts = _parse_ts(value)
    if ts is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 60.0)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _latest_row(conn: sqlite3.Connection, table: str, order_col: str = "id") -> dict[str, Any] | None:
    if not _table_exists(conn, table):
        return None
    try:
        row = conn.execute(f"SELECT * FROM {table} ORDER BY {order_col} DESC LIMIT 1").fetchone()
        return None if row is None else dict(row)
    except Exception:
        return None


@dataclass(frozen=True)
class DriftCheckItem:
    name: str
    status: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccountComparisonReport:
    timestamp_utc: str
    status: str
    summary: dict[str, Any]
    checks: list[DriftCheckItem]
    shadow_snapshot: dict[str, Any]
    paper_snapshot: dict[str, Any]
    target_snapshot: dict[str, Any]
    live_gate_snapshot: dict[str, Any]

    @property
    def blockers(self) -> list[DriftCheckItem]:
        return [c for c in self.checks if c.status == BLOCKED]

    @property
    def warnings(self) -> list[DriftCheckItem]:
        return [c for c in self.checks if c.status == WARN]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "status": self.status,
            "summary": self.summary,
            "blockers": [b.to_dict() for b in self.blockers],
            "warnings": [w.to_dict() for w in self.warnings],
            "checks": [c.to_dict() for c in self.checks],
            "shadow_snapshot": self.shadow_snapshot,
            "paper_snapshot": self.paper_snapshot,
            "target_snapshot": self.target_snapshot,
            "live_gate_snapshot": self.live_gate_snapshot,
        }

    def checks_frame(self) -> pd.DataFrame:
        rows = []
        for c in self.checks:
            d = c.to_dict()
            d["details_json"] = json.dumps(d.pop("details", {}), ensure_ascii=False, default=str)
            rows.append(d)
        return pd.DataFrame(rows)


class ShadowMonitorStore:
    """SQLite persistence for shadow-live vs paper drift reports.

    The monitor intentionally writes to the same paper/demo database so all
    deployment bundles can export a single auditable state file.
    """

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
                CREATE TABLE IF NOT EXISTS shadow_monitor_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    status TEXT NOT NULL,
                    shadow_equity REAL,
                    paper_equity REAL,
                    equity_diff_fraction REAL,
                    shadow_position_qty REAL,
                    paper_position_qty REAL,
                    position_qty_diff REAL,
                    target_exposure REAL,
                    actual_shadow_exposure REAL,
                    actual_paper_exposure REAL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shadow_monitor_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_timestamp_utc TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    severity TEXT,
                    message TEXT,
                    details_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def latest_shadow_snapshot(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _latest_row(conn, "shadow_live_snapshots", "id")

    def latest_paper_account(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _latest_row(conn, "account_state", "id")

    def latest_equity_curve(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _latest_row(conn, "equity_curve", "id")

    def latest_target_decision(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            return _latest_row(conn, "target_exposure_decisions", "id")

    def pending_open_order_count(self) -> int:
        with self.connect() as conn:
            if not _table_exists(conn, "pending_orders"):
                return 0
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) FROM pending_orders
                    WHERE lower(COALESCE(status, '')) NOT IN ('filled', 'canceled', 'cancelled', 'expired', 'rejected')
                    """
                ).fetchone()
                return int(row[0] or 0)
            except Exception:
                return 0

    def append_report(self, report: AccountComparisonReport) -> None:
        s = report.summary
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO shadow_monitor_reports(
                    timestamp_utc, status, shadow_equity, paper_equity, equity_diff_fraction,
                    shadow_position_qty, paper_position_qty, position_qty_diff,
                    target_exposure, actual_shadow_exposure, actual_paper_exposure, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.timestamp_utc,
                    report.status,
                    _safe_float(s.get("shadow_equity_usdt"), 0.0),
                    _safe_float(s.get("paper_equity_usdt"), 0.0),
                    _safe_float(s.get("equity_diff_fraction"), 0.0),
                    _safe_float(s.get("shadow_position_qty"), 0.0),
                    _safe_float(s.get("paper_position_qty"), 0.0),
                    _safe_float(s.get("position_qty_diff"), 0.0),
                    _safe_float(s.get("target_exposure"), 0.0),
                    _safe_float(s.get("actual_shadow_exposure"), 0.0),
                    _safe_float(s.get("actual_paper_exposure"), 0.0),
                    _json_dumps(report.to_dict()),
                ),
            )
            for c in report.checks:
                conn.execute(
                    """
                    INSERT INTO shadow_monitor_checks(report_timestamp_utc, name, status, severity, message, details_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.timestamp_utc,
                        c.name,
                        c.status,
                        c.severity,
                        c.message,
                        json.dumps(c.details, ensure_ascii=False, default=str),
                    ),
                )
            conn.commit()


class ShadowLivePaperMonitor:
    """Compare read-only live snapshots with local paper/ensemble state."""

    def __init__(self, cfg: dict[str, Any], *, root: str | Path | None = None):
        self.cfg = cfg
        self.root = Path(root) if root is not None else Path.cwd()
        self.monitor_cfg = cfg.get("shadow_monitor", {})
        self.db_path = self._resolve(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
        self.store = ShadowMonitorStore(self.db_path)

    def _resolve(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.root / p

    def _normalize_shadow(self, row: dict[str, Any] | None) -> dict[str, Any]:
        if not row:
            return {
                "available": False,
                "timestamp_utc": None,
                "source": "missing",
                "dry_run": True,
                "equity_usdt": 0.0,
                "position_qty": 0.0,
                "open_order_count": 0,
                "last_price": None,
            }
        payload = {}
        raw_json = row.get("payload_json")
        if raw_json:
            try:
                payload = json.loads(raw_json)
            except Exception:
                payload = {}
        payload.update({k: v for k, v in row.items() if k != "payload_json" and v is not None})
        return {
            "available": True,
            "timestamp_utc": payload.get("timestamp_utc") or row.get("timestamp_utc"),
            "source": payload.get("source") or "shadow_live_snapshots",
            "dry_run": bool(payload.get("dry_run", row.get("dry_run", 1))),
            "symbol": payload.get("symbol"),
            "equity_usdt": _safe_float(payload.get("equity_usdt"), 0.0),
            "position_qty": _safe_float(payload.get("position_qty"), 0.0),
            "entry_price": payload.get("entry_price"),
            "last_price": payload.get("last_price"),
            "open_order_count": _safe_int(payload.get("open_order_count"), 0),
            "age_minutes": _age_minutes(payload.get("timestamp_utc") or row.get("timestamp_utc")),
            "payload": payload,
        }

    def _normalize_paper(self, account: dict[str, Any] | None, equity_row: dict[str, Any] | None) -> dict[str, Any]:
        account = account or {}
        equity_row = equity_row or {}
        price = equity_row.get("price")
        timestamp = equity_row.get("timestamp") or account.get("last_update_timestamp") or account.get("updated_at")
        return {
            "available": bool(account),
            "timestamp_utc": timestamp,
            "equity_usdt": _safe_float(account.get("equity"), _safe_float(equity_row.get("equity"), 0.0)),
            "cash_usdt": _safe_float(account.get("cash"), 0.0),
            "position_qty": _safe_float(account.get("position_qty"), 0.0),
            "entry_price": account.get("entry_price"),
            "last_price": _safe_float(price, 0.0) if price is not None else None,
            "leverage": _safe_float(account.get("leverage"), 0.0),
            "realized_pnl": _safe_float(account.get("realized_pnl"), 0.0),
            "open_order_count": self.store.pending_open_order_count(),
            "age_minutes": _age_minutes(timestamp),
            "raw_account": account,
            "raw_equity": equity_row,
        }

    def _normalize_target(self, target: dict[str, Any] | None) -> dict[str, Any]:
        target = target or {}
        return {
            "available": bool(target),
            "timestamp_utc": target.get("timestamp"),
            "price": _safe_float(target.get("price"), 0.0),
            "ensemble_score": _safe_float(target.get("ensemble_score"), 0.0),
            "signal": _safe_int(target.get("signal"), 0),
            "target_exposure": _safe_float(target.get("target_exposure"), 0.0),
            "target_notional": _safe_float(target.get("target_notional"), 0.0),
            "action": target.get("action"),
            "reason": target.get("reason"),
            "age_minutes": _age_minutes(target.get("timestamp")),
            "raw": target,
        }

    @staticmethod
    def _actual_exposure(position_qty: float, price: float | None, equity: float) -> float:
        if equity <= 0 or price is None or price <= 0:
            return 0.0
        return abs(float(position_qty)) * float(price) / float(equity)

    def _resolve_reference_price(self, shadow: dict[str, Any], paper: dict[str, Any], target: dict[str, Any]) -> float | None:
        for value in [shadow.get("last_price"), paper.get("last_price"), target.get("price")]:
            f = _safe_float(value, 0.0)
            if f > 0:
                return f
        return None

    def maybe_refresh_shadow_snapshot(self, *, fetch_private: bool = False, offline_fallback: bool = True) -> dict[str, Any] | None:
        """Optionally query/store a fresh shadow snapshot before comparison."""
        client = ShadowLiveReadOnlyClient(self.cfg)
        if fetch_private:
            snapshot = client.fetch_private_snapshot()
            LiveSafetyStore(self.db_path).append_shadow_snapshot(snapshot)
            return snapshot
        if offline_fallback and self.store.latest_shadow_snapshot() is None:
            snapshot = client.offline_snapshot()
            LiveSafetyStore(self.db_path).append_shadow_snapshot(snapshot)
            return snapshot
        return None

    def build_report(self) -> AccountComparisonReport:
        shadow = self._normalize_shadow(self.store.latest_shadow_snapshot())
        paper = self._normalize_paper(self.store.latest_paper_account(), self.store.latest_equity_curve())
        target = self._normalize_target(self.store.latest_target_decision())
        reference_price = self._resolve_reference_price(shadow, paper, target)
        checks: list[DriftCheckItem] = []

        max_shadow_age = float(self.monitor_cfg.get("max_shadow_snapshot_age_minutes", 60.0))
        max_paper_age = float(self.monitor_cfg.get("max_paper_state_age_minutes", 60.0))
        max_target_age = float(self.monitor_cfg.get("max_target_age_minutes", 240.0))
        qty_tolerance = float(self.monitor_cfg.get("qty_tolerance", 1e-8))
        equity_tol = float(self.monitor_cfg.get("equity_tolerance_fraction", 0.05))
        exposure_tol = float(self.monitor_cfg.get("exposure_tolerance_abs", 0.10))
        allow_offline_shadow = bool(self.monitor_cfg.get("allow_offline_shadow_snapshot", True))

        if not shadow["available"]:
            checks.append(DriftCheckItem(
                name="shadow_snapshot_available",
                status=BLOCKED,
                severity="critical",
                message="No shadow-live snapshot is available. Run shadow_live_readonly_check.py or shadow_drift_check.py.",
            ))
        else:
            is_offline = bool(shadow.get("dry_run")) or str(shadow.get("source", "")).startswith("offline")
            checks.append(DriftCheckItem(
                name="shadow_snapshot_source",
                status=WARN if is_offline and not allow_offline_shadow else PASS,
                severity="warning" if is_offline else "info",
                message="Shadow snapshot is offline/dry-run." if is_offline else "Shadow snapshot comes from a private read-only source.",
                details={"source": shadow.get("source"), "dry_run": shadow.get("dry_run")},
            ))
            age = shadow.get("age_minutes")
            checks.append(DriftCheckItem(
                name="shadow_snapshot_freshness",
                status=WARN if age is None or age > max_shadow_age else PASS,
                severity="warning" if age is None or age > max_shadow_age else "info",
                message=f"Shadow snapshot age is {age if age is not None else 'unknown'} minutes; max={max_shadow_age}.",
                details={"age_minutes": age, "max_minutes": max_shadow_age},
            ))

        if not paper["available"]:
            checks.append(DriftCheckItem(
                name="paper_account_available",
                status=BLOCKED,
                severity="critical",
                message="No local paper account_state is available. Run paper_init.py first.",
            ))
        else:
            age = paper.get("age_minutes")
            checks.append(DriftCheckItem(
                name="paper_state_freshness",
                status=WARN if age is None or age > max_paper_age else PASS,
                severity="warning" if age is None or age > max_paper_age else "info",
                message=f"Paper state age is {age if age is not None else 'unknown'} minutes; max={max_paper_age}.",
                details={"age_minutes": age, "max_minutes": max_paper_age},
            ))

        if not target["available"]:
            checks.append(DriftCheckItem(
                name="target_exposure_available",
                status=WARN,
                severity="warning",
                message="No ensemble target_exposure decision is available. Run paper_ensemble_once.py or paper_ensemble_replay_dataset.py.",
            ))
        else:
            age = target.get("age_minutes")
            checks.append(DriftCheckItem(
                name="target_exposure_freshness",
                status=WARN if age is None or age > max_target_age else PASS,
                severity="warning" if age is None or age > max_target_age else "info",
                message=f"Target exposure age is {age if age is not None else 'unknown'} minutes; max={max_target_age}.",
                details={"age_minutes": age, "max_minutes": max_target_age},
            ))

        paper_equity = _safe_float(paper.get("equity_usdt"), 0.0)
        shadow_equity = _safe_float(shadow.get("equity_usdt"), 0.0)
        paper_qty = _safe_float(paper.get("position_qty"), 0.0)
        shadow_qty = _safe_float(shadow.get("position_qty"), 0.0)
        qty_diff = shadow_qty - paper_qty
        equity_diff_frac = 0.0 if max(abs(paper_equity), 1e-12) <= 1e-12 else (shadow_equity - paper_equity) / paper_equity

        if shadow["available"] and paper["available"]:
            checks.append(DriftCheckItem(
                name="equity_drift",
                status=WARN if abs(equity_diff_frac) > equity_tol else PASS,
                severity="warning" if abs(equity_diff_frac) > equity_tol else "info",
                message=f"Shadow vs paper equity drift: {equity_diff_frac:.4%}; tolerance={equity_tol:.2%}.",
                details={"shadow_equity": shadow_equity, "paper_equity": paper_equity, "diff_fraction": equity_diff_frac},
            ))
            checks.append(DriftCheckItem(
                name="position_qty_drift",
                status=WARN if abs(qty_diff) > qty_tolerance else PASS,
                severity="warning" if abs(qty_diff) > qty_tolerance else "info",
                message=f"Shadow vs paper position qty drift: {qty_diff:.10f}; tolerance={qty_tolerance}.",
                details={"shadow_qty": shadow_qty, "paper_qty": paper_qty, "diff_qty": qty_diff},
            ))

        actual_shadow_exposure = self._actual_exposure(shadow_qty, reference_price, max(shadow_equity, 1e-12))
        actual_paper_exposure = self._actual_exposure(paper_qty, reference_price, max(paper_equity, 1e-12))
        target_exposure = _safe_float(target.get("target_exposure"), 0.0)

        if target["available"] and reference_price is not None:
            shadow_target_gap = actual_shadow_exposure - target_exposure
            paper_target_gap = actual_paper_exposure - target_exposure
            checks.append(DriftCheckItem(
                name="shadow_vs_target_exposure",
                status=WARN if abs(shadow_target_gap) > exposure_tol else PASS,
                severity="warning" if abs(shadow_target_gap) > exposure_tol else "info",
                message=f"Shadow actual exposure minus target: {shadow_target_gap:.4f}; tolerance={exposure_tol}.",
                details={"actual_shadow_exposure": actual_shadow_exposure, "target_exposure": target_exposure, "gap": shadow_target_gap},
            ))
            checks.append(DriftCheckItem(
                name="paper_vs_target_exposure",
                status=WARN if abs(paper_target_gap) > exposure_tol else PASS,
                severity="warning" if abs(paper_target_gap) > exposure_tol else "info",
                message=f"Paper actual exposure minus target: {paper_target_gap:.4f}; tolerance={exposure_tol}.",
                details={"actual_paper_exposure": actual_paper_exposure, "target_exposure": target_exposure, "gap": paper_target_gap},
            ))

        if _safe_int(shadow.get("open_order_count"), 0) > 0 and abs(shadow_qty) <= qty_tolerance:
            checks.append(DriftCheckItem(
                name="shadow_open_orders_when_flat",
                status=WARN,
                severity="warning",
                message="Shadow/live account appears flat but still has open orders. Check for stale reduce-only or leftover orders.",
                details={"open_order_count": shadow.get("open_order_count"), "shadow_qty": shadow_qty},
            ))

        live_gate = LiveSafetyGate(self.cfg, root=self.root).evaluate(mode="shadow_monitor")
        live_gate_dict = live_gate.to_dict()
        checks.append(DriftCheckItem(
            name="live_safety_gate_state",
            status=PASS if live_gate.status in {"blocked", "pass", "warn"} else WARN,
            severity="info",
            message=f"Live gate status is {live_gate.status}. Blocked is expected while system is in shadow/demo mode.",
            details={"live_gate_status": live_gate.status, "blocker_count": len(live_gate.blockers), "warning_count": len(live_gate.warnings)},
        ))

        blocked = [c for c in checks if c.status == BLOCKED]
        warns = [c for c in checks if c.status == WARN]
        status = BLOCKED if blocked else (WARN if warns else PASS)
        summary = {
            "reference_price": reference_price,
            "shadow_equity_usdt": shadow_equity,
            "paper_equity_usdt": paper_equity,
            "equity_diff_fraction": equity_diff_frac,
            "shadow_position_qty": shadow_qty,
            "paper_position_qty": paper_qty,
            "position_qty_diff": qty_diff,
            "target_exposure": target_exposure,
            "actual_shadow_exposure": actual_shadow_exposure,
            "actual_paper_exposure": actual_paper_exposure,
            "shadow_open_order_count": _safe_int(shadow.get("open_order_count"), 0),
            "paper_open_order_count": _safe_int(paper.get("open_order_count"), 0),
            "check_count": len(checks),
            "warning_count": len(warns),
            "blocker_count": len(blocked),
        }
        return AccountComparisonReport(
            timestamp_utc=utc_now_iso(),
            status=status,
            summary=summary,
            checks=checks,
            shadow_snapshot=shadow,
            paper_snapshot=paper,
            target_snapshot=target,
            live_gate_snapshot=live_gate_dict,
        )

    def write_outputs(self, report: AccountComparisonReport, output_dir: str | Path | None = None) -> dict[str, Path]:
        output = self._resolve(output_dir or self.monitor_cfg.get("output_path", "reports/shadow_monitor"))
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "shadow_drift_report.json"
        csv_path = output / "shadow_drift_checks.csv"
        html_path = output / "shadow_monitor_panel.html"
        summary_path = output / "shadow_monitor_summary.csv"

        json_path.write_text(_json_dumps(report.to_dict()), encoding="utf-8")
        report.checks_frame().to_csv(csv_path, index=False)
        pd.DataFrame([report.summary]).to_csv(summary_path, index=False)
        html_path.write_text(render_shadow_monitor_html(report), encoding="utf-8")
        self.store.append_report(report)
        return {"json": json_path, "checks_csv": csv_path, "summary_csv": summary_path, "html": html_path}


def _status_badge(status: str) -> str:
    colors = {PASS: "#138a36", WARN: "#b7791f", BLOCKED: "#b42318"}
    color = colors.get(status, "#475467")
    return f'<span style="display:inline-block;padding:3px 9px;border-radius:999px;background:{color};color:white;font-weight:700;">{html.escape(status)}</span>'


def render_shadow_monitor_html(report: AccountComparisonReport) -> str:
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
    raw_blocks = {
        "shadow_snapshot": report.shadow_snapshot,
        "paper_snapshot": report.paper_snapshot,
        "target_snapshot": report.target_snapshot,
        "live_gate_snapshot": report.live_gate_snapshot,
    }
    raw_html = "".join(
        f"<h3>{html.escape(name)}</h3><pre>{html.escape(json.dumps(payload, ensure_ascii=False, indent=2, default=str))}</pre>"
        for name, payload in raw_blocks.items()
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>BTC Quant Shadow Monitor</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif; margin: 28px; color: #101828; }}
    h1 {{ margin-bottom: 4px; }}
    .sub {{ color: #667085; margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 14px 0 28px; }}
    th, td {{ border: 1px solid #d0d5dd; padding: 8px 10px; vertical-align: top; }}
    th {{ background: #f2f4f7; text-align: left; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f8f9fb; padding: 8px; border-radius: 8px; max-height: 360px; overflow: auto; }}
    .card {{ border: 1px solid #d0d5dd; border-radius: 14px; padding: 16px 18px; margin: 16px 0; box-shadow: 0 1px 2px rgba(16,24,40,0.06); }}
  </style>
</head>
<body>
  <h1>BTC Quant Shadow Monitor</h1>
  <p class="sub">Generated at {html.escape(report.timestamp_utc)} · Overall status: {_status_badge(report.status)}</p>
  <div class="card">
    <h2>Summary</h2>
    <table>{summary_rows}</table>
  </div>
  <div class="card">
    <h2>Checks</h2>
    <table>
      <thead><tr><th>Name</th><th>Status</th><th>Severity</th><th>Message</th><th>Details</th></tr></thead>
      <tbody>{check_rows}</tbody>
    </table>
  </div>
  <div class="card">
    <h2>Raw Snapshots</h2>
    {raw_html}
  </div>
</body>
</html>
"""


def build_v21_readiness_payload(cfg: dict[str, Any], *, root: str | Path | None = None, fetch_live_readonly: bool = False) -> dict[str, Any]:
    root_path = Path(root) if root is not None else Path.cwd()
    monitor = ShadowLivePaperMonitor(cfg, root=root_path)
    monitor.maybe_refresh_shadow_snapshot(fetch_private=fetch_live_readonly, offline_fallback=True)
    drift = monitor.build_report()
    drift_paths = monitor.write_outputs(drift)
    live_gate = LiveSafetyGate(cfg, root=root_path).evaluate(mode="v2_1_readiness")
    status = BLOCKED if drift.status == BLOCKED else (WARN if drift.status == WARN or live_gate.status == "warn" else PASS)
    return {
        "timestamp_utc": utc_now_iso(),
        "status": status,
        "shadow_drift_status": drift.status,
        "live_gate_status": live_gate.status,
        "summary": drift.summary,
        "output_paths": {k: str(v) for k, v in drift_paths.items()},
        "drift_report": drift.to_dict(),
        "live_gate": live_gate.to_dict(),
        "notes": [
            "Live gate remaining blocked is expected unless the operator intentionally enables live trading.",
            "V2.1 is intended for read-only shadow/live monitoring and local paper comparison; it does not submit live orders.",
        ],
    }
