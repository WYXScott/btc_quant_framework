from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pandas as pd

from crypto_quant.paper.account import PaperAccount


@dataclass
class CircuitBreakerDecision:
    allowed: bool
    reason: str
    risk_pause_until: str | None = None


def _to_utc_timestamp(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


class CircuitBreaker:
    """Account-level risk stops for paper/demo execution.

    This layer is intentionally independent from the model. It blocks new entries
    after daily loss limits or consecutive loss streaks are reached.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.risk_cfg = cfg.get("risk", {})
        self.initial_equity = float(cfg.get("trading", {}).get("initial_equity", 1000.0))

    def can_open_position(self, account: PaperAccount, timestamp: str) -> CircuitBreakerDecision:
        now = _to_utc_timestamp(timestamp)
        pause_until = _to_utc_timestamp(account.risk_pause_until)
        if now is not None and pause_until is not None and now < pause_until:
            return CircuitBreakerDecision(False, "risk_pause_active", account.risk_pause_until)

        date_key = str(timestamp)[:10]
        daily_pnl = float(account.daily_realized_pnl) if account.daily_loss_date == date_key else 0.0
        max_daily_loss = float(self.risk_cfg.get("max_daily_loss_fraction", 0.05)) * self.initial_equity
        if daily_pnl <= -abs(max_daily_loss):
            return CircuitBreakerDecision(False, "max_daily_loss_reached", account.risk_pause_until)

        return CircuitBreakerDecision(True, "risk_ok", account.risk_pause_until)

    def update_after_closed_trade(self, account: PaperAccount, pnl: float, timestamp: str) -> None:
        account.register_closed_trade(float(pnl), timestamp)
        max_losses = int(self.risk_cfg.get("pause_after_consecutive_losses", 3))
        if max_losses > 0 and account.consecutive_losses >= max_losses:
            bars = int(self.risk_cfg.get("pause_bars_after_consecutive_losses", 6))
            timeframe = str(self.cfg.get("data", {}).get("timeframe", "4h"))
            pause_delta = self._bars_to_timedelta(bars, timeframe)
            now = _to_utc_timestamp(timestamp) or pd.Timestamp.now(tz='UTC')
            account.risk_pause_until = (now + pause_delta).isoformat()

    @staticmethod
    def _bars_to_timedelta(bars: int, timeframe: str) -> timedelta:
        timeframe = timeframe.strip().lower()
        if timeframe.endswith("m"):
            return timedelta(minutes=int(timeframe[:-1]) * bars)
        if timeframe.endswith("h"):
            return timedelta(hours=int(timeframe[:-1]) * bars)
        if timeframe.endswith("d"):
            return timedelta(days=int(timeframe[:-1]) * bars)
        return timedelta(hours=4 * bars)
