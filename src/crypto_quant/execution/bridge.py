from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.order_intent import OrderIntent
from crypto_quant.exchange.safety import ExecutionSafetyGuard
from crypto_quant.execution.decision import StrategyDecision
from crypto_quant.execution.intent_builder import build_order_intent_from_decision
from crypto_quant.paper.account import PaperAccount
from crypto_quant.paper.broker import PaperBroker


@dataclass
class ExecutionBridgeResult:
    mode: str
    status: str
    dry_run: bool
    decision: dict[str, Any]
    intent: dict[str, Any] | None = None
    order: dict[str, Any] | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExecutionBridge:
    """Routes broker-neutral decisions to a selected execution backend.

    Supported modes in v0.5:
      - local_paper: execute against the local PaperAccount/PaperBroker.
      - binance_futures_demo: convert to OrderIntent and preview/submit to the
        Binance USD-M futures demo/testnet adapter. Dry-run remains default.

    The bridge keeps strategy code independent from exchange-specific execution.
    """

    def __init__(
        self,
        cfg: dict[str, Any],
        account: PaperAccount,
        *,
        mode: str | None = None,
    ):
        self.cfg = cfg
        self.account = account
        self.mode = mode or str(cfg.get("execution", {}).get("mode", "local_paper"))

    @property
    def safety(self) -> ExecutionSafetyGuard:
        return ExecutionSafetyGuard.from_config(self.cfg)

    def build_intent(self, decision: StrategyDecision) -> OrderIntent | None:
        broker_cap = None
        if self.mode == "binance_futures_demo":
            broker_cap = self.safety.cfg.max_order_notional_usdt
        return build_order_intent_from_decision(
            decision=decision,
            account=self.account,
            cfg=self.cfg,
            max_order_notional_usdt=broker_cap,
        )

    def execute(
        self,
        decision: StrategyDecision,
        *,
        execute: bool = False,
        confirmation: str | None = None,
    ) -> ExecutionBridgeResult:
        if not decision.requires_order:
            return ExecutionBridgeResult(
                mode=self.mode,
                status="no_order_required",
                dry_run=True,
                decision=decision.to_dict(),
                message=f"Decision action={decision.action!r} does not require execution.",
            )

        intent = self.build_intent(decision)
        if intent is None:
            return ExecutionBridgeResult(
                mode=self.mode,
                status="no_intent",
                dry_run=True,
                decision=decision.to_dict(),
                message="Decision could not be converted to an OrderIntent.",
            )

        if self.mode == "local_paper":
            broker = PaperBroker(
                self.account,
                fee_rate=float(self.cfg["trading"]["fee_rate"]),
                slippage_rate=float(self.cfg["trading"]["slippage_rate"]),
            )
            metadata = {"prob_up": decision.prob_up, "signal": decision.signal}
            if decision.metadata:
                metadata.update({k: v for k, v in decision.metadata.items() if k != "protective_levels"})
            if decision.action == "buy":
                order = broker.buy_with_margin_fraction(
                    price=float(decision.price),
                    margin_fraction=float(decision.margin_fraction),
                    leverage=float(decision.leverage),
                    timestamp=decision.timestamp,
                    reason=decision.reason,
                    metadata=metadata,
                    protective_levels=(decision.metadata or {}).get("protective_levels"),
                )
            else:
                order = broker.close_long(
                    price=float(decision.price),
                    timestamp=decision.timestamp,
                    reason=decision.reason,
                    metadata=metadata,
                    fill_price_override=(decision.metadata or {}).get("execution_price"),
                )
            return ExecutionBridgeResult(
                mode=self.mode,
                status=str(order.get("status", "unknown")),
                dry_run=False,
                decision=decision.to_dict(),
                intent=intent.to_dict(),
                order=order,
                message="Executed on local PaperBroker.",
            )

        if self.mode == "binance_futures_demo":
            demo = BinanceFuturesDemoBroker(self.cfg, require_private=execute)
            response = demo.place_order(
                intent,
                reference_price=float(decision.price),
                execute=execute,
                confirmation=confirmation,
            )
            return ExecutionBridgeResult(
                mode=self.mode,
                status=response.status,
                dry_run=response.dry_run,
                decision=decision.to_dict(),
                intent=response.intent,
                order=response.response,
                message=response.message,
            )

        raise ValueError(f"Unsupported execution mode: {self.mode}")
