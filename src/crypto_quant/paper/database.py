from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from crypto_quant.paper.account import PaperAccount


class PaperStore:
    """SQLite storage for paper-trading account, orders, decisions and equity curve."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.create_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def create_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS account_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    position_qty REAL NOT NULL,
                    entry_price REAL,
                    leverage REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    entry_timestamp TEXT,
                    last_update_timestamp TEXT,
                    bars_held INTEGER NOT NULL,
                    stop_loss_price REAL,
                    take_profit_price REAL,
                    trailing_stop_price REAL,
                    highest_price_since_entry REAL,
                    consecutive_losses INTEGER NOT NULL DEFAULT 0,
                    risk_pause_until TEXT,
                    daily_loss_date TEXT,
                    daily_realized_pnl REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_columns(
                conn,
                "account_state",
                {
                    "stop_loss_price": "REAL",
                    "take_profit_price": "REAL",
                    "trailing_stop_price": "REAL",
                    "highest_price_since_entry": "REAL",
                    "consecutive_losses": "INTEGER NOT NULL DEFAULT 0",
                    "risk_pause_until": "TEXT",
                    "daily_loss_date": "TEXT",
                    "daily_realized_pnl": "REAL NOT NULL DEFAULT 0",
                },
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    side TEXT NOT NULL,
                    price REAL,
                    qty REAL,
                    notional REAL,
                    fee REAL,
                    pnl REAL,
                    status TEXT,
                    reason TEXT,
                    prob_up REAL,
                    signal INTEGER,
                    equity_after REAL,
                    metadata_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_columns(conn, "orders", {"metadata_json": "TEXT"})
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    price REAL NOT NULL,
                    prob_up REAL,
                    signal INTEGER,
                    action TEXT NOT NULL,
                    reason TEXT,
                    risk_allowed INTEGER,
                    leverage REAL,
                    margin_fraction REAL,
                    notional_fraction REAL,
                    equity REAL,
                    position_qty REAL,
                    stop_loss_price REAL,
                    take_profit_price REAL,
                    trailing_stop_price REAL,
                    risk_pause_until TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(timestamp)
                )
                """
            )
            self._ensure_columns(
                conn,
                "decisions",
                {
                    "stop_loss_price": "REAL",
                    "take_profit_price": "REAL",
                    "trailing_stop_price": "REAL",
                    "risk_pause_until": "TEXT",
                },
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS target_exposure_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL UNIQUE,
                    price REAL NOT NULL,
                    ensemble_score REAL,
                    signal INTEGER,
                    target_exposure REAL,
                    target_notional REAL,
                    current_exposure_before REAL,
                    current_exposure_after REAL,
                    current_notional_before REAL,
                    delta_notional REAL,
                    action TEXT,
                    reason TEXT,
                    equity REAL,
                    cash REAL,
                    position_qty REAL,
                    entry_price REAL,
                    candidate_active_count REAL,
                    candidate_active_fraction REAL,
                    candidate_count INTEGER,
                    order_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS equity_curve (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL UNIQUE,
                    price REAL NOT NULL,
                    cash REAL NOT NULL,
                    equity REAL NOT NULL,
                    position_qty REAL NOT NULL,
                    entry_price REAL,
                    leverage REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL,
                    bars_held INTEGER NOT NULL,
                    liquidation_price REAL,
                    stop_loss_price REAL,
                    take_profit_price REAL,
                    trailing_stop_price REAL,
                    highest_price_since_entry REAL,
                    consecutive_losses INTEGER,
                    risk_pause_until TEXT,
                    daily_realized_pnl REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._ensure_columns(
                conn,
                "equity_curve",
                {
                    "stop_loss_price": "REAL",
                    "take_profit_price": "REAL",
                    "trailing_stop_price": "REAL",
                    "highest_price_since_entry": "REAL",
                    "consecutive_losses": "INTEGER",
                    "risk_pause_until": "TEXT",
                    "daily_realized_pnl": "REAL",
                },
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    dry_run INTEGER NOT NULL,
                    action TEXT,
                    reason TEXT,
                    intent_json TEXT,
                    order_json TEXT,
                    message TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT UNIQUE,
                    created_timestamp TEXT,
                    last_update_timestamp TEXT,
                    side TEXT,
                    order_type TEXT,
                    price REAL,
                    qty REAL,
                    reason TEXT,
                    status TEXT,
                    age_bars INTEGER,
                    filled_timestamp TEXT,
                    filled_price REAL,
                    order_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exchange_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_time TEXT,
                    kind TEXT,
                    symbol TEXT,
                    side TEXT,
                    order_type TEXT,
                    order_status TEXT,
                    client_order_id TEXT,
                    exchange_order_id TEXT,
                    execution_type TEXT,
                    reduce_only INTEGER,
                    position_side TEXT,
                    quantity REAL,
                    filled_quantity REAL,
                    last_fill_quantity REAL,
                    average_price REAL,
                    last_fill_price REAL,
                    realized_pnl REAL,
                    position_amount REAL,
                    entry_price REAL,
                    raw_event_type TEXT,
                    event_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exchange_order_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE,
                    symbol TEXT,
                    side TEXT,
                    order_type TEXT,
                    order_status TEXT,
                    client_order_id TEXT,
                    exchange_order_id TEXT,
                    reduce_only INTEGER,
                    quantity REAL,
                    filled_quantity REAL,
                    average_price REAL,
                    last_event_time TEXT,
                    order_json TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exchange_position_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    symbol TEXT,
                    contracts REAL,
                    side TEXT,
                    entry_price REAL,
                    notional REAL,
                    position_amount REAL,
                    mark_price REAL,
                    source TEXT,
                    snapshot_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reconciliation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT,
                    source TEXT,
                    status TEXT,
                    open_order_count INTEGER,
                    report_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS target_execution_prechecks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT,
                    source TEXT,
                    status TEXT,
                    allow_execution INTEGER,
                    plan_action TEXT,
                    target_exposure REAL,
                    exchange_qty REAL,
                    plan_current_qty REAL,
                    open_order_count INTEGER,
                    protective_order_count INTEGER,
                    report_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recovery_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT,
                    action TEXT,
                    severity TEXT,
                    reason TEXT,
                    status TEXT,
                    dry_run INTEGER NOT NULL,
                    execute_requested INTEGER NOT NULL,
                    result_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT,
                    level TEXT,
                    title TEXT,
                    message TEXT,
                    alert_json TEXT,
                    delivery_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daemon_heartbeats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT,
                    component TEXT,
                    status TEXT,
                    iteration INTEGER,
                    details_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS exchange_order_lifecycle (
                    key TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    order_type TEXT,
                    state TEXT,
                    client_order_id TEXT,
                    exchange_order_id TEXT,
                    reduce_only INTEGER,
                    original_quantity REAL,
                    filled_quantity REAL,
                    remaining_quantity REAL,
                    average_price REAL,
                    last_fill_price REAL,
                    realized_pnl REAL,
                    last_event_time TEXT,
                    lifecycle_json TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS order_state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT,
                    previous_state TEXT,
                    new_state TEXT,
                    transition_reason TEXT,
                    event_time TEXT,
                    client_order_id TEXT,
                    exchange_order_id TEXT,
                    filled_quantity_delta REAL,
                    filled_quantity_total REAL,
                    remaining_quantity REAL,
                    severity TEXT,
                    transition_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS protection_recalc_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    reason TEXT,
                    symbol TEXT,
                    position_qty REAL,
                    desired_protection_qty REAL,
                    existing_protection_qty REAL,
                    missing_qty REAL,
                    excess_qty REAL,
                    plan_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cancel_failure_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    order_id TEXT,
                    client_order_id TEXT,
                    error_category TEXT,
                    retryable INTEGER,
                    plan_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY,
                    client_order_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    intent_json TEXT,
                    result_json TEXT,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS resilient_order_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT,
                    client_order_id TEXT,
                    attempt INTEGER,
                    status TEXT,
                    retryable INTEGER,
                    error_category TEXT,
                    error_message TEXT,
                    delay_seconds REAL,
                    payload_json TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def reset(self, initial_equity: float, leverage: float = 3.0) -> PaperAccount:
        account = PaperAccount(equity=float(initial_equity), cash=float(initial_equity), leverage=float(leverage))
        with self.connect() as conn:
            for table in [
                "account_state",
                "orders",
                "decisions",
                "target_exposure_decisions",
                "equity_curve",
                "execution_events",
                "pending_orders",
                "exchange_events",
                "exchange_order_state",
                "exchange_position_snapshots",
                "reconciliation_runs",
                "target_execution_prechecks",
                "recovery_actions",
                "alerts",
                "daemon_heartbeats",
                "exchange_order_lifecycle",
                "order_state_transitions",
                "protection_recalc_plans",
                "cancel_failure_events",
                "idempotency_keys",
                "resilient_order_attempts",
                "shadow_monitor_reports",
                "shadow_monitor_checks",
            ]:
                # Some V2.1 monitoring tables may not exist in older databases.
                try:
                    conn.execute(f"DELETE FROM {table}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
        self.save_account(account)
        return account

    def load_account(self, initial_equity: float | None = None, leverage: float = 3.0) -> PaperAccount:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM account_state WHERE id = 1").fetchone()
        if row is None:
            equity = float(initial_equity if initial_equity is not None else 1000.0)
            account = PaperAccount(equity=equity, cash=equity, leverage=float(leverage))
            self.save_account(account)
            return account
        keys = set(row.keys())
        return PaperAccount(
            equity=float(row["equity"]),
            cash=float(row["cash"]),
            position_qty=float(row["position_qty"]),
            entry_price=None if row["entry_price"] is None else float(row["entry_price"]),
            leverage=float(row["leverage"]),
            realized_pnl=float(row["realized_pnl"]),
            entry_timestamp=row["entry_timestamp"],
            last_update_timestamp=row["last_update_timestamp"],
            bars_held=int(row["bars_held"]),
            stop_loss_price=None if "stop_loss_price" not in keys or row["stop_loss_price"] is None else float(row["stop_loss_price"]),
            take_profit_price=None if "take_profit_price" not in keys or row["take_profit_price"] is None else float(row["take_profit_price"]),
            trailing_stop_price=None if "trailing_stop_price" not in keys or row["trailing_stop_price"] is None else float(row["trailing_stop_price"]),
            highest_price_since_entry=None if "highest_price_since_entry" not in keys or row["highest_price_since_entry"] is None else float(row["highest_price_since_entry"]),
            consecutive_losses=0 if "consecutive_losses" not in keys else int(row["consecutive_losses"] or 0),
            risk_pause_until=None if "risk_pause_until" not in keys else row["risk_pause_until"],
            daily_loss_date=None if "daily_loss_date" not in keys else row["daily_loss_date"],
            daily_realized_pnl=0.0 if "daily_realized_pnl" not in keys else float(row["daily_realized_pnl"] or 0.0),
        )

    def save_account(self, account: PaperAccount) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO account_state (
                    id, equity, cash, position_qty, entry_price, leverage, realized_pnl,
                    entry_timestamp, last_update_timestamp, bars_held,
                    stop_loss_price, take_profit_price, trailing_stop_price, highest_price_since_entry,
                    consecutive_losses, risk_pause_until, daily_loss_date, daily_realized_pnl, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    equity=excluded.equity,
                    cash=excluded.cash,
                    position_qty=excluded.position_qty,
                    entry_price=excluded.entry_price,
                    leverage=excluded.leverage,
                    realized_pnl=excluded.realized_pnl,
                    entry_timestamp=excluded.entry_timestamp,
                    last_update_timestamp=excluded.last_update_timestamp,
                    bars_held=excluded.bars_held,
                    stop_loss_price=excluded.stop_loss_price,
                    take_profit_price=excluded.take_profit_price,
                    trailing_stop_price=excluded.trailing_stop_price,
                    highest_price_since_entry=excluded.highest_price_since_entry,
                    consecutive_losses=excluded.consecutive_losses,
                    risk_pause_until=excluded.risk_pause_until,
                    daily_loss_date=excluded.daily_loss_date,
                    daily_realized_pnl=excluded.daily_realized_pnl,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    account.equity,
                    account.cash,
                    account.position_qty,
                    account.entry_price,
                    account.leverage,
                    account.realized_pnl,
                    account.entry_timestamp,
                    account.last_update_timestamp,
                    account.bars_held,
                    account.stop_loss_price,
                    account.take_profit_price,
                    account.trailing_stop_price,
                    account.highest_price_since_entry,
                    account.consecutive_losses,
                    account.risk_pause_until,
                    account.daily_loss_date,
                    account.daily_realized_pnl,
                ),
            )
            conn.commit()

    def append_order(self, order: dict[str, Any], equity_after: float | None = None) -> None:
        if order.get("status") != "filled":
            return
        stored_cols = {"timestamp", "side", "price", "qty", "notional", "fee", "pnl", "status", "reason", "prob_up", "signal"}
        metadata = {k: v for k, v in order.items() if k not in stored_cols}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    timestamp, side, price, qty, notional, fee, pnl, status, reason,
                    prob_up, signal, equity_after, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.get("timestamp"),
                    order.get("side"),
                    order.get("price"),
                    order.get("qty"),
                    order.get("notional"),
                    order.get("fee"),
                    order.get("pnl"),
                    order.get("status"),
                    order.get("reason"),
                    order.get("prob_up"),
                    order.get("signal"),
                    equity_after,
                    json.dumps(metadata, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_decision(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO decisions (
                    timestamp, price, prob_up, signal, action, reason, risk_allowed,
                    leverage, margin_fraction, notional_fraction, equity, position_qty,
                    stop_loss_price, take_profit_price, trailing_stop_price, risk_pause_until
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("timestamp"),
                    row.get("price"),
                    row.get("prob_up"),
                    row.get("signal"),
                    row.get("action"),
                    row.get("reason"),
                    int(bool(row.get("risk_allowed", False))),
                    row.get("leverage"),
                    row.get("margin_fraction"),
                    row.get("notional_fraction"),
                    row.get("equity"),
                    row.get("position_qty"),
                    row.get("stop_loss_price"),
                    row.get("take_profit_price"),
                    row.get("trailing_stop_price"),
                    row.get("risk_pause_until"),
                ),
            )
            conn.commit()

    def has_target_exposure_decision_for_timestamp(self, timestamp: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM target_exposure_decisions WHERE timestamp = ? LIMIT 1",
                (timestamp,),
            ).fetchone()
        return row is not None

    def append_target_exposure_decision(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO target_exposure_decisions (
                    timestamp, price, ensemble_score, signal, target_exposure, target_notional,
                    current_exposure_before, current_exposure_after, current_notional_before,
                    delta_notional, action, reason, equity, cash, position_qty, entry_price,
                    candidate_active_count, candidate_active_fraction, candidate_count, order_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("timestamp"),
                    row.get("price"),
                    row.get("ensemble_score"),
                    row.get("signal"),
                    row.get("target_exposure"),
                    row.get("target_notional"),
                    row.get("current_exposure_before"),
                    row.get("current_exposure_after"),
                    row.get("current_notional_before"),
                    row.get("delta_notional"),
                    row.get("action"),
                    row.get("reason"),
                    row.get("equity"),
                    row.get("cash"),
                    row.get("position_qty"),
                    row.get("entry_price"),
                    row.get("candidate_active_count"),
                    row.get("candidate_active_fraction"),
                    row.get("candidate_count"),
                    json.dumps(row.get("order_json"), ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_equity(self, timestamp: str, price: float, account: PaperAccount, maintenance_margin_rate: float = 0.005) -> None:
        unrealized = account.unrealized_pnl(price)
        liq = account.estimated_long_liquidation_price(maintenance_margin_rate=maintenance_margin_rate)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO equity_curve (
                    timestamp, price, cash, equity, position_qty, entry_price, leverage,
                    realized_pnl, unrealized_pnl, bars_held, liquidation_price,
                    stop_loss_price, take_profit_price, trailing_stop_price, highest_price_since_entry,
                    consecutive_losses, risk_pause_until, daily_realized_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    float(price),
                    account.cash,
                    account.equity,
                    account.position_qty,
                    account.entry_price,
                    account.leverage,
                    account.realized_pnl,
                    unrealized,
                    account.bars_held,
                    liq,
                    account.stop_loss_price,
                    account.take_profit_price,
                    account.trailing_stop_price,
                    account.highest_price_since_entry,
                    account.consecutive_losses,
                    account.risk_pause_until,
                    account.daily_realized_pnl,
                ),
            )
            conn.commit()

    def last_processed_timestamp(self) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT MAX(timestamp) AS ts FROM equity_curve").fetchone()
        return None if row is None else row["ts"]

    def has_execution_for_timestamp(self, timestamp: str, action: str | None = None) -> bool:
        with self.connect() as conn:
            if action is None:
                row = conn.execute("SELECT 1 FROM execution_events WHERE timestamp = ? LIMIT 1", (timestamp,)).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM execution_events WHERE timestamp = ? AND action = ? LIMIT 1", (timestamp, action)
                ).fetchone()
        return row is not None

    def append_execution_event(self, result: dict[str, Any]) -> None:
        decision = result.get("decision") or {}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_events (
                    timestamp, mode, status, dry_run, action, reason, intent_json, order_json, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.get("timestamp"),
                    result.get("mode"),
                    result.get("status"),
                    int(bool(result.get("dry_run", True))),
                    decision.get("action"),
                    decision.get("reason"),
                    json.dumps(result.get("intent"), ensure_ascii=False, default=str),
                    json.dumps(result.get("order"), ensure_ascii=False, default=str),
                    result.get("message"),
                ),
            )
            conn.commit()

    def upsert_pending_order(self, order: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO pending_orders (
                    order_id, created_timestamp, last_update_timestamp, side, order_type, price, qty,
                    reason, status, age_bars, filled_timestamp, filled_price, order_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    last_update_timestamp=excluded.last_update_timestamp,
                    status=excluded.status,
                    age_bars=excluded.age_bars,
                    filled_timestamp=excluded.filled_timestamp,
                    filled_price=excluded.filled_price,
                    order_json=excluded.order_json
                """,
                (
                    order.get("order_id"),
                    order.get("created_timestamp"),
                    order.get("last_update_timestamp"),
                    order.get("side"),
                    order.get("order_type"),
                    order.get("price"),
                    order.get("qty"),
                    order.get("reason"),
                    order.get("status"),
                    order.get("age_bars"),
                    order.get("filled_timestamp"),
                    order.get("filled_price"),
                    json.dumps(order, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_exchange_event(self, event: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO exchange_events (
                    event_time, kind, symbol, side, order_type, order_status, client_order_id,
                    exchange_order_id, execution_type, reduce_only, position_side, quantity,
                    filled_quantity, last_fill_quantity, average_price, last_fill_price, realized_pnl,
                    position_amount, entry_price, raw_event_type, event_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    None if event.get("event_time") is None else str(event.get("event_time")),
                    event.get("kind"),
                    event.get("symbol"),
                    event.get("side"),
                    event.get("order_type"),
                    event.get("order_status"),
                    event.get("client_order_id"),
                    None if event.get("exchange_order_id") is None else str(event.get("exchange_order_id")),
                    event.get("execution_type"),
                    None if event.get("reduce_only") is None else int(bool(event.get("reduce_only"))),
                    event.get("position_side"),
                    event.get("quantity"),
                    event.get("filled_quantity"),
                    event.get("last_fill_quantity"),
                    event.get("average_price"),
                    event.get("last_fill_price"),
                    event.get("realized_pnl"),
                    event.get("position_amount"),
                    event.get("entry_price"),
                    event.get("raw_event_type"),
                    json.dumps(event, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def upsert_exchange_order_state(self, order: dict[str, Any]) -> None:
        info = order.get("info", {}) if isinstance(order.get("info"), dict) else {}
        key = str(order.get("client_order_id") or order.get("clientOrderId") or order.get("id") or order.get("exchange_order_id") or info.get("clientOrderId") or info.get("orderId") or info.get("algoId") or "unknown")
        symbol = order.get("symbol") or order.get("symbol") or info.get("symbol")
        side = order.get("side") or info.get("side")
        order_type = order.get("order_type") or order.get("type") or info.get("type")
        order_status = order.get("order_status") or order.get("status") or info.get("status")
        client_order_id = order.get("client_order_id") or order.get("clientOrderId") or info.get("clientOrderId")
        exchange_order_id = order.get("exchange_order_id") or order.get("id") or info.get("orderId") or info.get("algoId")
        reduce_only = order.get("reduce_only") if "reduce_only" in order else order.get("reduceOnly", info.get("reduceOnly"))
        quantity = order.get("quantity") or order.get("amount") or info.get("origQty")
        filled_quantity = order.get("filled_quantity") or order.get("filled") or info.get("executedQty")
        average_price = order.get("average_price") or order.get("average") or info.get("avgPrice")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO exchange_order_state (
                    key, symbol, side, order_type, order_status, client_order_id, exchange_order_id,
                    reduce_only, quantity, filled_quantity, average_price, last_event_time, order_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    symbol=excluded.symbol,
                    side=excluded.side,
                    order_type=excluded.order_type,
                    order_status=excluded.order_status,
                    client_order_id=excluded.client_order_id,
                    exchange_order_id=excluded.exchange_order_id,
                    reduce_only=excluded.reduce_only,
                    quantity=excluded.quantity,
                    filled_quantity=excluded.filled_quantity,
                    average_price=excluded.average_price,
                    last_event_time=excluded.last_event_time,
                    order_json=excluded.order_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    key,
                    symbol,
                    side,
                    order_type,
                    order_status,
                    None if client_order_id is None else str(client_order_id),
                    None if exchange_order_id is None else str(exchange_order_id),
                    None if reduce_only is None else int(str(reduce_only).lower() in {"true", "1", "yes"}),
                    None if quantity is None else float(quantity),
                    None if filled_quantity is None else float(filled_quantity),
                    None if average_price is None else float(average_price),
                    None if order.get("event_time") is None else str(order.get("event_time")),
                    json.dumps(order, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_exchange_position_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO exchange_position_snapshots (
                    symbol, contracts, side, entry_price, notional, position_amount, mark_price, source, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.get("symbol"),
                    snapshot.get("contracts"),
                    snapshot.get("side"),
                    snapshot.get("entry_price"),
                    snapshot.get("notional"),
                    snapshot.get("position_amount"),
                    snapshot.get("mark_price"),
                    snapshot.get("source") or snapshot.get("kind") or "exchange_snapshot",
                    json.dumps(snapshot, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_reconciliation_run(self, report: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reconciliation_runs (timestamp_utc, source, status, open_order_count, report_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report.get("timestamp_utc"),
                    report.get("source"),
                    report.get("status"),
                    report.get("open_order_count"),
                    json.dumps(report, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_target_execution_precheck(self, report: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO target_execution_prechecks (
                    timestamp_utc, source, status, allow_execution, plan_action, target_exposure,
                    exchange_qty, plan_current_qty, open_order_count, protective_order_count, report_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.get("timestamp_utc"),
                    report.get("source"),
                    report.get("status"),
                    int(bool(report.get("allow_execution", False))),
                    report.get("plan_action"),
                    report.get("plan_target_exposure"),
                    report.get("exchange_qty"),
                    report.get("plan_current_qty"),
                    report.get("open_order_count"),
                    report.get("protective_order_count"),
                    json.dumps(report, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_recovery_action(self, action_result: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO recovery_actions (
                    timestamp_utc, action, severity, reason, status, dry_run,
                    execute_requested, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_result.get("timestamp_utc"),
                    action_result.get("action"),
                    action_result.get("severity"),
                    action_result.get("reason"),
                    action_result.get("status"),
                    int(bool(action_result.get("dry_run", True))),
                    int(bool(action_result.get("execute_requested", False))),
                    json.dumps(action_result, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_alert(self, alert_delivery_result: dict[str, Any]) -> None:
        alert = alert_delivery_result.get("alert") or {}
        delivery = alert_delivery_result.get("delivery") or {}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO alerts (timestamp_utc, level, title, message, alert_json, delivery_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.get("timestamp_utc"),
                    alert.get("level"),
                    alert.get("title"),
                    alert.get("message"),
                    json.dumps(alert, ensure_ascii=False, default=str),
                    json.dumps(delivery, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_daemon_heartbeat(self, heartbeat: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO daemon_heartbeats (timestamp_utc, component, status, iteration, details_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    heartbeat.get("timestamp_utc"),
                    heartbeat.get("component"),
                    heartbeat.get("status"),
                    heartbeat.get("iteration"),
                    json.dumps(heartbeat.get("details") or {}, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def load_order_lifecycle(self, key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM exchange_order_lifecycle WHERE key = ?", (key,)).fetchone()
        return None if row is None else dict(row)

    def upsert_order_lifecycle(self, lifecycle: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO exchange_order_lifecycle (
                    key, symbol, side, order_type, state, client_order_id, exchange_order_id,
                    reduce_only, original_quantity, filled_quantity, remaining_quantity, average_price,
                    last_fill_price, realized_pnl, last_event_time, lifecycle_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    symbol=excluded.symbol,
                    side=excluded.side,
                    order_type=excluded.order_type,
                    state=excluded.state,
                    client_order_id=excluded.client_order_id,
                    exchange_order_id=excluded.exchange_order_id,
                    reduce_only=excluded.reduce_only,
                    original_quantity=excluded.original_quantity,
                    filled_quantity=excluded.filled_quantity,
                    remaining_quantity=excluded.remaining_quantity,
                    average_price=excluded.average_price,
                    last_fill_price=excluded.last_fill_price,
                    realized_pnl=excluded.realized_pnl,
                    last_event_time=excluded.last_event_time,
                    lifecycle_json=excluded.lifecycle_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    lifecycle.get("key"),
                    lifecycle.get("symbol"),
                    lifecycle.get("side"),
                    lifecycle.get("order_type"),
                    lifecycle.get("state"),
                    lifecycle.get("client_order_id"),
                    None if lifecycle.get("exchange_order_id") is None else str(lifecycle.get("exchange_order_id")),
                    None if lifecycle.get("reduce_only") is None else int(bool(lifecycle.get("reduce_only"))),
                    lifecycle.get("original_quantity"),
                    lifecycle.get("filled_quantity"),
                    lifecycle.get("remaining_quantity"),
                    lifecycle.get("average_price"),
                    lifecycle.get("last_fill_price"),
                    lifecycle.get("realized_pnl"),
                    None if lifecycle.get("last_event_time") is None else str(lifecycle.get("last_event_time")),
                    json.dumps(lifecycle, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_order_state_transition(self, transition: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO order_state_transitions (
                    key, previous_state, new_state, transition_reason, event_time,
                    client_order_id, exchange_order_id, filled_quantity_delta,
                    filled_quantity_total, remaining_quantity, severity, transition_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.get("key"),
                    transition.get("previous_state"),
                    transition.get("new_state"),
                    transition.get("transition_reason"),
                    None if transition.get("event_time") is None else str(transition.get("event_time")),
                    transition.get("client_order_id"),
                    None if transition.get("exchange_order_id") is None else str(transition.get("exchange_order_id")),
                    transition.get("filled_quantity_delta"),
                    transition.get("filled_quantity_total"),
                    transition.get("remaining_quantity"),
                    transition.get("severity"),
                    json.dumps(transition, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_protection_recalc_plan(self, plan: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO protection_recalc_plans (
                    status, reason, symbol, position_qty, desired_protection_qty,
                    existing_protection_qty, missing_qty, excess_qty, plan_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.get("status"),
                    plan.get("reason"),
                    plan.get("symbol"),
                    plan.get("position_qty"),
                    plan.get("desired_protection_qty"),
                    plan.get("existing_protection_qty"),
                    plan.get("missing_qty"),
                    plan.get("excess_qty"),
                    json.dumps(plan, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    def append_cancel_failure_event(self, plan: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO cancel_failure_events (
                    status, order_id, client_order_id, error_category, retryable, plan_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.get("status"),
                    plan.get("order_id"),
                    plan.get("client_order_id"),
                    plan.get("error_category"),
                    int(bool(plan.get("retryable", False))),
                    json.dumps(plan, ensure_ascii=False, default=str),
                ),
            )
            conn.commit()

    @staticmethod
    def paper_tables() -> list[str]:
        return [
            "account_state",
            "orders",
            "decisions",
            "target_exposure_decisions",
            "equity_curve",
            "execution_events",
            "pending_orders",
            "exchange_events",
            "exchange_order_state",
            "exchange_position_snapshots",
            "reconciliation_runs",
            "target_execution_prechecks",
            "recovery_actions",
            "alerts",
            "daemon_heartbeats",
            "exchange_order_lifecycle",
            "order_state_transitions",
            "protection_recalc_plans",
            "cancel_failure_events",
            "idempotency_keys",
            "resilient_order_attempts",
            "shadow_monitor_reports",
            "shadow_monitor_checks",
            "shadow_live_snapshots",
            "live_safety_events",
            "prelive_validation_reports",
        ]

    def read_table(self, table: str) -> pd.DataFrame:
        allowed = set(self.paper_tables())
        if table not in allowed:
            raise ValueError(f"Unsupported table: {table}")
        with self.connect() as conn:
            exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists is None:
                return pd.DataFrame()
            return pd.read_sql_query(f"SELECT * FROM {table}", conn)

    def export_csvs(self, output_dir: str | Path) -> dict[str, Path]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}
        for table in self.paper_tables():
            df = self.read_table(table)
            path = output_dir / f"paper_{table}.csv"
            df.to_csv(path, index=False)
            paths[table] = path
        return paths
