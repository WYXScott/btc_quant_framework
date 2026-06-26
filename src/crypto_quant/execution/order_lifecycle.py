from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class PendingOrder:
    """A simple local-paper limit/stop order ticket.

    This class is intentionally exchange-neutral. It is used to test whether a pending
    order would have filled or timed out during historical candle replay.
    """

    order_id: str
    created_timestamp: str
    side: str                 # buy | sell
    order_type: str           # limit | stop_market
    price: float
    qty: float
    reason: str
    status: str = "open"      # open | filled | canceled | expired
    age_bars: int = 0
    filled_timestamp: str | None = None
    filled_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrderLifecycleSimulator:
    """Simulate pending-order fills and timeout cancellation on OHLC bars."""

    def __init__(self, max_order_age_bars: int = 1, slippage_rate: float = 0.0005):
        self.max_order_age_bars = int(max_order_age_bars)
        self.slippage_rate = float(slippage_rate)

    def update(self, order: PendingOrder, *, timestamp: str, high: float, low: float) -> PendingOrder:
        if order.status != "open":
            return order
        order.age_bars += 1
        high = float(high)
        low = float(low)
        price = float(order.price)

        filled = False
        if order.order_type == "limit":
            if order.side == "buy" and low <= price:
                filled = True
            elif order.side == "sell" and high >= price:
                filled = True
        elif order.order_type == "stop_market":
            if order.side == "buy" and high >= price:
                filled = True
            elif order.side == "sell" and low <= price:
                filled = True

        if filled:
            order.status = "filled"
            order.filled_timestamp = timestamp
            slip = 1 + self.slippage_rate if order.side == "buy" else 1 - self.slippage_rate
            order.filled_price = price * slip
            return order

        if order.age_bars >= self.max_order_age_bars:
            order.status = "expired"
        return order
