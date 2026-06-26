from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from crypto_quant.alerts import AlertMessage, AlertRouter
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.sync import SyncAction, SyncReport
from crypto_quant.paper.database import PaperStore


@dataclass(frozen=True)
class RecoveryExecutionResult:
    timestamp_utc: str
    action: str
    severity: str
    reason: str
    status: str
    dry_run: bool
    execute_requested: bool
    result: dict[str, Any]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecoveryActionExecutor:
    """Safely convert reconciliation actions into controlled recovery operations.

    Design principle:
    - critical position mismatches never trigger automatic market orders;
    - automatic actions are restricted to low-risk cleanup such as cancel-all;
    - every operation defaults to dry-run and is auditable in SQLite.
    """

    def __init__(self, cfg: dict[str, Any], store: PaperStore, *, alert_router: AlertRouter | None = None):
        self.cfg = cfg
        self.store = store
        self.recovery_cfg = cfg.get("auto_recovery", {}) or {}
        self.alert_router = alert_router or AlertRouter.from_config(cfg)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _record_alert(self, *, level: str, title: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        delivery = self.alert_router.notify(AlertMessage(level=level, title=title, message=message, payload=payload))
        try:
            self.store.append_alert(delivery)
        except Exception:
            # Alert persistence must not stop the safety path.
            pass
        return delivery

    def _record_result(self, result: RecoveryExecutionResult) -> RecoveryExecutionResult:
        self.store.append_recovery_action(result.to_dict())
        if result.severity in {"critical", "warning"} or result.status in {"blocked", "failed"}:
            self._record_alert(
                level=result.severity,
                title=f"Recovery action: {result.action}",
                message=result.message,
                payload=result.to_dict(),
            )
        return result

    def _cancel_open_orders(
        self,
        *,
        execute: bool,
        confirmation: str | None,
        action: SyncAction,
        include_algo: bool = True,
    ) -> RecoveryExecutionResult:
        broker = BinanceFuturesDemoBroker(self.cfg, require_private=bool(execute))
        try:
            response = broker.cancel_open_orders(execute=execute, confirmation=confirmation, include_algo=include_algo)
            status = "executed" if execute else "preview"
            message = "Cancel-open-orders recovery step completed in preview mode." if not execute else "Cancel-open-orders recovery step was submitted to Demo/Testnet."
            return RecoveryExecutionResult(
                timestamp_utc=self._utc_now(),
                action=action.action,
                severity=action.severity,
                reason=action.reason,
                status=status,
                dry_run=not execute,
                execute_requested=bool(execute),
                result=response,
                message=message,
            )
        except Exception as exc:  # noqa: BLE001 - preserve exception in audit log
            return RecoveryExecutionResult(
                timestamp_utc=self._utc_now(),
                action=action.action,
                severity=action.severity,
                reason=action.reason,
                status="failed",
                dry_run=not execute,
                execute_requested=bool(execute),
                result={"error": str(exc)},
                message=f"Cancel-open-orders recovery step failed: {exc}",
            )

    def execute_action(
        self,
        action: SyncAction | dict[str, Any],
        *,
        execute: bool = False,
        confirmation: str | None = None,
    ) -> RecoveryExecutionResult:
        if isinstance(action, dict):
            action_obj = SyncAction(
                action=str(action.get("action")),
                severity=str(action.get("severity", "warning")),
                reason=str(action.get("reason", "")),
                dry_run_safe=bool(action.get("dry_run_safe", True)),
            )
        else:
            action_obj = action

        auto_enabled = bool(self.recovery_cfg.get("enabled", False))
        allowed_execute_actions = set(self.recovery_cfg.get("allow_execute_actions", []) or [])
        can_execute = execute and auto_enabled and action_obj.action in allowed_execute_actions

        # Position mismatches are never auto-fixed with market orders in this framework.
        if action_obj.action in {"halt_and_manual_reconcile", "halt_and_resync_position_quantity"}:
            return self._record_result(
                RecoveryExecutionResult(
                    timestamp_utc=self._utc_now(),
                    action=action_obj.action,
                    severity=action_obj.severity,
                    reason=action_obj.reason,
                    status="blocked",
                    dry_run=True,
                    execute_requested=bool(execute),
                    result={"manual_intervention_required": True},
                    message="Position mismatch requires manual reconciliation; no automatic market order was sent.",
                )
            )

        if action_obj.action in {
            "cancel_remaining_protective_orders",
            "verify_flat_then_cancel_open_reduce_only_orders",
        }:
            if execute and not can_execute:
                return self._record_result(
                    RecoveryExecutionResult(
                        timestamp_utc=self._utc_now(),
                        action=action_obj.action,
                        severity=action_obj.severity,
                        reason=action_obj.reason,
                        status="blocked",
                        dry_run=True,
                        execute_requested=True,
                        result={
                            "auto_recovery_enabled": auto_enabled,
                            "allowed_execute_actions": sorted(allowed_execute_actions),
                        },
                        message="Execution was requested but this recovery action is not enabled in config.",
                    )
                )
            return self._record_result(
                self._cancel_open_orders(
                    execute=can_execute,
                    confirmation=confirmation,
                    action=action_obj,
                    include_algo=True,
                )
            )

        if action_obj.action == "replace_native_protective_orders":
            return self._record_result(
                RecoveryExecutionResult(
                    timestamp_utc=self._utc_now(),
                    action=action_obj.action,
                    severity=action_obj.severity,
                    reason=action_obj.reason,
                    status="manual_required",
                    dry_run=True,
                    execute_requested=bool(execute),
                    result={"next_step": "Run demo_protective_orders_preview.py after verifying entry price, quantity, and side."},
                    message="Native protective orders are missing; replacement is intentionally manual in V0.9.",
                )
            )

        return self._record_result(
            RecoveryExecutionResult(
                timestamp_utc=self._utc_now(),
                action=action_obj.action,
                severity=action_obj.severity,
                reason=action_obj.reason,
                status="record_only",
                dry_run=True,
                execute_requested=bool(execute),
                result={},
                message="No executable recovery operation is associated with this action.",
            )
        )

    def execute_report_actions(
        self,
        report: SyncReport,
        *,
        execute: bool = False,
        confirmation: str | None = None,
    ) -> list[RecoveryExecutionResult]:
        results: list[RecoveryExecutionResult] = []
        for raw_action in report.actions:
            results.append(self.execute_action(raw_action, execute=execute, confirmation=confirmation))
        return results
