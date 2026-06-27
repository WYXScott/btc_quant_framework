from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionSafetyConfig:
    environment: str = "demo"             # demo | testnet | sandbox | live
    default_dry_run: bool = True
    allow_live_trading: bool = False
    require_confirmation_phrase: str = "I_UNDERSTAND_TESTNET_ORDER"
    max_order_notional_usdt: float = 50.0
    max_leverage: float = 10.0


class ExecutionSafetyGuard:
    """Centralized execution guard for demo/testnet/live adapters.

    The defaults are intentionally conservative:
    - dry-run is on by default;
    - live trading is blocked unless explicitly enabled;
    - notional and leverage are capped even in testnet mode.
    """

    def __init__(self, cfg: ExecutionSafetyConfig):
        self.cfg = cfg

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "ExecutionSafetyGuard":
        broker_cfg = cfg.get("broker", {})
        safety_cfg = broker_cfg.get("safety", {})
        return cls(
            ExecutionSafetyConfig(
                environment=str(broker_cfg.get("environment", "testnet")),
                default_dry_run=bool(safety_cfg.get("default_dry_run", True)),
                allow_live_trading=bool(safety_cfg.get("allow_live_trading", False)),
                require_confirmation_phrase=str(
                    safety_cfg.get("require_confirmation_phrase", "I_UNDERSTAND_TESTNET_ORDER")
                ),
                max_order_notional_usdt=float(safety_cfg.get("max_order_notional_usdt", 50.0)),
                max_leverage=float(safety_cfg.get("max_leverage", cfg.get("trading", {}).get("max_leverage", 10.0))),
            )
        )

    def validate_environment(self) -> None:
        env = self.cfg.environment.lower()
        if env not in {"demo", "testnet", "sandbox", "live"}:
            raise ValueError(f"Unsupported broker environment: {self.cfg.environment}")
        if env == "live" and not self.cfg.allow_live_trading:
            raise PermissionError(
                "Live trading is disabled by safety guard. Keep broker.environment='testnet' until the strategy has "
                "passed paper trading and demo trading checks."
            )

    def validate_order_limits(self, quantity: float, reference_price: float, leverage: float | None = None) -> None:
        if quantity <= 0:
            raise ValueError("Order quantity must be positive")
        if reference_price <= 0:
            raise ValueError("Reference price must be positive")
        notional = quantity * reference_price
        if notional > self.cfg.max_order_notional_usdt:
            raise PermissionError(
                f"Order notional {notional:.2f} USDT exceeds safety cap "
                f"{self.cfg.max_order_notional_usdt:.2f} USDT."
            )
        if leverage is not None and leverage > self.cfg.max_leverage:
            raise PermissionError(f"Leverage {leverage} exceeds safety cap {self.cfg.max_leverage}.")

    def validate_confirmation(self, execute: bool, confirmation: str | None) -> None:
        if not execute:
            return
        expected = self.cfg.require_confirmation_phrase
        if confirmation != expected:
            raise PermissionError(
                f"Execution requested but confirmation phrase is missing. Required phrase: {expected!r}"
            )
