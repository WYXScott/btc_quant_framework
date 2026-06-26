from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


OrderSide = Literal["buy", "sell"]
OrderType = Literal[
    "market",
    "limit",
    "stop_market",
    "take_profit_market",
    "trailing_stop_market",
]


@dataclass(frozen=True)
class OrderIntent:
    """A broker-neutral order request used before touching any exchange API.

    The project intentionally separates *decision generation* from *order execution*.
    Strategies should produce an OrderIntent first; execution adapters decide whether the
    intent is simulated locally, sent to a testnet, or blocked by safety checks.

    V0.7 extends this object to cover native exchange protective orders:
      - stop_market: reduce-only stop loss;
      - take_profit_market: reduce-only take profit;
      - trailing_stop_market: optional reduce-only trailing stop.

    All exchange-specific parameters stay optional and are interpreted by the broker
    adapter. The default scripts only preview these intents unless explicit testnet
    execution is requested with a confirmation phrase.
    """

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    reduce_only: bool = False
    leverage: float | None = None
    client_order_id: str | None = None
    reason: str = "strategy_signal"

    # Conditional/protective order parameters.
    stop_price: float | None = None
    activation_price: float | None = None
    callback_rate: float | None = None
    working_type: str | None = None       # MARK_PRICE | CONTRACT_PRICE, venue-specific
    close_position: bool = False
    position_side: str | None = None      # BOTH | LONG | SHORT, needed in hedge mode
    time_in_force: str | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.symbol:
            raise ValueError("OrderIntent.symbol is required")
        if self.side not in {"buy", "sell"}:
            raise ValueError(f"Unsupported side: {self.side}")
        allowed_types = {"market", "limit", "stop_market", "take_profit_market", "trailing_stop_market"}
        if self.order_type not in allowed_types:
            raise ValueError(f"Unsupported order_type: {self.order_type}")
        if self.quantity <= 0 and not self.close_position:
            raise ValueError("OrderIntent.quantity must be positive unless close_position=True")
        if self.order_type == "limit" and (self.price is None or self.price <= 0):
            raise ValueError("Limit orders require a positive price")
        if self.order_type in {"stop_market", "take_profit_market"} and (
            self.stop_price is None or self.stop_price <= 0
        ):
            raise ValueError(f"{self.order_type} requires a positive stop_price")
        if self.order_type == "trailing_stop_market":
            if self.callback_rate is None or self.callback_rate <= 0:
                raise ValueError("trailing_stop_market requires a positive callback_rate")
            if self.activation_price is not None and self.activation_price <= 0:
                raise ValueError("activation_price must be positive when provided")
        if self.leverage is not None and self.leverage <= 0:
            raise ValueError("Leverage must be positive when provided")
        if self.close_position and self.reduce_only:
            # Binance USD-M docs specify that reduceOnly should not be sent together
            # with closePosition=true. Keep the invariant in the neutral intent too.
            raise ValueError("close_position=True cannot be combined with reduce_only=True")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)
