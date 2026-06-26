from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PaperAccount:
    """Stateful leveraged long-only paper account.

    The account intentionally keeps the accounting simple and conservative enough for
    research/paper trading:
      - cash is reduced by fees and realized PnL only;
      - margin is tracked through position notional and leverage but is not moved to a
        separate locked-margin ledger;
      - equity = cash + unrealized PnL.

    V0.6 adds explicit protective-order state and circuit-breaker state. These fields
    are still local-paper approximations, not exchange liquidation/risk-engine formulas.
    """

    equity: float = 1000.0
    cash: float = 1000.0
    position_qty: float = 0.0
    entry_price: float | None = None
    leverage: float = 3.0
    realized_pnl: float = 0.0
    entry_timestamp: str | None = None
    last_update_timestamp: str | None = None
    bars_held: int = 0

    # Protective order state for the current long position.
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    trailing_stop_price: float | None = None
    highest_price_since_entry: float | None = None

    # Circuit breaker state.
    consecutive_losses: int = 0
    risk_pause_until: str | None = None
    daily_loss_date: str | None = None
    daily_realized_pnl: float = 0.0

    orders: list[dict] = field(default_factory=list)

    @property
    def in_position(self) -> bool:
        return self.position_qty != 0 and self.entry_price is not None

    def unrealized_pnl(self, price: float) -> float:
        if not self.in_position:
            return 0.0
        return float(self.position_qty * (price - float(self.entry_price)))

    def position_notional(self, price: float) -> float:
        if not self.in_position:
            return 0.0
        return float(abs(self.position_qty) * price)

    def mark_to_market(self, price: float) -> float:
        self.equity = float(self.cash + self.unrealized_pnl(price))
        return self.equity

    def estimated_long_liquidation_price(self, maintenance_margin_rate: float = 0.005) -> float | None:
        """Approximate liquidation price for isolated long exposure.

        This proxy is intentionally conservative and should only be used as a warning
        signal in paper trading. Real exchanges have venue-specific formulas.
        """
        if not self.in_position or not self.entry_price or self.leverage <= 0:
            return None
        distance = max(0.0, 1.0 / self.leverage - maintenance_margin_rate)
        return float(self.entry_price * (1.0 - distance))

    def reset_position_state(self) -> None:
        """Clear all position and protective-order fields after closing."""
        self.position_qty = 0.0
        self.entry_price = None
        self.entry_timestamp = None
        self.bars_held = 0
        self.stop_loss_price = None
        self.take_profit_price = None
        self.trailing_stop_price = None
        self.highest_price_since_entry = None

    def update_daily_realized_pnl(self, timestamp: str | None, pnl: float) -> None:
        """Update realized PnL for the UTC calendar date of the supplied timestamp."""
        date_key = str(timestamp or "")[:10]
        if not date_key:
            date_key = "unknown"
        if self.daily_loss_date != date_key:
            self.daily_loss_date = date_key
            self.daily_realized_pnl = 0.0
        self.daily_realized_pnl += float(pnl)

    def register_closed_trade(self, pnl: float, timestamp: str | None) -> None:
        """Update loss-streak and daily PnL state after a filled exit order."""
        pnl = float(pnl)
        self.update_daily_realized_pnl(timestamp, pnl)
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
