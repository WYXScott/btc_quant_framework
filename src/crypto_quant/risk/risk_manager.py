from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    margin_fraction: float
    leverage: float
    notional_fraction: float


class RiskManager:
    """Centralized risk checks for leveraged BTC trading."""

    def __init__(
        self,
        max_leverage: float,
        max_margin_fraction: float,
        max_notional_fraction: float,
        min_liquidation_buffer: float,
    ) -> None:
        self.max_leverage = float(max_leverage)
        self.max_margin_fraction = float(max_margin_fraction)
        self.max_notional_fraction = float(max_notional_fraction)
        self.min_liquidation_buffer = float(min_liquidation_buffer)

    def validate_order(self, leverage: float, margin_fraction: float) -> RiskDecision:
        if leverage <= 0:
            return RiskDecision(False, "leverage must be positive", 0.0, leverage, 0.0)
        if leverage > self.max_leverage:
            return RiskDecision(False, "leverage exceeds configured max_leverage", 0.0, leverage, 0.0)
        if margin_fraction <= 0:
            return RiskDecision(False, "margin_fraction must be positive", 0.0, leverage, 0.0)
        if margin_fraction > self.max_margin_fraction:
            return RiskDecision(False, "margin_fraction exceeds max_margin_fraction", 0.0, leverage, 0.0)
        notional_fraction = leverage * margin_fraction
        if notional_fraction > self.max_notional_fraction:
            return RiskDecision(False, "notional exposure exceeds max_notional_fraction", 0.0, leverage, notional_fraction)
        # Rough long-only liquidation distance proxy: 1/leverage minus maintenance/buffer.
        liquidation_distance = 1.0 / leverage
        if liquidation_distance < self.min_liquidation_buffer:
            return RiskDecision(False, "liquidation buffer too small for configured leverage", 0.0, leverage, notional_fraction)
        return RiskDecision(True, "ok", margin_fraction, leverage, notional_fraction)
