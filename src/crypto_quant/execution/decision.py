from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyDecision:
    """Broker-neutral strategy decision for one candle.

    A StrategyDecision is intentionally not an order. It records what the strategy
    wants to do and why. The execution bridge then converts the decision into an
    OrderIntent only when execution is required.
    """

    timestamp: str
    symbol: str
    price: float
    action: str                  # buy | sell | hold_cash | hold_position | skipped
    reason: str
    signal: int
    prob_up: float | None
    equity: float
    position_qty: float
    leverage: float
    margin_fraction: float
    notional_fraction: float
    risk_allowed: bool = True
    metadata: dict[str, Any] | None = None

    @property
    def requires_order(self) -> bool:
        return self.action in {"buy", "sell"}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
