from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from crypto_quant.exchange.order_intent import OrderIntent
from crypto_quant.exchange.order_state_machine import OrderLifecycleState
from crypto_quant.exchange.protective_orders import build_long_protective_order_plan, protective_levels_from_percentages


@dataclass(frozen=True)
class ProtectionRecalcPlan:
    """Action plan generated after partial fills or position/order mismatches."""

    status: str
    reason: str
    symbol: str
    position_qty: float
    desired_protection_qty: float
    existing_protection_qty: float
    missing_qty: float
    excess_qty: float
    actions: list[dict[str, Any]] = field(default_factory=list)
    new_protective_intents: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def protective_order_qty(open_order: dict[str, Any]) -> float:
    info = open_order.get("info", {}) if isinstance(open_order.get("info"), dict) else {}
    value = (
        open_order.get("remaining")
        or open_order.get("amount")
        or open_order.get("quantity")
        or open_order.get("origQty")
        or info.get("origQty")
        or info.get("quantity")
        or 0.0
    )
    return _float(value, 0.0)


def is_reduce_only_protective_order(open_order: dict[str, Any]) -> bool:
    info = open_order.get("info", {}) if isinstance(open_order.get("info"), dict) else {}
    order_type = str(open_order.get("type") or open_order.get("order_type") or info.get("type") or "").upper()
    reduce_only_raw = open_order.get("reduceOnly", open_order.get("reduce_only", info.get("reduceOnly")))
    reduce_only = str(reduce_only_raw).lower() in {"true", "1", "yes"}
    return reduce_only or order_type in {"STOP_MARKET", "TAKE_PROFIT_MARKET", "TRAILING_STOP_MARKET"}


def total_existing_protection_qty(open_orders: list[dict[str, Any]]) -> float:
    return sum(protective_order_qty(o) for o in open_orders if is_reduce_only_protective_order(o))


def build_protection_recalc_plan(
    *,
    symbol: str,
    position_qty: float,
    entry_price: float,
    open_orders: list[dict[str, Any]] | None = None,
    qty_tolerance: float = 1e-8,
    attach_new_intents: bool = False,
    cfg: dict[str, Any] | None = None,
) -> ProtectionRecalcPlan:
    """Compare current position quantity with existing protection quantity.

    If protection is smaller than the actual filled position, the safe response is to
    add or recreate protective orders. If it is larger, stale reduce-only orders can
    be cancelled/replaced after verifying the position.
    """
    open_orders = open_orders or []
    desired_qty = abs(float(position_qty))
    existing_qty = total_existing_protection_qty(open_orders)
    missing = max(0.0, desired_qty - existing_qty)
    excess = max(0.0, existing_qty - desired_qty)
    actions: list[dict[str, Any]] = []
    warnings: list[str] = []
    new_intents: list[dict[str, Any]] = []

    if desired_qty <= qty_tolerance:
        if existing_qty > qty_tolerance:
            actions.append({"action": "cancel_stale_reduce_only_orders", "severity": "warning", "qty": existing_qty})
            warnings.append("Position is flat but reduce-only protective orders remain.")
            status = "stale_protection"
            reason = "flat_position_with_open_protection"
        else:
            status = "ok"
            reason = "flat_position_no_protection_needed"
    elif missing > qty_tolerance:
        actions.append({"action": "recalculate_or_add_missing_protection", "severity": "critical", "missing_qty": missing})
        warnings.append("Existing protection quantity is smaller than current position quantity.")
        status = "under_protected"
        reason = "protection_qty_below_position_qty"
    elif excess > qty_tolerance:
        actions.append({"action": "cancel_or_resize_excess_protection", "severity": "warning", "excess_qty": excess})
        warnings.append("Existing reduce-only protection quantity exceeds current position quantity.")
        status = "over_protected"
        reason = "protection_qty_above_position_qty"
    else:
        status = "ok"
        reason = "protection_quantity_matches_position"

    if attach_new_intents and desired_qty > qty_tolerance and cfg is not None and status in {"under_protected", "over_protected"}:
        try:
            native_cfg = cfg.get("native_protection", {})
            stop_loss, take_profit = protective_levels_from_percentages(
                entry_price=float(entry_price),
                stop_loss_pct=float(native_cfg.get("fallback_stop_loss_pct", 0.02)),
                take_profit_pct=float(native_cfg.get("fallback_take_profit_pct", 0.04)),
            )
            trailing_activation = None
            if bool(native_cfg.get("enable_trailing_stop", False)):
                trailing_activation = float(entry_price) * (1.0 + float(native_cfg.get("trailing_activation_pct", 0.01)))
            plan = build_long_protective_order_plan(
                symbol=str(cfg.get("symbol", {}).get("ccxt_symbol", symbol)),
                quantity=desired_qty,
                entry_price=float(entry_price),
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
                trailing_activation_price=trailing_activation,
                trailing_callback_rate=float(native_cfg.get("trailing_callback_rate", 1.0)),
                leverage=float(cfg.get("ensemble_demo_execution", {}).get("leverage", cfg.get("trading", {}).get("leverage", 3.0))),
                working_type=str(native_cfg.get("working_type", "MARK_PRICE")),
                position_side=str(native_cfg.get("position_side", "BOTH")),
                client_order_prefix=str(cfg.get("exchange_resilience", {}).get("client_order_prefix", "btcqv19")),
                enable_stop_loss=bool(native_cfg.get("enable_stop_loss", True)),
                enable_take_profit=bool(native_cfg.get("enable_take_profit", True)),
                enable_trailing_stop=bool(native_cfg.get("enable_trailing_stop", False)),
            )
            new_intents = [intent.to_dict() for intent in plan.intents]
            warnings.extend(plan.warnings)
        except Exception as exc:  # noqa: BLE001 - keep this diagnostic non-fatal
            warnings.append(f"Could not build replacement protective order plan: {exc}")

    return ProtectionRecalcPlan(
        status=status,
        reason=reason,
        symbol=symbol,
        position_qty=float(position_qty),
        desired_protection_qty=desired_qty,
        existing_protection_qty=existing_qty,
        missing_qty=missing,
        excess_qty=excess,
        actions=actions,
        new_protective_intents=new_intents,
        warnings=warnings,
    )


@dataclass(frozen=True)
class PartialFillActionPlan:
    status: str
    reason: str
    lifecycle: dict[str, Any]
    protection_plan: dict[str, Any] | None
    actions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def actions_for_order_lifecycle(
    lifecycle: OrderLifecycleState,
    *,
    cfg: dict[str, Any] | None = None,
    open_orders: list[dict[str, Any]] | None = None,
    entry_price: float | None = None,
) -> PartialFillActionPlan:
    actions: list[dict[str, Any]] = []
    protection: ProtectionRecalcPlan | None = None
    reason = "no_action_required"
    status = "ok"

    if lifecycle.state == "partially_filled":
        status = "requires_attention"
        reason = "partial_fill_requires_position_and_protection_recheck"
        actions.append({
            "action": "reconcile_position_after_partial_fill",
            "severity": "critical",
            "filled_quantity": lifecycle.filled_quantity,
            "remaining_quantity": lifecycle.remaining_quantity,
        })
        if lifecycle.reduce_only is not True and lifecycle.filled_quantity > 0 and entry_price is not None:
            protection = build_protection_recalc_plan(
                symbol=str(lifecycle.symbol or "BTC/USDT:USDT"),
                position_qty=float(lifecycle.filled_quantity),
                entry_price=float(entry_price),
                open_orders=open_orders or [],
                cfg=cfg,
                attach_new_intents=True,
            )
            actions.extend(protection.actions)
    elif lifecycle.state in {"rejected", "expired"}:
        status = "requires_attention"
        reason = f"order_{lifecycle.state}_requires_strategy_recheck"
        actions.append({"action": "recheck_strategy_before_resubmit", "severity": "warning"})
    elif lifecycle.state == "filled" and lifecycle.reduce_only:
        status = "requires_attention"
        reason = "protective_exit_filled_cancel_opposite_orders"
        actions.append({"action": "cancel_remaining_protective_orders_after_exit_fill", "severity": "critical"})

    return PartialFillActionPlan(
        status=status,
        reason=reason,
        lifecycle=lifecycle.to_dict(),
        protection_plan=None if protection is None else protection.to_dict(),
        actions=actions,
    )


def resize_intent_quantity(intent: OrderIntent, new_quantity: float) -> OrderIntent:
    """Return a copy-like OrderIntent with replacement quantity."""
    data = intent.to_dict()
    data["quantity"] = float(new_quantity)
    return OrderIntent(**data)
