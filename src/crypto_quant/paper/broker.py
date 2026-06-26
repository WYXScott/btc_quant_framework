from __future__ import annotations

from crypto_quant.paper.account import PaperAccount


class PaperBroker:
    """Minimal long-only paper broker for one BTC/USDT instrument."""

    def __init__(self, account: PaperAccount, fee_rate: float = 0.0005, slippage_rate: float = 0.0005):
        self.account = account
        self.fee_rate = float(fee_rate)
        self.slippage_rate = float(slippage_rate)

    def buy_with_margin_fraction(
        self,
        price: float,
        margin_fraction: float,
        leverage: float,
        timestamp: str | None = None,
        reason: str = "entry_signal",
        metadata: dict | None = None,
        protective_levels: dict | None = None,
    ) -> dict:
        if self.account.in_position:
            return {"status": "ignored", "reason": "already in position"}

        equity = self.account.mark_to_market(price)
        margin = equity * float(margin_fraction)
        notional = margin * float(leverage)
        fill_price = price * (1.0 + self.slippage_rate)
        qty = notional / fill_price
        fee = notional * self.fee_rate

        self.account.cash -= fee
        self.account.position_qty = float(qty)
        self.account.entry_price = float(fill_price)
        self.account.leverage = float(leverage)
        self.account.entry_timestamp = timestamp
        self.account.bars_held = 0
        if protective_levels:
            self.account.stop_loss_price = protective_levels.get("stop_loss_price")
            self.account.take_profit_price = protective_levels.get("take_profit_price")
            self.account.trailing_stop_price = protective_levels.get("trailing_stop_price")
            self.account.highest_price_since_entry = protective_levels.get("highest_price_since_entry", fill_price)
        else:
            self.account.highest_price_since_entry = fill_price
        self.account.mark_to_market(price)

        order = {
            "timestamp": timestamp,
            "side": "buy",
            "price": float(fill_price),
            "qty": float(qty),
            "notional": float(notional),
            "fee": float(fee),
            "pnl": 0.0,
            "status": "filled",
            "reason": reason,
        }
        if metadata:
            order.update(metadata)
        self.account.orders.append(order)
        return order

    def close_long(
        self,
        price: float,
        timestamp: str | None = None,
        reason: str = "exit_signal",
        metadata: dict | None = None,
        fill_price_override: float | None = None,
    ) -> dict:
        if not self.account.in_position:
            return {"status": "ignored", "reason": "no position"}

        fill_price = float(fill_price_override) if fill_price_override is not None else price * (1.0 - self.slippage_rate)
        qty = float(self.account.position_qty)
        notional = qty * fill_price
        fee = notional * self.fee_rate
        pnl = qty * (fill_price - float(self.account.entry_price)) - fee

        self.account.cash += pnl
        self.account.realized_pnl += pnl
        order = {
            "timestamp": timestamp,
            "side": "sell",
            "price": float(fill_price),
            "qty": qty,
            "notional": float(notional),
            "fee": float(fee),
            "pnl": float(pnl),
            "status": "filled",
            "reason": reason,
        }
        if metadata:
            order.update(metadata)
        self.account.reset_position_state()
        self.account.orders.append(order)
        self.account.mark_to_market(price)
        return order
