from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_quant.config import project_root
from crypto_quant.paper.database import PaperStore


@dataclass(frozen=True)
class RuntimeStatusSnapshot:
    timestamp_utc: str
    database_path: str
    account: dict[str, Any]
    latest_decision: dict[str, Any] | None
    latest_order: dict[str, Any] | None
    latest_equity: dict[str, Any] | None
    latest_alert: dict[str, Any] | None
    latest_heartbeat: dict[str, Any] | None
    table_counts: dict[str, int]
    derived: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeStatusBuilder:
    """Build a compact runtime dashboard snapshot from the SQLite store."""

    def __init__(self, cfg: dict[str, Any], *, root: Path | None = None):
        self.cfg = cfg
        self.root = root or project_root()
        db_path = cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
        self.db_path = Path(db_path) if Path(db_path).is_absolute() else self.root / db_path
        self.store = PaperStore(self.db_path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _last_record(df: pd.DataFrame) -> dict[str, Any] | None:
        if df.empty:
            return None
        row = df.iloc[-1].where(pd.notna(df.iloc[-1]), None)
        return row.to_dict()

    def _table_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in self.store.paper_tables():
            try:
                counts[table] = len(self.store.read_table(table))
            except Exception:
                counts[table] = -1
        return counts

    def build(self) -> RuntimeStatusSnapshot:
        account_obj = self.store.load_account(
            initial_equity=float(self.cfg.get("trading", {}).get("initial_equity", 1000.0)),
            leverage=float(self.cfg.get("trading", {}).get("leverage", 3.0)),
        )
        account = asdict(account_obj)
        tables: dict[str, pd.DataFrame] = {}
        for name in ["decisions", "orders", "equity_curve", "alerts", "daemon_heartbeats", "reconciliation_runs", "recovery_actions"]:
            try:
                tables[name] = self.store.read_table(name)
            except Exception:
                tables[name] = pd.DataFrame()
        latest_equity = self._last_record(tables["equity_curve"])
        latest_order = self._last_record(tables["orders"])
        latest_decision = self._last_record(tables["decisions"])
        latest_alert = self._last_record(tables["alerts"])
        latest_heartbeat = self._last_record(tables["daemon_heartbeats"])

        derived: dict[str, Any] = {
            "in_position": bool(account.get("position_qty", 0.0)),
            "position_qty": account.get("position_qty"),
            "equity": account.get("equity"),
            "cash": account.get("cash"),
            "realized_pnl": account.get("realized_pnl"),
            "consecutive_losses": account.get("consecutive_losses"),
            "risk_pause_until": account.get("risk_pause_until"),
        }
        if latest_equity and latest_equity.get("equity") is not None:
            initial = float(self.cfg.get("trading", {}).get("initial_equity", 1000.0))
            equity = float(latest_equity.get("equity"))
            derived["paper_return_since_init"] = equity / initial - 1.0 if initial > 0 else None
        return RuntimeStatusSnapshot(
            timestamp_utc=self._now(),
            database_path=str(self.db_path),
            account=account,
            latest_decision=latest_decision,
            latest_order=latest_order,
            latest_equity=latest_equity,
            latest_alert=latest_alert,
            latest_heartbeat=latest_heartbeat,
            table_counts=self._table_counts(),
            derived=derived,
        )

    def write_snapshot(self, snapshot: RuntimeStatusSnapshot, path: str | Path | None = None) -> Path:
        import json

        if path is None:
            path = self.cfg.get("deployment", {}).get("status_report_path", "reports/deployment/runtime_status.json")
        out = Path(path) if Path(path).is_absolute() else self.root / path
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2, default=str)
        return out
