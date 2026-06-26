from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from crypto_quant.exchange.pretrade import PreTradeCheckReport, build_pretrade_check
from crypto_quant.exchange.state_snapshot import ExchangeExecutionState, build_offline_execution_state, fetch_demo_execution_state
from crypto_quant.exchange.target_execution import execute_target_position_plan
from crypto_quant.exchange.target_position import TargetPositionPlan, build_target_position_plan


@dataclass(frozen=True)
class SyncedTargetPreview:
    plan: TargetPositionPlan
    pretrade: PreTradeCheckReport
    state: ExchangeExecutionState
    latest_signal: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "latest_signal": self.latest_signal,
            "state": self.state.to_dict(),
            "pretrade": self.pretrade.to_dict(),
            "plan": self.plan.to_dict(),
        }


@dataclass(frozen=True)
class SyncedTargetExecutionResult:
    status: str
    dry_run: bool
    pretrade: dict[str, Any]
    plan: dict[str, Any]
    execution_result: dict[str, Any] | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_synced_target_preview(
    cfg: dict[str, Any],
    *,
    latest_signal: dict[str, Any],
    state: ExchangeExecutionState,
    reference_price: float,
    include_protective_plan: bool | None = None,
    apply_demo_order_cap: bool | None = None,
) -> SyncedTargetPreview:
    target_exposure = float(latest_signal.get("target_exposure", 0.0))
    plan = build_target_position_plan(
        cfg,
        reference_price=float(reference_price),
        equity_usdt=float(state.equity_usdt),
        target_exposure=target_exposure,
        current_qty=float(state.current_qty),
        timestamp=str(latest_signal.get("timestamp", state.timestamp_utc)),
        leverage=float(cfg.get("ensemble_demo_execution", {}).get("leverage", cfg.get("trading", {}).get("leverage", 3.0))),
        reason="synced_exchange_ensemble_target_exposure",
        apply_demo_order_cap=apply_demo_order_cap,
        include_protective_plan=include_protective_plan,
    )
    pretrade = build_pretrade_check(cfg, state=state, plan=plan)
    return SyncedTargetPreview(plan=plan, pretrade=pretrade, state=state, latest_signal=latest_signal)


def build_offline_synced_state(
    cfg: dict[str, Any],
    *,
    exchange_qty: float = 0.0,
    equity_usdt: float | None = None,
    open_order_count: int = 0,
    mark_price: float | None = None,
) -> ExchangeExecutionState:
    return build_offline_execution_state(
        cfg,
        exchange_qty=exchange_qty,
        equity_usdt=equity_usdt,
        open_order_count=open_order_count,
        mark_price=mark_price,
    )


def fetch_synced_state(cfg: dict[str, Any]) -> ExchangeExecutionState:
    return fetch_demo_execution_state(cfg)


def execute_synced_target_preview(
    cfg: dict[str, Any],
    preview: SyncedTargetPreview,
    *,
    execute: bool = False,
    confirmation: str | None = None,
    allow_warning: bool = False,
) -> SyncedTargetExecutionResult:
    if not preview.pretrade.allow_execution:
        return SyncedTargetExecutionResult(
            status="blocked_by_pretrade_check",
            dry_run=True,
            pretrade=preview.pretrade.to_dict(),
            plan=preview.plan.to_dict(),
            execution_result=None,
            message="Execution blocked because pre-trade synchronization check failed.",
        )
    if preview.pretrade.status == "warning" and execute and not allow_warning:
        return SyncedTargetExecutionResult(
            status="blocked_by_pretrade_warning",
            dry_run=True,
            pretrade=preview.pretrade.to_dict(),
            plan=preview.plan.to_dict(),
            execution_result=None,
            message="Pre-trade check returned warnings. Re-run with --allow-warning to execute on Demo/Testnet.",
        )
    result = execute_target_position_plan(
        cfg,
        preview.plan,
        execute=execute,
        confirmation=confirmation,
    )
    return SyncedTargetExecutionResult(
        status=result.status,
        dry_run=result.dry_run,
        pretrade=preview.pretrade.to_dict(),
        plan=preview.plan.to_dict(),
        execution_result=result.to_dict(),
        message=result.message,
    )
