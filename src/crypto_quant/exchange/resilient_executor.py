from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from crypto_quant.config import resolve_path
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.idempotency import IdempotencyStore, with_idempotent_client_order_id
from crypto_quant.exchange.order_intent import OrderIntent
from crypto_quant.exchange.retry import RetryExecutor, RetryPolicy


@dataclass(frozen=True)
class ResilientOrderResult:
    status: str
    dry_run: bool
    key: str
    client_order_id: str
    intent: dict[str, Any]
    retry: dict[str, Any] | None
    exchange_result: dict[str, Any] | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResilientExchangeExecutor:
    """Idempotent, retry-aware execution wrapper for Demo/Testnet orders.

    The class is deliberately broker-neutral at the call-site: it accepts an
    OrderIntent and protects it with deterministic clientOrderId, local
    idempotency ledger, retry classification, and audit-friendly result payloads.
    """

    def __init__(
        self,
        cfg: dict[str, Any],
        *,
        db_path: str | Path | None = None,
        broker_factory: Callable[[bool], BinanceFuturesDemoBroker] | None = None,
    ):
        self.cfg = cfg
        if db_path is None:
            db_path = cfg.get("exchange_resilience", {}).get("idempotency_db_path") or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
        self.store = IdempotencyStore(resolve_path(db_path))
        self.policy = RetryPolicy.from_config(cfg)
        self.retry_executor = RetryExecutor(self.policy)
        self.broker_factory = broker_factory

    @property
    def client_order_prefix(self) -> str:
        return str(
            self.cfg.get("exchange_resilience", {}).get("client_order_prefix")
            or self.cfg.get("ensemble_demo_execution", {}).get("client_order_prefix")
            or "btcqv18"
        )

    def _broker(self, require_private: bool) -> BinanceFuturesDemoBroker:
        if self.broker_factory is not None:
            return self.broker_factory(require_private)
        return BinanceFuturesDemoBroker(self.cfg, require_private=require_private)

    def submit_intent(
        self,
        intent: OrderIntent,
        *,
        reference_price: float,
        execute: bool = False,
        confirmation: str | None = None,
        time_bucket: str | None = None,
    ) -> ResilientOrderResult:
        safe_intent, key, fingerprint = with_idempotent_client_order_id(
            intent,
            prefix=self.client_order_prefix,
            time_bucket=time_bucket,
        )
        intent_dict = safe_intent.to_dict()
        if not execute:
            return ResilientOrderResult(
                status="preview",
                dry_run=True,
                key=key,
                client_order_id=str(safe_intent.client_order_id),
                intent=intent_dict,
                retry=None,
                exchange_result=None,
                message="Offline dry-run. Idempotency key and client_order_id were generated; no order was sent.",
            )

        reserved, existing = self.store.reserve(
            key=key,
            client_order_id=str(safe_intent.client_order_id),
            fingerprint=fingerprint,
            intent=intent_dict,
        )
        if not reserved and existing is not None:
            return ResilientOrderResult(
                status="duplicate_blocked",
                dry_run=True,
                key=key,
                client_order_id=existing.client_order_id,
                intent=existing.intent_json,
                retry=None,
                exchange_result=existing.result_json,
                message=f"Duplicate order intent blocked by idempotency ledger; existing status={existing.status}.",
            )

        def call_exchange() -> dict[str, Any]:
            broker = self._broker(require_private=True)
            result = broker.place_order(
                safe_intent,
                reference_price=reference_price,
                execute=True,
                confirmation=confirmation,
            )
            return {
                "status": result.status,
                "dry_run": result.dry_run,
                "intent": result.intent,
                "response": result.response,
                "message": result.message,
            }

        retry_result = self.retry_executor.run(call_exchange)
        for attempt in retry_result.attempts:
            self.store.append_attempt(key=key, client_order_id=str(safe_intent.client_order_id), attempt=attempt.to_dict())

        if retry_result.ok:
            payload = retry_result.value or {}
            self.store.update_status(key, status="submitted", result=payload, increment_attempts=True)
            return ResilientOrderResult(
                status="submitted",
                dry_run=False,
                key=key,
                client_order_id=str(safe_intent.client_order_id),
                intent=intent_dict,
                retry=retry_result.to_dict(),
                exchange_result=payload,
                message="Order submitted through resilient executor.",
            )

        err = retry_result.error
        status = "unknown_order_state" if err is not None and err.retryable else "failed"
        self.store.update_status(key, status=status, result=retry_result.to_dict(), increment_attempts=True)
        return ResilientOrderResult(
            status=status,
            dry_run=False,
            key=key,
            client_order_id=str(safe_intent.client_order_id),
            intent=intent_dict,
            retry=retry_result.to_dict(),
            exchange_result=None,
            message="Order failed after retry policy." if status == "failed" else "Retryable failure; order state must be reconciled before retrying manually.",
        )

    def submit_intents(
        self,
        intents: list[OrderIntent],
        *,
        reference_price: float,
        execute: bool = False,
        confirmation: str | None = None,
        time_bucket: str | None = None,
    ) -> dict[str, Any]:
        results = [
            self.submit_intent(
                intent,
                reference_price=reference_price,
                execute=execute,
                confirmation=confirmation,
                time_bucket=time_bucket,
            ).to_dict()
            for intent in intents
        ]
        status = "preview" if not execute else ("submitted" if all(r["status"] == "submitted" for r in results) else "partial_or_failed")
        return {"status": status, "dry_run": not execute, "num_orders": len(results), "orders": results}
