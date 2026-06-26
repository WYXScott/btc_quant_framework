from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

import pandas as pd

from crypto_quant.paper.account import PaperAccount


@dataclass
class ProtectiveLevels:
    stop_loss_price: float | None
    take_profit_price: float | None
    trailing_stop_price: float | None
    highest_price_since_entry: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProtectiveExit:
    triggered: bool
    reason: str
    trigger_price: float | None = None
    execution_price: float | None = None
    metadata: dict[str, Any] | None = None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


class ProtectiveOrderManager:
    """Local-paper protective order simulator for leveraged long positions.

    Assumptions:
      - long-only in this version;
      - if stop-loss and take-profit are both crossed in the same candle, the simulator
        uses the conservative outcome configured in risk.conservative_same_bar_exit;
      - fills include the global slippage rate and are not exchange guarantees.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.risk_cfg = cfg.get("risk", {})
        self.trading_cfg = cfg.get("trading", {})
        self.atr_window = int(cfg.get("features", {}).get("atr_window", 14))

    @property
    def slippage_rate(self) -> float:
        return float(self.trading_cfg.get("slippage_rate", 0.0005))

    def atr_from_row(self, row: pd.Series) -> float:
        atr_col = f"atr_{self.atr_window}"
        return _safe_float(row.get(atr_col, 0.0), 0.0)

    def initial_levels(self, entry_reference_price: float, atr: float) -> ProtectiveLevels:
        entry = float(entry_reference_price)
        atr = float(atr)
        stop = None
        take = None
        trailing = None
        if atr > 0:
            stop = entry - atr * float(self.risk_cfg.get("stop_loss_atr_multiple", 2.5))
            take = entry + atr * float(self.risk_cfg.get("take_profit_atr_multiple", 4.0))
            if bool(self.risk_cfg.get("enable_trailing_stop", True)):
                trailing = entry - atr * float(self.risk_cfg.get("trailing_stop_atr_multiple", 3.0))
        return ProtectiveLevels(
            stop_loss_price=stop,
            take_profit_price=take,
            trailing_stop_price=trailing,
            highest_price_since_entry=entry,
        )

    def attach_initial_levels(self, account: PaperAccount, entry_reference_price: float, atr: float) -> ProtectiveLevels:
        levels = self.initial_levels(entry_reference_price, atr)
        account.stop_loss_price = levels.stop_loss_price
        account.take_profit_price = levels.take_profit_price
        account.trailing_stop_price = levels.trailing_stop_price
        account.highest_price_since_entry = levels.highest_price_since_entry
        return levels

    def update_trailing_state(self, account: PaperAccount, bar_high: float, atr: float) -> None:
        if not account.in_position:
            return
        high = float(bar_high)
        account.highest_price_since_entry = max(
            float(account.highest_price_since_entry or account.entry_price or high), high
        )
        if not bool(self.risk_cfg.get("enable_trailing_stop", True)) or atr <= 0:
            return
        candidate = account.highest_price_since_entry - atr * float(self.risk_cfg.get("trailing_stop_atr_multiple", 3.0))
        if account.trailing_stop_price is None:
            account.trailing_stop_price = float(candidate)
        else:
            account.trailing_stop_price = float(max(account.trailing_stop_price, candidate))

    def evaluate_long_exit(self, account: PaperAccount, row: pd.Series) -> ProtectiveExit:
        if not account.in_position:
            return ProtectiveExit(False, "no_position")

        bar_high = _safe_float(row.get("high", row.get("close")), 0.0)
        bar_low = _safe_float(row.get("low", row.get("close")), 0.0)
        close = _safe_float(row.get("close"), 0.0)
        atr = self.atr_from_row(row)
        self.update_trailing_state(account, bar_high=bar_high, atr=atr)

        # Liquidation-buffer exit is checked first because leveraged accounts must avoid
        # reaching the exchange liquidation region.
        liq = account.estimated_long_liquidation_price(
            maintenance_margin_rate=float(self.trading_cfg.get("maintenance_margin_rate", 0.005))
        )
        if liq is not None and bar_low <= liq * 1.05:
            trigger = max(liq * 1.05, bar_low)
            return ProtectiveExit(True, "liquidation_buffer_exit", trigger, trigger * (1 - self.slippage_rate), {"liquidation_price": liq})

        stop_hits: list[tuple[str, float]] = []
        if account.stop_loss_price is not None and bar_low <= float(account.stop_loss_price):
            stop_hits.append(("protective_stop_loss", float(account.stop_loss_price)))
        if account.trailing_stop_price is not None and bar_low <= float(account.trailing_stop_price):
            stop_hits.append(("protective_trailing_stop", float(account.trailing_stop_price)))
        take_hit = account.take_profit_price is not None and bar_high >= float(account.take_profit_price)

        if stop_hits and take_hit:
            same_bar_mode = str(self.risk_cfg.get("conservative_same_bar_exit", "stop_first"))
            if same_bar_mode == "take_profit_first":
                trigger = float(account.take_profit_price)
                return ProtectiveExit(True, "protective_take_profit_same_bar", trigger, trigger * (1 - self.slippage_rate))
            # Conservative default.
            reason, trigger = sorted(stop_hits, key=lambda x: x[1], reverse=True)[0]
            return ProtectiveExit(True, reason + "_same_bar", trigger, trigger * (1 - self.slippage_rate))

        if stop_hits:
            # For long positions, the highest triggered stop is the nearest active stop.
            reason, trigger = sorted(stop_hits, key=lambda x: x[1], reverse=True)[0]
            return ProtectiveExit(True, reason, trigger, trigger * (1 - self.slippage_rate))

        if take_hit:
            trigger = float(account.take_profit_price)
            return ProtectiveExit(True, "protective_take_profit", trigger, trigger * (1 - self.slippage_rate))

        return ProtectiveExit(False, "no_protective_exit", None, close)
