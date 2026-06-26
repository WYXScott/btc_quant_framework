from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from uuid import uuid4

from crypto_quant.exchange.order_intent import OrderIntent
from crypto_quant.exchange.protective_orders import (
    NativeProtectiveOrderPlan,
    build_long_protective_order_plan,
    protective_levels_from_percentages,
)

TargetAction = Literal["hold_flat", "hold", "increase", "reduce", "close", "blocked"]


@dataclass(frozen=True)
class TargetPositionPlan:
    """A broker-neutral plan for rebalancing one long-only symbol to target exposure.

    The plan intentionally uses *target_exposure* rather than a fixed buy/sell signal:
      - 0.0 = flat;
      - 1.0 = notional exposure equals account equity;
      - 3.0 = notional exposure equals 3x account equity.

    It is safe to preview offline. Submission is handled by a broker adapter and remains
    blocked unless the caller explicitly opts into Demo/Testnet execution.
    """

    symbol: str
    timestamp: str
    reference_price: float
    equity_usdt: float
    leverage: float
    current_qty: float
    current_notional: float
    current_exposure: float
    target_exposure_requested: float
    target_exposure: float
    target_notional: float
    target_qty: float
    delta_notional: float
    delta_qty: float
    action: TargetAction
    reason: str
    order_intent: OrderIntent | None
    expected_position_qty: float
    protective_plan: NativeProtectiveOrderPlan | None
    warnings: list[str]

    @property
    def intents(self) -> list[OrderIntent]:
        out: list[OrderIntent] = []
        if self.order_intent is not None:
            out.append(self.order_intent)
        if self.protective_plan is not None:
            out.extend(self.protective_plan.intents)
        return out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["order_intent"] = None if self.order_intent is None else self.order_intent.to_dict()
        d["protective_plan"] = None if self.protective_plan is None else self.protective_plan.to_dict()
        d["intents"] = [intent.to_dict() for intent in self.intents]
        return d


def _client_id(prefix: str, role: str) -> str:
    return f"{prefix}_{role}_{uuid4().hex[:12]}"[:36]


def _positive_float(cfg: dict[str, Any], path: tuple[str, ...], default: float) -> float:
    node: Any = cfg
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return float(default)
        node = node[key]
    try:
        return float(node)
    except (TypeError, ValueError):
        return float(default)


def _native_protection_plan(
    cfg: dict[str, Any],
    *,
    quantity: float,
    entry_price: float,
    leverage: float,
    client_prefix: str,
) -> NativeProtectiveOrderPlan | None:
    native_cfg = cfg.get("native_protection", {})
    if not bool(native_cfg.get("enabled", True)):
        return None
    if quantity <= 0 or entry_price <= 0:
        return None

    sl, tp = protective_levels_from_percentages(
        entry_price=entry_price,
        stop_loss_pct=float(native_cfg.get("fallback_stop_loss_pct", 0.02)),
        take_profit_pct=float(native_cfg.get("fallback_take_profit_pct", 0.04)),
    )
    trailing_activation = None
    if bool(native_cfg.get("enable_trailing_stop", False)):
        trailing_activation = entry_price * (1.0 + float(native_cfg.get("trailing_activation_pct", 0.01)))

    return build_long_protective_order_plan(
        symbol=str(cfg["symbol"]["ccxt_symbol"]),
        quantity=float(quantity),
        entry_price=float(entry_price),
        stop_loss_price=float(sl),
        take_profit_price=float(tp),
        trailing_activation_price=trailing_activation,
        trailing_callback_rate=float(native_cfg.get("trailing_callback_rate", 1.0)),
        leverage=float(leverage),
        working_type=str(native_cfg.get("working_type", "MARK_PRICE")),
        position_side=str(native_cfg.get("position_side", "BOTH")),
        client_order_prefix=client_prefix,
        enable_stop_loss=bool(native_cfg.get("enable_stop_loss", True)),
        enable_take_profit=bool(native_cfg.get("enable_take_profit", True)),
        enable_trailing_stop=bool(native_cfg.get("enable_trailing_stop", False)),
    )


def build_target_position_plan(
    cfg: dict[str, Any],
    *,
    reference_price: float,
    equity_usdt: float,
    target_exposure: float,
    current_qty: float = 0.0,
    timestamp: str = "manual",
    leverage: float | None = None,
    reason: str = "ensemble_target_exposure",
    apply_demo_order_cap: bool | None = None,
    include_protective_plan: bool | None = None,
) -> TargetPositionPlan:
    """Convert target exposure into a neutral market/reduce-only order intent.

    This is the V1.6 core bridge between the ensemble paper signal and Demo/Testnet
    execution. It remains long-only and never creates short-opening orders.
    """
    price = float(reference_price)
    equity = float(equity_usdt)
    current_qty = max(0.0, float(current_qty))
    requested_exposure = max(0.0, float(target_exposure))
    if price <= 0:
        raise ValueError("reference_price must be positive")
    if equity <= 0:
        raise ValueError("equity_usdt must be positive")

    exec_cfg = cfg.get("ensemble_demo_execution", {})
    trading_cfg = cfg.get("trading", {})
    broker_safety = cfg.get("broker", {}).get("safety", {})
    symbol = str(cfg["symbol"]["ccxt_symbol"])
    lev = float(leverage if leverage is not None else exec_cfg.get("leverage", trading_cfg.get("leverage", 3.0)))
    max_exposure = float(exec_cfg.get("max_exposure", cfg.get("ensemble", {}).get("max_exposure", trading_cfg.get("max_notional_fraction", 3.0))))
    max_exposure = max(0.0, min(max_exposure, float(trading_cfg.get("max_notional_fraction", max_exposure))))
    min_rebalance_notional = float(exec_cfg.get("min_rebalance_notional", cfg.get("ensemble_paper", {}).get("min_rebalance_notional", 25.0)))
    order_type = str(exec_cfg.get("order_type", cfg.get("execution", {}).get("order_type", "market")))
    if apply_demo_order_cap is None:
        apply_demo_order_cap = bool(exec_cfg.get("apply_demo_order_cap", True))
    if include_protective_plan is None:
        include_protective_plan = bool(exec_cfg.get("attach_native_protection", False))

    warnings: list[str] = []
    if requested_exposure > max_exposure:
        warnings.append(f"target_exposure capped from {requested_exposure:.4f} to {max_exposure:.4f}")
    target_exposure_capped = min(requested_exposure, max_exposure)
    current_notional = current_qty * price
    current_exposure = current_notional / equity if equity > 0 else 0.0
    target_notional = equity * target_exposure_capped
    if target_exposure_capped <= 1e-12:
        target_notional = 0.0
    target_qty = target_notional / price
    raw_delta_notional = target_notional - current_notional

    action: TargetAction
    plan_reason: str
    if current_qty <= 0 and target_notional <= 0:
        action = "hold_flat"
        plan_reason = "already_flat_target_flat"
    elif current_qty > 0 and target_notional <= 0:
        action = "close"
        plan_reason = "target_exposure_zero"
    elif abs(raw_delta_notional) < min_rebalance_notional:
        action = "hold"
        plan_reason = "delta_below_min_rebalance_notional"
    elif raw_delta_notional > 0:
        action = "increase"
        plan_reason = "target_exposure_above_current"
    else:
        action = "reduce"
        plan_reason = "target_exposure_below_current"

    order_intent: OrderIntent | None = None
    expected_position_qty = current_qty
    delta_notional = raw_delta_notional
    delta_qty = raw_delta_notional / price
    client_prefix = str(exec_cfg.get("client_order_prefix", "btcqv16"))
    max_order_notional = None
    if apply_demo_order_cap:
        max_order_notional = broker_safety.get("max_order_notional_usdt")
        max_order_notional = None if max_order_notional is None else float(max_order_notional)

    if action == "increase":
        order_notional = max(0.0, raw_delta_notional)
        if max_order_notional is not None and order_notional > max_order_notional:
            warnings.append(f"increase order notional capped from {order_notional:.4f} to {max_order_notional:.4f} by demo safety cap")
            order_notional = max_order_notional
        qty = order_notional / price
        delta_notional = order_notional
        delta_qty = qty
        expected_position_qty = current_qty + qty
        if qty <= 0:
            action = "blocked"
            plan_reason = "capped_quantity_non_positive"
        else:
            order_intent = OrderIntent(
                symbol=symbol,
                side="buy",
                order_type=order_type,  # type: ignore[arg-type]
                quantity=float(qty),
                price=None if order_type == "market" else price,
                reduce_only=False,
                leverage=lev,
                client_order_id=_client_id(client_prefix, "inc"),
                reason=f"{reason}:increase_to_target_exposure",
            )
    elif action in {"reduce", "close"}:
        desired_sell_notional = current_notional if action == "close" else abs(raw_delta_notional)
        if max_order_notional is not None and desired_sell_notional > max_order_notional:
            warnings.append(f"reduce order notional capped from {desired_sell_notional:.4f} to {max_order_notional:.4f} by demo safety cap")
            desired_sell_notional = max_order_notional
        qty = min(current_qty, desired_sell_notional / price)
        delta_notional = -qty * price
        delta_qty = -qty
        expected_position_qty = max(0.0, current_qty - qty)
        if qty <= 0:
            action = "blocked"
            plan_reason = "capped_quantity_non_positive"
        else:
            order_intent = OrderIntent(
                symbol=symbol,
                side="sell",
                order_type=order_type,  # type: ignore[arg-type]
                quantity=float(qty),
                price=None if order_type == "market" else price,
                reduce_only=True,
                leverage=lev,
                client_order_id=_client_id(client_prefix, "red" if action == "reduce" else "cls"),
                reason=f"{reason}:{action}_to_target_exposure",
            )

    protective_plan = None
    if include_protective_plan and expected_position_qty > 0 and action in {"increase", "hold"}:
        protective_plan = _native_protection_plan(
            cfg,
            quantity=expected_position_qty,
            entry_price=price,
            leverage=lev,
            client_prefix=client_prefix,
        )
        if protective_plan is not None:
            warnings.extend(protective_plan.warnings)

    if order_intent is not None:
        order_intent.validate()
    if protective_plan is not None:
        for intent in protective_plan.intents:
            intent.validate()

    return TargetPositionPlan(
        symbol=symbol,
        timestamp=str(timestamp),
        reference_price=price,
        equity_usdt=equity,
        leverage=lev,
        current_qty=current_qty,
        current_notional=current_notional,
        current_exposure=current_exposure,
        target_exposure_requested=requested_exposure,
        target_exposure=target_exposure_capped,
        target_notional=target_notional,
        target_qty=target_qty,
        delta_notional=delta_notional,
        delta_qty=delta_qty,
        action=action,
        reason=f"{reason}:{plan_reason}",
        order_intent=order_intent,
        expected_position_qty=expected_position_qty,
        protective_plan=protective_plan,
        warnings=warnings,
    )
