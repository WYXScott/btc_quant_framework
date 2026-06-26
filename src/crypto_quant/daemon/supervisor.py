from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import time
from typing import Any

from crypto_quant.alerts import AlertMessage, AlertRouter
from crypto_quant.exchange.recovery_executor import RecoveryActionExecutor
from crypto_quant.exchange.sync import ExchangeStateSynchronizer
from crypto_quant.paper.database import PaperStore


@dataclass(frozen=True)
class SupervisorIterationResult:
    iteration: int
    timestamp_utc: str
    status: str
    report: dict[str, Any]
    recovery_results: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DemoSupervisor:
    """Polling supervisor for Demo/Testnet reconciliation and safe recovery.

    This is intentionally conservative and starts with a finite max_iterations in
    scripts. Use a process manager only after the demo flow has been validated.
    """

    def __init__(self, cfg: dict[str, Any], store: PaperStore, *, alert_router: AlertRouter | None = None):
        self.cfg = cfg
        self.store = store
        self.alert_router = alert_router or AlertRouter.from_config(cfg)
        self.sync = ExchangeStateSynchronizer(cfg, store)
        self.executor = RecoveryActionExecutor(cfg, store, alert_router=self.alert_router)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _heartbeat(self, *, iteration: int, status: str, details: dict[str, Any]) -> None:
        self.store.append_daemon_heartbeat(
            {
                "timestamp_utc": self._utc_now(),
                "component": "demo_supervisor",
                "status": status,
                "iteration": iteration,
                "details": details,
            }
        )

    def run_once(
        self,
        *,
        iteration: int = 1,
        fetch_private: bool = False,
        execute_recovery: bool = False,
        confirmation: str | None = None,
        offline_exchange_qty: float | None = None,
        offline_open_order_count: int | None = None,
    ) -> SupervisorIterationResult:
        try:
            if fetch_private:
                report = self.sync.fetch_and_record_snapshot()
            else:
                report = self.sync.build_offline_report(
                    exchange_qty=offline_exchange_qty,
                    open_order_count=offline_open_order_count,
                )

            recovery_results = self.executor.execute_report_actions(
                report,
                execute=execute_recovery,
                confirmation=confirmation,
            )
            status = "ok" if report.status in {"ok", "local_only"} else "warning"
            result = SupervisorIterationResult(
                iteration=iteration,
                timestamp_utc=self._utc_now(),
                status=status,
                report=report.to_dict(),
                recovery_results=[r.to_dict() for r in recovery_results],
            )
            self._heartbeat(iteration=iteration, status=status, details=result.to_dict())
            if status != "ok":
                delivery = self.alert_router.notify(
                    AlertMessage(
                        level="warning",
                        title="Demo supervisor reconciliation warning",
                        message="The supervisor detected a non-ok reconciliation status.",
                        payload=result.to_dict(),
                    )
                )
                self.store.append_alert(delivery)
            return result
        except Exception as exc:  # noqa: BLE001 - daemon must record failure
            error_payload = {"error": str(exc), "iteration": iteration}
            self._heartbeat(iteration=iteration, status="error", details=error_payload)
            delivery = self.alert_router.notify(
                AlertMessage(
                    level="critical",
                    title="Demo supervisor error",
                    message=str(exc),
                    payload=error_payload,
                )
            )
            self.store.append_alert(delivery)
            return SupervisorIterationResult(
                iteration=iteration,
                timestamp_utc=self._utc_now(),
                status="error",
                report={},
                recovery_results=[{"error": str(exc)}],
            )

    def run_loop(
        self,
        *,
        max_iterations: int,
        interval_seconds: int,
        fetch_private: bool = False,
        execute_recovery: bool = False,
        confirmation: str | None = None,
    ) -> list[SupervisorIterationResult]:
        results: list[SupervisorIterationResult] = []
        for i in range(1, int(max_iterations) + 1):
            result = self.run_once(
                iteration=i,
                fetch_private=fetch_private,
                execute_recovery=execute_recovery,
                confirmation=confirmation,
            )
            results.append(result)
            if i < int(max_iterations):
                time.sleep(int(interval_seconds))
        return results
