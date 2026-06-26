from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any

from crypto_quant.alerts import AlertMessage, AlertRouter
from crypto_quant.daemon import DemoSupervisor
from crypto_quant.deploy.health import DeploymentHealthChecker
from crypto_quant.deploy.status import RuntimeStatusBuilder
from crypto_quant.paper.database import PaperStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemoServiceRunSummary:
    started_at_utc: str
    finished_at_utc: str
    iterations: int
    mode: str
    health_status: str
    last_status: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DemoServiceRunner:
    """Guarded V1.0 demo/paper service runner.

    The service intentionally performs a pre-flight health check first. It can
    run finite loops for Windows Task Scheduler/manual validation, and can be
    configured for longer supervisor-only Demo monitoring once the user is ready.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        paper_cfg = cfg.get("paper", {}) or {}
        self.store = PaperStore(paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))
        self.alert_router = AlertRouter.from_config(cfg)
        self.supervisor = DemoSupervisor(cfg, self.store, alert_router=self.alert_router)
        self.status_builder = RuntimeStatusBuilder(cfg)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def run(
        self,
        *,
        max_iterations: int | None = None,
        interval_seconds: float | None = None,
        fetch_private: bool = False,
        execute_recovery: bool = False,
        confirmation: str | None = None,
        offline_exchange_qty: float | None = None,
        offline_open_order_count: int | None = None,
        skip_health_failures: bool = False,
    ) -> DemoServiceRunSummary:
        service_cfg = self.cfg.get("service", {}) or {}
        max_iterations = int(max_iterations if max_iterations is not None else service_cfg.get("max_iterations_default", 1))
        interval_seconds = float(interval_seconds if interval_seconds is not None else service_cfg.get("interval_seconds", 60))
        mode = str(service_cfg.get("mode", "demo_supervisor"))

        health = DeploymentHealthChecker(self.cfg).run()
        if health.has_failures and not skip_health_failures:
            alert = AlertMessage(
                level="error",
                title="V1.0 service preflight failed",
                message="Service start blocked because deployment health check has failures.",
                payload=health.to_dict(),
            )
            self.store.append_alert(self.alert_router.send(alert))
            raise RuntimeError("Deployment health check failed. Run scripts/deploy_check.py for details.")

        started = self._now()
        last_status: dict[str, Any] | None = None
        iterations_done = 0
        for i in range(1, max_iterations + 1):
            logger.info("Demo service iteration %s/%s", i, max_iterations)
            if mode == "demo_supervisor":
                self.supervisor.run_once(
                    iteration=i,
                    fetch_private=fetch_private,
                    execute_recovery=execute_recovery,
                    confirmation=confirmation,
                    offline_exchange_qty=offline_exchange_qty,
                    offline_open_order_count=offline_open_order_count,
                )
            else:
                raise ValueError(f"Unsupported service.mode: {mode}")
            snapshot = self.status_builder.build()
            self.status_builder.write_snapshot(snapshot)
            last_status = snapshot.to_dict()
            iterations_done += 1
            if i < max_iterations:
                time.sleep(interval_seconds)

        return DemoServiceRunSummary(
            started_at_utc=started,
            finished_at_utc=self._now(),
            iterations=iterations_done,
            mode=mode,
            health_status=health.overall_status,
            last_status=last_status,
        )
