from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from crypto_quant.exchange.events import NormalizedExchangeEvent


CanonicalOrderState = Literal[
    "created",
    "submitted",
    "new",
    "partially_filled",
    "filled",
    "cancel_requested",
    "canceled",
    "expired",
    "rejected",
    "cancel_failed",
    "unknown",
]

FINAL_STATES = {"filled", "canceled", "expired", "rejected"}
ACTIVE_STATES = {"created", "submitted", "new", "partially_filled", "cancel_requested", "unknown"}


@dataclass(frozen=True)
class OrderLifecycleState:
    """Venue-neutral lifecycle state for one exchange order.

    V1.9 keeps a local state machine because real exchange execution is not binary:
    orders can be partially filled, canceled after a partial fill, expire, be rejected,
    or become unknown after network/timeout failures. The state object is small enough
    to be persisted to SQLite and audited later.
    """

    key: str
    symbol: str | None
    side: str | None
    order_type: str | None
    state: CanonicalOrderState
    client_order_id: str | None = None
    exchange_order_id: str | int | None = None
    reduce_only: bool | None = None
    original_quantity: float | None = None
    filled_quantity: float = 0.0
    remaining_quantity: float | None = None
    average_price: float | None = None
    last_fill_price: float | None = None
    realized_pnl: float | None = None
    last_event_time: str | int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_final(self) -> bool:
        return self.state in FINAL_STATES

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_STATES

    @property
    def fill_ratio(self) -> float | None:
        if not self.original_quantity or self.original_quantity <= 0:
            return None
        return max(0.0, min(1.0, float(self.filled_quantity or 0.0) / float(self.original_quantity)))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderStateTransition:
    key: str
    previous_state: str | None
    new_state: str
    transition_reason: str
    event_time: str | int | None
    client_order_id: str | None
    exchange_order_id: str | int | None
    filled_quantity_delta: float
    filled_quantity_total: float
    remaining_quantity: float | None
    severity: str = "info"
    raw_event: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderStateUpdateResult:
    lifecycle: OrderLifecycleState
    transition: OrderStateTransition
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lifecycle": self.lifecycle.to_dict(),
            "transition": self.transition.to_dict(),
            "warnings": list(self.warnings),
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonicalize_order_status(status: Any, execution_type: Any = None) -> CanonicalOrderState:
    """Map exchange-specific order status/execution fields to canonical states."""
    status_text = str(status or "").strip().upper()
    exec_text = str(execution_type or "").strip().upper()

    if status_text in {"NEW", "OPEN"}:
        return "new"
    if status_text in {"PARTIALLY_FILLED", "PARTIAL", "PARTIALLYFILLED"}:
        return "partially_filled"
    if status_text in {"FILLED", "CLOSED"}:
        return "filled"
    if status_text in {"CANCELED", "CANCELLED"}:
        return "canceled"
    if status_text in {"EXPIRED"}:
        return "expired"
    if status_text in {"REJECTED"}:
        return "rejected"

    if exec_text in {"TRADE"}:
        return "partially_filled"
    if exec_text in {"CANCELED", "CANCELLED"}:
        return "canceled"
    if exec_text in {"EXPIRED"}:
        return "expired"
    if exec_text in {"REJECTED"}:
        return "rejected"

    return "unknown"


def order_key_from_event(event: NormalizedExchangeEvent) -> str:
    return str(
        event.client_order_id
        or event.exchange_order_id
        or f"{event.symbol or 'UNKNOWN'}:{event.side or 'NA'}:{event.order_type or 'NA'}:{event.event_time or utc_now_iso()}"
    )


def _remaining(original_qty: float | None, filled_qty: float | None) -> float | None:
    if original_qty is None:
        return None
    return max(0.0, float(original_qty) - float(filled_qty or 0.0))


class ExchangeOrderStateMachine:
    """Small deterministic order lifecycle state machine.

    It accepts normalized exchange events and returns both the new lifecycle state
    and the transition that should be persisted. It intentionally does not perform
    any exchange call; action generation belongs to recovery/execution layers.
    """

    def __init__(self, existing_state: OrderLifecycleState | None = None):
        self.existing_state = existing_state

    def apply_event(self, event: NormalizedExchangeEvent) -> OrderStateUpdateResult:
        if event.kind != "order":
            raise ValueError("ExchangeOrderStateMachine can only process order events")

        key = order_key_from_event(event)
        prev = self.existing_state
        previous_state = None if prev is None else prev.state
        new_state = canonicalize_order_status(event.order_status, event.execution_type)

        original_qty = event.quantity
        if original_qty is None and prev is not None:
            original_qty = prev.original_quantity

        prev_filled = 0.0 if prev is None else float(prev.filled_quantity or 0.0)
        total_filled = float(event.filled_quantity if event.filled_quantity is not None else prev_filled)
        last_fill = float(event.last_fill_quantity or max(0.0, total_filled - prev_filled))
        remaining = _remaining(original_qty, total_filled)

        # If Binance reports TRADE with partial executedQty but status did not say PARTIALLY_FILLED,
        # infer a partial fill when quantity is not fully filled.
        if new_state == "filled" and original_qty is not None and total_filled + 1e-12 < float(original_qty):
            new_state = "partially_filled"
        if new_state == "unknown" and total_filled > prev_filled:
            new_state = "partially_filled"

        warnings: list[str] = []
        severity = "info"
        reason = "exchange_event"

        if previous_state in FINAL_STATES and new_state not in FINAL_STATES:
            warnings.append(f"Received non-final state {new_state} after final state {previous_state}; keep audit trail and reconcile manually.")
            severity = "warning"
            reason = "unexpected_transition_after_final_state"
        elif new_state == "partially_filled":
            severity = "warning"
            reason = "partial_fill_detected"
        elif new_state in {"rejected", "expired"}:
            severity = "warning"
            reason = f"order_{new_state}"
        elif new_state == "unknown":
            severity = "warning"
            reason = "unknown_order_state"

        lifecycle = OrderLifecycleState(
            key=key,
            symbol=event.symbol if event.symbol is not None else (prev.symbol if prev else None),
            side=event.side if event.side is not None else (prev.side if prev else None),
            order_type=event.order_type if event.order_type is not None else (prev.order_type if prev else None),
            state=new_state,
            client_order_id=event.client_order_id if event.client_order_id is not None else (prev.client_order_id if prev else None),
            exchange_order_id=event.exchange_order_id if event.exchange_order_id is not None else (prev.exchange_order_id if prev else None),
            reduce_only=event.reduce_only if event.reduce_only is not None else (prev.reduce_only if prev else None),
            original_quantity=original_qty,
            filled_quantity=total_filled,
            remaining_quantity=remaining,
            average_price=event.average_price if event.average_price is not None else (prev.average_price if prev else None),
            last_fill_price=event.last_fill_price if event.last_fill_price is not None else (prev.last_fill_price if prev else None),
            realized_pnl=event.realized_pnl if event.realized_pnl is not None else (prev.realized_pnl if prev else None),
            last_event_time=event.event_time,
            raw=event.to_dict(),
        )
        transition = OrderStateTransition(
            key=key,
            previous_state=previous_state,
            new_state=new_state,
            transition_reason=reason,
            event_time=event.event_time,
            client_order_id=lifecycle.client_order_id,
            exchange_order_id=lifecycle.exchange_order_id,
            filled_quantity_delta=max(0.0, total_filled - prev_filled) if event.filled_quantity is not None else last_fill,
            filled_quantity_total=total_filled,
            remaining_quantity=remaining,
            severity=severity,
            raw_event=event.to_dict(),
        )
        return OrderStateUpdateResult(lifecycle=lifecycle, transition=transition, warnings=warnings)


def lifecycle_from_exchange_order_row(row: dict[str, Any] | None) -> OrderLifecycleState | None:
    if not row:
        return None
    state = canonicalize_order_status(row.get("order_status"))
    qty = row.get("quantity")
    filled = row.get("filled_quantity")
    remaining = _remaining(None if qty is None else float(qty), None if filled is None else float(filled))
    return OrderLifecycleState(
        key=str(row.get("key")),
        symbol=row.get("symbol"),
        side=row.get("side"),
        order_type=row.get("order_type"),
        state=state,
        client_order_id=row.get("client_order_id"),
        exchange_order_id=row.get("exchange_order_id"),
        reduce_only=None if row.get("reduce_only") is None else bool(row.get("reduce_only")),
        original_quantity=None if qty is None else float(qty),
        filled_quantity=0.0 if filled is None else float(filled),
        remaining_quantity=remaining,
        average_price=None if row.get("average_price") is None else float(row.get("average_price")),
        last_event_time=row.get("last_event_time"),
        raw=row,
    )
