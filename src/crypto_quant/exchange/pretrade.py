from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from crypto_quant.exchange.state_snapshot import ExchangeExecutionState
from crypto_quant.exchange.target_position import TargetPositionPlan


@dataclass(frozen=True)
class PreTradeIssue:
    severity: str  # info | warning | critical
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreTradeCheckReport:
    status: str  # pass | warning | blocked
    allow_execution: bool
    timestamp_utc: str
    source: str
    plan_action: str
    plan_target_exposure: float
    exchange_qty: float
    plan_current_qty: float
    open_order_count: int
    protective_order_count: int
    issues: list[PreTradeIssue]
    state: dict[str, Any]
    plan: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["issues"] = [i.to_dict() for i in self.issues]
        return d


def build_pretrade_check(
    cfg: dict[str, Any],
    *,
    state: ExchangeExecutionState,
    plan: TargetPositionPlan,
) -> PreTradeCheckReport:
    """Conservative execution gate for target-exposure Demo/Testnet orders.

    V1.7 uses this before any synchronized Demo/Testnet execution. Critical
    issues block execution; warnings are allowed only if the caller explicitly
    chooses to continue in the script layer.
    """
    sync_cfg = cfg.get("sync", {})
    v17_cfg = cfg.get("ensemble_demo_sync", {})
    native_cfg = cfg.get("native_protection", {})
    qty_tol = float(sync_cfg.get("qty_tolerance", v17_cfg.get("qty_tolerance", 1e-8)))
    min_protective = int(native_cfg.get("min_protective_order_count", 1))
    halt_on_unprotected = bool(v17_cfg.get("halt_if_position_unprotected", True))
    block_non_protective_orders = bool(v17_cfg.get("block_if_non_protective_open_orders", True))
    block_on_warnings = bool(v17_cfg.get("block_on_warnings", False))

    issues: list[PreTradeIssue] = []
    exchange_qty = float(state.current_qty)
    plan_qty = float(plan.current_qty)
    if abs(exchange_qty - plan_qty) > qty_tol:
        issues.append(PreTradeIssue(
            "critical",
            "plan_exchange_qty_mismatch",
            f"Target plan current_qty={plan_qty:.10f} does not match exchange snapshot qty={exchange_qty:.10f}.",
        ))

    if float(state.position.contracts or 0.0) < -qty_tol:
        issues.append(PreTradeIssue("critical", "short_position_detected", "Long-only system detected a short exchange position."))

    cls = state.order_classification
    if state.in_position and cls.protective_count < min_protective and plan.action not in {"close", "reduce"}:
        severity = "critical" if halt_on_unprotected else "warning"
        issues.append(PreTradeIssue(
            severity,
            "missing_native_protection",
            f"Exchange position is open but protective order count={cls.protective_count}, required>={min_protective}.",
        ))

    if cls.non_protective_count > 0 and block_non_protective_orders:
        issues.append(PreTradeIssue(
            "critical",
            "non_protective_open_orders_exist",
            f"Exchange has {cls.non_protective_count} non-protective open order(s); reconcile before target execution.",
        ))

    if plan.action in {"reduce", "close"} and exchange_qty <= qty_tol:
        issues.append(PreTradeIssue("critical", "reduce_without_exchange_position", "Plan wants to reduce/close but exchange snapshot is flat."))

    if plan.action == "increase" and plan.order_intent is None:
        issues.append(PreTradeIssue("critical", "increase_without_order_intent", "Plan wants to increase exposure but no order intent was generated."))

    for warning in plan.warnings:
        issues.append(PreTradeIssue("warning", "plan_warning", str(warning)))

    has_critical = any(i.severity == "critical" for i in issues)
    has_warning = any(i.severity == "warning" for i in issues)
    if has_critical or (block_on_warnings and has_warning):
        status = "blocked"
        allow = False
    elif has_warning:
        status = "warning"
        allow = True
    else:
        status = "pass"
        allow = True

    return PreTradeCheckReport(
        status=status,
        allow_execution=allow,
        timestamp_utc=state.timestamp_utc,
        source=state.source,
        plan_action=plan.action,
        plan_target_exposure=float(plan.target_exposure),
        exchange_qty=exchange_qty,
        plan_current_qty=plan_qty,
        open_order_count=cls.total_count,
        protective_order_count=cls.protective_count,
        issues=issues,
        state=state.to_dict(),
        plan=plan.to_dict(),
    )
