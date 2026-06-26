from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_quant.paper.account import PaperAccount


@dataclass
class RebalancePlan:
    timestamp: str
    price: float
    equity: float
    current_qty: float
    current_notional: float
    current_exposure: float
    target_exposure: float
    target_notional: float
    delta_notional: float
    action: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "price": self.price,
            "equity": self.equity,
            "current_qty": self.current_qty,
            "current_notional": self.current_notional,
            "current_exposure": self.current_exposure,
            "target_exposure": self.target_exposure,
            "target_notional": self.target_notional,
            "delta_notional": self.delta_notional,
            "action": self.action,
            "reason": self.reason,
        }


class DynamicPaperBroker:
    """Local long-only paper broker that rebalances toward target notional exposure.

    target_exposure convention:
        0.0 = flat
        1.0 = notional exposure equal to current equity
        3.0 = notional exposure equal to 3x current equity

    This broker is deliberately conservative and local-only. It is meant to test
    whether an ensemble/dynamic-positioning signal can be run as a stateful paper
    strategy before any Demo/Testnet order routing is considered.
    """

    def __init__(
        self,
        account: PaperAccount,
        fee_rate: float = 0.0005,
        slippage_rate: float = 0.0005,
        min_rebalance_notional: float = 25.0,
        max_exposure: float = 3.0,
    ) -> None:
        self.account = account
        self.fee_rate = float(fee_rate)
        self.slippage_rate = float(slippage_rate)
        self.min_rebalance_notional = float(min_rebalance_notional)
        self.max_exposure = float(max_exposure)
        if self.max_exposure <= 0:
            raise ValueError("max_exposure must be positive")

    def current_exposure(self, price: float) -> float:
        equity = max(float(self.account.mark_to_market(price)), 1e-12)
        return float(self.account.position_notional(price) / equity)

    def plan_rebalance(self, price: float, target_exposure: float, timestamp: str, reason: str = "dynamic_target") -> RebalancePlan:
        price = float(price)
        equity = max(float(self.account.mark_to_market(price)), 0.0)
        current_qty = abs(float(self.account.position_qty)) if self.account.in_position else 0.0
        current_notional = current_qty * price
        current_exposure = current_notional / equity if equity > 0 else 0.0
        target_exposure = max(0.0, min(float(target_exposure), self.max_exposure))
        target_notional = equity * target_exposure
        if target_exposure <= 1e-12:
            target_notional = 0.0
        delta_notional = target_notional - current_notional

        if equity <= 0:
            action = "blocked"
            plan_reason = "non_positive_equity"
        elif current_qty <= 0 and target_notional <= 0:
            action = "hold_flat"
            plan_reason = "already_flat_target_flat"
        elif current_qty > 0 and target_notional <= 0:
            action = "close"
            plan_reason = "target_exposure_zero"
        elif abs(delta_notional) < self.min_rebalance_notional:
            action = "hold"
            plan_reason = "delta_below_min_rebalance_notional"
        elif delta_notional > 0:
            action = "increase"
            plan_reason = "target_exposure_above_current"
        else:
            action = "reduce"
            plan_reason = "target_exposure_below_current"

        return RebalancePlan(
            timestamp=str(timestamp),
            price=price,
            equity=equity,
            current_qty=current_qty,
            current_notional=current_notional,
            current_exposure=current_exposure,
            target_exposure=target_exposure,
            target_notional=target_notional,
            delta_notional=delta_notional,
            action=action,
            reason=f"{reason}:{plan_reason}",
        )

    def _buy_delta(
        self,
        price: float,
        notional: float,
        timestamp: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
        protective_levels: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fill_price = float(price) * (1.0 + self.slippage_rate)
        notional = max(0.0, float(notional))
        qty = notional / fill_price if fill_price > 0 else 0.0
        fee = notional * self.fee_rate
        old_qty = abs(float(self.account.position_qty)) if self.account.in_position else 0.0
        old_entry = float(self.account.entry_price) if self.account.entry_price is not None else fill_price
        new_qty = old_qty + qty
        if new_qty <= 0:
            return {"timestamp": timestamp, "side": "buy", "status": "ignored", "reason": "zero_quantity"}

        weighted_entry = (old_qty * old_entry + qty * fill_price) / new_qty
        self.account.cash -= fee
        self.account.position_qty = float(new_qty)
        self.account.entry_price = float(weighted_entry)
        self.account.entry_timestamp = self.account.entry_timestamp or timestamp
        if protective_levels:
            self.account.stop_loss_price = protective_levels.get("stop_loss_price")
            self.account.take_profit_price = protective_levels.get("take_profit_price")
            self.account.trailing_stop_price = protective_levels.get("trailing_stop_price")
            self.account.highest_price_since_entry = protective_levels.get("highest_price_since_entry", fill_price)
        elif self.account.highest_price_since_entry is None:
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
            "target_exposure": metadata.get("target_exposure") if metadata else None,
            "current_exposure_before": metadata.get("current_exposure_before") if metadata else None,
            "rebalance_action": metadata.get("rebalance_action") if metadata else None,
        }
        if metadata:
            order.update({k: v for k, v in metadata.items() if k not in order})
        self.account.orders.append(order)
        return order

    def _sell_delta(
        self,
        price: float,
        notional: float,
        timestamp: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
        close_all: bool = False,
    ) -> dict[str, Any]:
        if not self.account.in_position:
            return {"timestamp": timestamp, "side": "sell", "status": "ignored", "reason": "no_position"}
        fill_price = float(price) * (1.0 - self.slippage_rate)
        current_qty = abs(float(self.account.position_qty))
        qty = current_qty if close_all else min(current_qty, max(0.0, float(notional)) / fill_price)
        if qty <= 0:
            return {"timestamp": timestamp, "side": "sell", "status": "ignored", "reason": "zero_quantity"}
        executed_notional = qty * fill_price
        fee = executed_notional * self.fee_rate
        pnl = qty * (fill_price - float(self.account.entry_price)) - fee
        self.account.cash += pnl
        self.account.realized_pnl += pnl
        order = {
            "timestamp": timestamp,
            "side": "sell",
            "price": float(fill_price),
            "qty": float(qty),
            "notional": float(executed_notional),
            "fee": float(fee),
            "pnl": float(pnl),
            "status": "filled",
            "reason": reason,
            "target_exposure": metadata.get("target_exposure") if metadata else None,
            "current_exposure_before": metadata.get("current_exposure_before") if metadata else None,
            "rebalance_action": metadata.get("rebalance_action") if metadata else None,
        }
        if metadata:
            order.update({k: v for k, v in metadata.items() if k not in order})
        remaining = current_qty - qty
        if remaining <= 1e-12 or close_all:
            self.account.register_closed_trade(pnl, timestamp)
            self.account.reset_position_state()
        else:
            self.account.position_qty = float(remaining)
            # Keep the old entry price for the remaining partial position.
        self.account.orders.append(order)
        self.account.mark_to_market(price)
        return order

    def rebalance_to_exposure(
        self,
        price: float,
        target_exposure: float,
        timestamp: str,
        reason: str = "dynamic_target",
        metadata: dict[str, Any] | None = None,
        protective_levels: dict[str, Any] | None = None,
    ) -> tuple[RebalancePlan, dict[str, Any] | None]:
        plan = self.plan_rebalance(price=price, target_exposure=target_exposure, timestamp=timestamp, reason=reason)
        meta = dict(metadata or {})
        meta.update(
            {
                "target_exposure": plan.target_exposure,
                "target_notional": plan.target_notional,
                "current_exposure_before": plan.current_exposure,
                "current_notional_before": plan.current_notional,
                "delta_notional": plan.delta_notional,
                "rebalance_action": plan.action,
            }
        )
        if plan.action in {"hold_flat", "hold", "blocked"}:
            self.account.mark_to_market(price)
            return plan, None
        if plan.action == "increase":
            return plan, self._buy_delta(price, plan.delta_notional, timestamp, plan.reason, meta, protective_levels)
        if plan.action == "reduce":
            return plan, self._sell_delta(price, abs(plan.delta_notional), timestamp, plan.reason, meta, close_all=False)
        if plan.action == "close":
            return plan, self._sell_delta(price, plan.current_notional, timestamp, plan.reason, meta, close_all=True)
        return plan, None
