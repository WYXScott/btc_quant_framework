from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from crypto_quant.exchange.order_intent import OrderIntent


@dataclass(frozen=True)
class NativeProtectiveOrderPlan:
    """A broker-neutral protective-order bundle for one long BTC position.

    The plan is intentionally expressed as OrderIntents, not as direct REST calls.
    This lets the same strategy generate a plan that can be previewed offline, logged,
    and only later submitted to a testnet/demo broker under the safety guard.
    """

    symbol: str
    position_side: str
    quantity: float
    entry_price: float
    stop_loss_price: float | None
    take_profit_price: float | None
    trailing_activation_price: float | None
    trailing_callback_rate: float | None
    stop_loss_intent: OrderIntent | None
    take_profit_intent: OrderIntent | None
    trailing_stop_intent: OrderIntent | None
    warnings: list[str]

    @property
    def intents(self) -> list[OrderIntent]:
        return [x for x in [self.stop_loss_intent, self.take_profit_intent, self.trailing_stop_intent] if x is not None]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "position_side": self.position_side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "trailing_activation_price": self.trailing_activation_price,
            "trailing_callback_rate": self.trailing_callback_rate,
            "stop_loss_intent": None if self.stop_loss_intent is None else self.stop_loss_intent.to_dict(),
            "take_profit_intent": None if self.take_profit_intent is None else self.take_profit_intent.to_dict(),
            "trailing_stop_intent": None if self.trailing_stop_intent is None else self.trailing_stop_intent.to_dict(),
            "warnings": self.warnings,
        }


def _client_id(prefix: str, role: str) -> str:
    # Binance client order ids are limited. Keep this compact and deterministic enough for logs.
    token = uuid4().hex[:12]
    return f"{prefix}_{role}_{token}"[:36]


def build_long_protective_order_plan(
    *,
    symbol: str,
    quantity: float,
    entry_price: float,
    stop_loss_price: float | None,
    take_profit_price: float | None,
    trailing_activation_price: float | None = None,
    trailing_callback_rate: float | None = None,
    leverage: float | None = None,
    working_type: str | None = "MARK_PRICE",
    position_side: str = "BOTH",
    client_order_prefix: str = "btcq",
    enable_stop_loss: bool = True,
    enable_take_profit: bool = True,
    enable_trailing_stop: bool = False,
) -> NativeProtectiveOrderPlan:
    """Build reduce-only protective order intents for a long position.

    The generated order intents are suitable for Binance USD-M futures demo/testnet
    preview and submission. They are not submitted here.
    """
    if not symbol:
        raise ValueError("symbol is required")
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")

    warnings: list[str] = []
    if stop_loss_price is not None and stop_loss_price >= entry_price:
        warnings.append("For a long position, stop_loss_price is expected to be below entry_price.")
    if take_profit_price is not None and take_profit_price <= entry_price:
        warnings.append("For a long position, take_profit_price is expected to be above entry_price.")
    if enable_trailing_stop and trailing_callback_rate is None:
        warnings.append("Trailing stop was enabled but trailing_callback_rate is missing; trailing stop intent omitted.")

    common = {
        "symbol": symbol,
        "side": "sell",
        "quantity": float(quantity),
        "reduce_only": True,
        "leverage": leverage,
        "working_type": working_type,
        "position_side": position_side,
    }

    stop_intent = None
    if enable_stop_loss and stop_loss_price is not None:
        stop_intent = OrderIntent(
            **common,
            order_type="stop_market",
            stop_price=float(stop_loss_price),
            client_order_id=_client_id(client_order_prefix, "sl"),
            reason="native_stop_loss_reduce_only",
        )

    tp_intent = None
    if enable_take_profit and take_profit_price is not None:
        tp_intent = OrderIntent(
            **common,
            order_type="take_profit_market",
            stop_price=float(take_profit_price),
            client_order_id=_client_id(client_order_prefix, "tp"),
            reason="native_take_profit_reduce_only",
        )

    trailing_intent = None
    if enable_trailing_stop and trailing_callback_rate is not None:
        trailing_intent = OrderIntent(
            **common,
            order_type="trailing_stop_market",
            activation_price=trailing_activation_price,
            callback_rate=float(trailing_callback_rate),
            client_order_id=_client_id(client_order_prefix, "ts"),
            reason="native_trailing_stop_reduce_only",
        )

    plan = NativeProtectiveOrderPlan(
        symbol=symbol,
        position_side=position_side,
        quantity=float(quantity),
        entry_price=float(entry_price),
        stop_loss_price=None if stop_loss_price is None else float(stop_loss_price),
        take_profit_price=None if take_profit_price is None else float(take_profit_price),
        trailing_activation_price=None if trailing_activation_price is None else float(trailing_activation_price),
        trailing_callback_rate=None if trailing_callback_rate is None else float(trailing_callback_rate),
        stop_loss_intent=stop_intent,
        take_profit_intent=tp_intent,
        trailing_stop_intent=trailing_intent,
        warnings=warnings,
    )
    # Validate immediately so scripts fail before any network call.
    for intent in plan.intents:
        intent.validate()
    return plan


def protective_levels_from_percentages(
    *,
    entry_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> tuple[float, float]:
    """Fallback protective levels when ATR is unavailable."""
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if stop_loss_pct <= 0 or take_profit_pct <= 0:
        raise ValueError("stop_loss_pct and take_profit_pct must be positive")
    return entry_price * (1.0 - stop_loss_pct), entry_price * (1.0 + take_profit_pct)
