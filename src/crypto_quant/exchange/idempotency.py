from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from crypto_quant.exchange.order_intent import OrderIntent


@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    client_order_id: str
    fingerprint: str
    status: str
    intent_json: dict[str, Any]
    result_json: dict[str, Any] | None = None
    attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def intent_fingerprint(intent: OrderIntent, *, time_bucket: str | None = None, exclude_client_order_id: bool = True) -> str:
    d = intent.to_dict()
    if exclude_client_order_id:
        d.pop("client_order_id", None)
    d["time_bucket"] = time_bucket or "manual"
    return hashlib.sha256(_stable_json(d).encode("utf-8")).hexdigest()


def make_client_order_id(prefix: str, fingerprint: str, *, max_len: int = 36) -> str:
    safe_prefix = "".join(ch for ch in prefix.lower() if ch.isalnum())[:12] or "btcq"
    suffix_len = max(8, min(20, max_len - len(safe_prefix) - 1))
    return f"{safe_prefix}_{fingerprint[:suffix_len]}"[:max_len]


def with_idempotent_client_order_id(
    intent: OrderIntent,
    *,
    prefix: str,
    time_bucket: str | None = None,
) -> tuple[OrderIntent, str, str]:
    fingerprint = intent_fingerprint(intent, time_bucket=time_bucket)
    client_order_id = intent.client_order_id or make_client_order_id(prefix, fingerprint)
    new_intent = OrderIntent(
        symbol=intent.symbol,
        side=intent.side,
        order_type=intent.order_type,
        quantity=intent.quantity,
        price=intent.price,
        reduce_only=intent.reduce_only,
        leverage=intent.leverage,
        client_order_id=client_order_id,
        reason=intent.reason,
        stop_price=intent.stop_price,
        activation_price=intent.activation_price,
        callback_rate=intent.callback_rate,
        working_type=intent.working_type,
        close_position=intent.close_position,
        position_side=intent.position_side,
        time_in_force=intent.time_in_force,
        extra_params=dict(intent.extra_params or {}),
    )
    key = f"{intent.symbol}:{client_order_id}"
    return new_intent, key, fingerprint


class IdempotencyStore:
    """Small SQLite-backed ledger for exactly-once order intent handling."""

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

    def get(self, key: str) -> IdempotencyRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM idempotency_keys WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return IdempotencyRecord(
            key=row["key"],
            client_order_id=row["client_order_id"],
            fingerprint=row["fingerprint"],
            status=row["status"],
            attempts=int(row["attempts"] or 0),
            intent_json=json.loads(row["intent_json"] or "{}"),
            result_json=None if row["result_json"] is None else json.loads(row["result_json"]),
        )

    def reserve(self, *, key: str, client_order_id: str, fingerprint: str, intent: dict[str, Any]) -> tuple[bool, IdempotencyRecord | None]:
        existing = self.get(key)
        if existing is not None and existing.status in {"submitted", "success", "unknown_order_state", "pending"}:
            return False, existing
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO idempotency_keys (key, client_order_id, fingerprint, status, attempts, intent_json, result_json, updated_at)
                VALUES (?, ?, ?, 'pending', 0, ?, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    status='pending',
                    intent_json=excluded.intent_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (key, client_order_id, fingerprint, _stable_json(intent)),
            )
            conn.commit()
        return True, self.get(key)

    def update_status(self, key: str, *, status: str, result: dict[str, Any] | None = None, increment_attempts: bool = False) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE idempotency_keys
                SET status = ?,
                    attempts = attempts + ?,
                    result_json = COALESCE(?, result_json),
                    updated_at = CURRENT_TIMESTAMP
                WHERE key = ?
                """,
                (status, 1 if increment_attempts else 0, None if result is None else _stable_json(result), key),
            )
            conn.commit()

    def append_attempt(self, *, key: str, client_order_id: str, attempt: dict[str, Any]) -> None:
        error = attempt.get("error") or {}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO resilient_order_attempts (
                    key, client_order_id, attempt, status, retryable, error_category,
                    error_message, delay_seconds, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    client_order_id,
                    attempt.get("attempt"),
                    attempt.get("status"),
                    int(bool(attempt.get("retryable", False))),
                    error.get("category"),
                    error.get("message"),
                    attempt.get("delay_seconds"),
                    _stable_json(attempt),
                ),
            )
            conn.commit()

    def read_keys(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM idempotency_keys ORDER BY updated_at DESC").fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({k: r[k] for k in r.keys()})
        return out

    def read_attempts(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM resilient_order_attempts ORDER BY id ASC").fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]
