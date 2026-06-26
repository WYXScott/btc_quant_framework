from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.events import NormalizedExchangeEvent
from crypto_quant.exchange.order_state_machine import ExchangeOrderStateMachine, lifecycle_from_exchange_order_row, order_key_from_event
from crypto_quant.exchange.partial_fill import actions_for_order_lifecycle
from crypto_quant.exchange.recovery import compare_local_and_exchange_state
from crypto_quant.paper.database import PaperStore


@dataclass(frozen=True)
class SyncAction:
    action: str
    severity: str
    reason: str
    dry_run_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SyncReport:
    timestamp_utc: str
    source: str
    status: str
    recovery_check: dict[str, Any]
    actions: list[dict[str, Any]]
    exchange_position: dict[str, Any] | None
    open_order_count: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExchangeStateSynchronizer:
    """Bridge between exchange snapshots/events and the local SQLite audit store."""

    def __init__(self, cfg: dict[str, Any], store: PaperStore):
        self.cfg = cfg
        self.store = store

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def actions_from_recovery(recovery: dict[str, Any]) -> list[SyncAction]:
        warnings = recovery.get("warnings") or []
        actions: list[SyncAction] = []
        for warning in warnings:
            text = str(warning)
            low = text.lower()
            if "exchange snapshot is in position, but local account is flat" in low:
                actions.append(SyncAction("halt_and_manual_reconcile", "critical", text, dry_run_safe=True))
            elif "local account is in position, but exchange snapshot is flat" in low:
                actions.append(SyncAction("reset_or_archive_local_position_after_manual_check", "warning", text, dry_run_safe=True))
            elif "native protective orders are missing" in low:
                actions.append(SyncAction("replace_native_protective_orders", "critical", text, dry_run_safe=True))
            elif "differs from exchange quantity" in low:
                actions.append(SyncAction("halt_and_resync_position_quantity", "critical", text, dry_run_safe=True))
            else:
                actions.append(SyncAction("review", "warning", text, dry_run_safe=True))
        if not actions:
            actions.append(SyncAction("continue", "info", "Local and exchange states are consistent within configured checks."))
        return actions

    def build_offline_report(
        self,
        *,
        exchange_qty: float | None = None,
        open_order_count: int | None = None,
    ) -> SyncReport:
        from crypto_quant.exchange.recovery import ExchangePositionSnapshot

        account = self.store.load_account(
            initial_equity=float(self.cfg.get("trading", {}).get("initial_equity", 1000.0)),
            leverage=float(self.cfg.get("trading", {}).get("leverage", 3.0)),
        )
        exchange_position = None
        open_orders = None
        if exchange_qty is not None:
            exchange_position = ExchangePositionSnapshot(
                symbol=str(self.cfg.get("symbol", {}).get("ccxt_symbol", "BTC/USDT:USDT")),
                contracts=float(exchange_qty),
                side="long" if exchange_qty > 0 else None,
                entry_price=None,
                notional=None,
                raw={"offline_simulated": True},
            )
            open_orders = [{"type": "STOP_MARKET", "reduceOnly": True} for _ in range(int(open_order_count or 0))]
        result = compare_local_and_exchange_state(
            local_account=account,
            exchange_position=exchange_position,
            open_orders=open_orders,
            min_protective_order_count=int(self.cfg.get("native_protection", {}).get("min_protective_order_count", 1)),
        )
        actions = self.actions_from_recovery(result.to_dict())
        report = SyncReport(
            timestamp_utc=self._utc_now(),
            source="offline_simulated_exchange" if exchange_qty is not None else "local_only",
            status=result.status,
            recovery_check=result.to_dict(),
            actions=[a.to_dict() for a in actions],
            exchange_position=None if exchange_position is None else exchange_position.to_dict(),
            open_order_count=None if open_orders is None else len(open_orders),
        )
        self.store.append_reconciliation_run(report.to_dict())
        return report

    def fetch_and_record_snapshot(self) -> SyncReport:
        broker = BinanceFuturesDemoBroker(self.cfg, require_private=True)
        account = self.store.load_account(
            initial_equity=float(self.cfg.get("trading", {}).get("initial_equity", 1000.0)),
            leverage=float(self.cfg.get("trading", {}).get("leverage", 3.0)),
        )
        position = broker.fetch_position_snapshot()
        open_orders = broker.fetch_open_orders_snapshot()
        self.store.append_exchange_position_snapshot(position.to_dict())
        for order in open_orders:
            self.store.upsert_exchange_order_state(order)
        result = compare_local_and_exchange_state(
            local_account=account,
            exchange_position=position,
            open_orders=open_orders,
            min_protective_order_count=int(self.cfg.get("native_protection", {}).get("min_protective_order_count", 1)),
        )
        actions = self.actions_from_recovery(result.to_dict())
        report = SyncReport(
            timestamp_utc=self._utc_now(),
            source="binance_futures_demo_private_snapshot",
            status=result.status,
            recovery_check=result.to_dict(),
            actions=[a.to_dict() for a in actions],
            exchange_position=position.to_dict(),
            open_order_count=len(open_orders),
        )
        self.store.append_reconciliation_run(report.to_dict())
        return report

    def ingest_event(self, event: NormalizedExchangeEvent) -> list[SyncAction]:
        """Persist a normalized user-data event and produce conservative actions."""
        self.store.append_exchange_event(event.to_dict())
        actions: list[SyncAction] = []
        if event.kind == "order":
            self.store.upsert_exchange_order_state(event.to_dict())
            # V1.9: persist a complete lifecycle transition before suggesting recovery actions.
            key = order_key_from_event(event)
            previous = lifecycle_from_exchange_order_row(self.store.load_order_lifecycle(key))
            update = ExchangeOrderStateMachine(previous).apply_event(event)
            lifecycle = update.lifecycle
            self.store.upsert_order_lifecycle(lifecycle.to_dict())
            self.store.append_order_state_transition(update.transition.to_dict())
            lifecycle_actions = actions_for_order_lifecycle(
                lifecycle,
                cfg=self.cfg,
                open_orders=[],
                entry_price=lifecycle.average_price or lifecycle.last_fill_price,
            )
            for action in lifecycle_actions.actions:
                actions.append(
                    SyncAction(
                        str(action.get("action", "review_order_lifecycle")),
                        str(action.get("severity", "warning")),
                        lifecycle_actions.reason,
                        dry_run_safe=True,
                    )
                )
            if lifecycle_actions.protection_plan:
                self.store.append_protection_recalc_plan(lifecycle_actions.protection_plan)
            if event.is_reduce_only_exit_fill:
                actions.append(
                    SyncAction(
                        "cancel_remaining_protective_orders",
                        "critical",
                        "A reduce-only exit/protective order was filled; cancel any opposite protective orders after verifying position.",
                    )
                )
        elif event.kind == "account":
            self.store.append_exchange_position_snapshot(event.to_dict())
            if event.is_flat_position:
                actions.append(
                    SyncAction(
                        "verify_flat_then_cancel_open_reduce_only_orders",
                        "warning",
                        "Account update reports a flat position; verify no stale reduce-only protective orders remain.",
                    )
                )
        if not actions:
            actions.append(SyncAction("record_only", "info", "Event recorded; no automatic action required."))
        return actions
