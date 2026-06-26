from __future__ import annotations


def btc_quantity_from_notional(
    equity_usdt: float,
    reference_price: float,
    margin_fraction: float,
    leverage: float,
    max_notional_fraction: float,
    max_order_notional_usdt: float | None = None,
) -> float:
    """Return BTC quantity using the same notional logic as the paper engine."""
    if equity_usdt <= 0:
        raise ValueError("equity_usdt must be positive")
    if reference_price <= 0:
        raise ValueError("reference_price must be positive")
    if margin_fraction <= 0 or leverage <= 0:
        raise ValueError("margin_fraction and leverage must be positive")
    notional = equity_usdt * margin_fraction * leverage
    notional = min(notional, equity_usdt * max_notional_fraction)
    if max_order_notional_usdt is not None:
        notional = min(notional, max_order_notional_usdt)
    return notional / reference_price
