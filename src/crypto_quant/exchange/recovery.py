from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from crypto_quant.paper.account import PaperAccount


@dataclass(frozen=True)
class ExchangePositionSnapshot:
    symbol: str
    contracts: float
    side: str | None
    entry_price: float | None
    notional: float | None
    raw: dict[str, Any]

    @property
    def in_position(self) -> bool:
        return abs(float(self.contracts)) > 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryCheckResult:
    status: str
    local_in_position: bool
    exchange_in_position: bool | None
    local_qty: float
    exchange_qty: float | None
    open_order_count: int | None
    missing_native_protection: bool | None
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_local_and_exchange_state(
    *,
    local_account: PaperAccount,
    exchange_position: ExchangePositionSnapshot | None,
    open_orders: list[dict[str, Any]] | None,
    min_protective_order_count: int = 1,
    qty_tolerance: float = 1e-8,
) -> RecoveryCheckResult:
    """Compare local paper state with exchange demo/testnet state.

    This is a pre-live safety helper. It does not decide trades; it only highlights
    mismatches that must be resolved before trusting automation after a restart or
    network/API interruption.
    """
    warnings: list[str] = []
    local_in = local_account.in_position
    local_qty = abs(float(local_account.position_qty or 0.0))

    if exchange_position is None:
        return RecoveryCheckResult(
            status="local_only",
            local_in_position=local_in,
            exchange_in_position=None,
            local_qty=local_qty,
            exchange_qty=None,
            open_order_count=None,
            missing_native_protection=None,
            warnings=["No exchange position snapshot supplied; only local state was checked."],
        )

    exchange_in = exchange_position.in_position
    exchange_qty = abs(float(exchange_position.contracts or 0.0))

    if local_in and not exchange_in:
        warnings.append("Local account is in position, but exchange snapshot is flat.")
    if exchange_in and not local_in:
        warnings.append("Exchange snapshot is in position, but local account is flat.")
    if local_in and exchange_in and abs(local_qty - exchange_qty) > qty_tolerance:
        warnings.append(f"Local quantity {local_qty:.10f} differs from exchange quantity {exchange_qty:.10f}.")

    order_count = None if open_orders is None else len(open_orders)
    missing_native_protection = None
    if exchange_in and open_orders is not None:
        # Heuristic: at least one reduce-only/conditional order should exist while a
        # leveraged position is open. Exact matching is exchange-specific and can be
        # tightened later after real testnet observations.
        protective_like = 0
        for order in open_orders:
            typ = str(order.get("type") or order.get("order_type") or order.get("info", {}).get("type") or "").upper()
            reduce_only = order.get("reduceOnly") or order.get("reduce_only") or order.get("info", {}).get("reduceOnly")
            if reduce_only or typ in {"STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET", "STOP", "TAKE_PROFIT"}:
                protective_like += 1
        missing_native_protection = protective_like < min_protective_order_count
        if missing_native_protection:
            warnings.append("Exchange position appears open but native protective orders are missing or insufficient.")

    status = "ok" if not warnings else "warning"
    return RecoveryCheckResult(
        status=status,
        local_in_position=local_in,
        exchange_in_position=exchange_in,
        local_qty=local_qty,
        exchange_qty=exchange_qty,
        open_order_count=order_count,
        missing_native_protection=missing_native_protection,
        warnings=warnings,
    )
