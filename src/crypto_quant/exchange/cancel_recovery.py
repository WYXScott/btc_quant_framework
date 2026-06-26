from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from crypto_quant.exchange.errors import classify_exchange_exception


@dataclass(frozen=True)
class CancelFailurePlan:
    status: str
    order_id: str | None
    client_order_id: str | None
    error_category: str
    retryable: bool
    actions: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_cancel_failure_plan(
    exc: Exception | None = None,
    *,
    order_id: str | None = None,
    client_order_id: str | None = None,
    exchange_response: dict[str, Any] | None = None,
) -> CancelFailurePlan:
    """Classify a cancel failure and generate conservative next actions."""
    if exc is not None:
        classified = classify_exchange_exception(exc)
        category = classified.category
        retryable = classified.retryable
        message = classified.message
    else:
        category = str((exchange_response or {}).get("error_category") or "unknown_exchange_error")
        retryable = bool((exchange_response or {}).get("retryable", False))
        message = str((exchange_response or {}).get("message") or "Cancel result was not successful.")

    actions: list[dict[str, Any]] = []
    status = "requires_manual_reconcile"

    if category == "order_not_found":
        actions.append({
            "action": "fetch_open_orders_and_order_history",
            "severity": "warning",
            "reason": "Order may already be filled/canceled/expired; do not blindly resubmit.",
        })
        status = "verify_absent_or_filled"
    elif retryable:
        actions.append({
            "action": "retry_cancel_with_backoff",
            "severity": "warning",
            "reason": "Temporary failure category; retry cancel after backoff, then reconcile open orders.",
        })
        actions.append({
            "action": "block_new_entries_until_cancel_resolved",
            "severity": "critical",
            "reason": "Stale reduce-only/protective orders can affect next position.",
        })
        status = "retryable_cancel_failure"
    else:
        actions.append({
            "action": "halt_and_manual_reconcile",
            "severity": "critical",
            "reason": "Non-retryable cancel failure or unknown state.",
        })

    return CancelFailurePlan(
        status=status,
        order_id=order_id,
        client_order_id=client_order_id,
        error_category=category,
        retryable=retryable,
        actions=actions,
        message=message,
    )
