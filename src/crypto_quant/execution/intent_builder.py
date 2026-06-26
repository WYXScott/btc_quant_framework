from __future__ import annotations

from typing import Any

from crypto_quant.exchange.order_intent import OrderIntent
from crypto_quant.exchange.position_sizing import btc_quantity_from_notional
from crypto_quant.execution.decision import StrategyDecision
from crypto_quant.paper.account import PaperAccount


def build_order_intent_from_decision(
    decision: StrategyDecision,
    account: PaperAccount,
    cfg: dict[str, Any],
    *,
    order_type: str | None = None,
    max_order_notional_usdt: float | None = None,
) -> OrderIntent | None:
    """Convert a strategy decision into a broker-neutral OrderIntent.

    The conversion uses the same notional logic as the paper account:
    notional = equity * margin_fraction * leverage, capped by max_notional_fraction.
    For closing a long position, the current local/paper position quantity is used.
    """
    if not decision.requires_order:
        return None

    order_type = order_type or str(cfg.get("execution", {}).get("order_type", "market"))
    symbol = str(cfg["symbol"]["ccxt_symbol"])
    leverage = float(decision.leverage)

    if decision.action == "buy":
        qty = btc_quantity_from_notional(
            equity_usdt=float(decision.equity),
            reference_price=float(decision.price),
            margin_fraction=float(decision.margin_fraction),
            leverage=leverage,
            max_notional_fraction=float(cfg["trading"]["max_notional_fraction"]),
            max_order_notional_usdt=max_order_notional_usdt,
        )
        return OrderIntent(
            symbol=symbol,
            side="buy",
            order_type=order_type,  # type: ignore[arg-type]
            quantity=float(qty),
            price=None if order_type == "market" else float(decision.price),
            reduce_only=False,
            leverage=leverage,
            reason=decision.reason,
        )

    if decision.action == "sell":
        qty = abs(float(account.position_qty))
        if qty <= 0:
            return None
        return OrderIntent(
            symbol=symbol,
            side="sell",
            order_type=order_type,  # type: ignore[arg-type]
            quantity=float(qty),
            price=None if order_type == "market" else float(decision.price),
            reduce_only=True,
            leverage=leverage,
            reason=decision.reason,
        )

    return None
