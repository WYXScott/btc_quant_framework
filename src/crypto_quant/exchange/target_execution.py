from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from crypto_quant.config import resolve_path
from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.target_position import TargetPositionPlan, build_target_position_plan
from crypto_quant.paper.account import PaperAccount
from crypto_quant.paper.database import PaperStore
from crypto_quant.paper.ensemble_runner import build_ensemble_exposure_dataset


@dataclass(frozen=True)
class TargetExecutionPreview:
    plan: TargetPositionPlan
    source: str
    account_equity: float
    current_qty: float
    latest_signal: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "account_equity": self.account_equity,
            "current_qty": self.current_qty,
            "latest_signal": self.latest_signal,
            "plan": self.plan.to_dict(),
        }


@dataclass(frozen=True)
class TargetExecutionResult:
    mode: str
    status: str
    dry_run: bool
    plan: dict[str, Any]
    order_results: dict[str, Any] | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _paper_account_from_config(cfg: dict[str, Any], db_path: str | Path | None = None) -> PaperAccount:
    if db_path is None:
        db_path = resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
    store = PaperStore(db_path)
    return store.load_account(
        initial_equity=float(cfg.get("trading", {}).get("initial_equity", 1000.0)),
        leverage=float(cfg.get("trading", {}).get("leverage", 3.0)),
    )


def latest_ensemble_target_preview(
    cfg: dict[str, Any],
    *,
    current_qty: float | None = None,
    equity_usdt: float | None = None,
    source: str = "local_paper",
    db_path: str | Path | None = None,
    apply_demo_order_cap: bool | None = None,
    include_protective_plan: bool | None = None,
) -> TargetExecutionPreview:
    """Build the latest ensemble target-position preview without network calls.

    source controls how current/equity are inferred when explicit overrides are not
    supplied:
      - local_paper: read SQLite paper account;
      - manual: require/accept supplied current_qty and equity_usdt.
    """
    exposure_table, candidates = build_ensemble_exposure_dataset(cfg)
    if exposure_table.empty:
        raise ValueError("Ensemble exposure table is empty. Run build_features.py and run_strategy_parameter_search.py first.")
    row = exposure_table.iloc[-1]
    timestamp = str(exposure_table.index[-1])
    price = float(row["close"])

    account = None
    if source == "local_paper":
        account = _paper_account_from_config(cfg, db_path=db_path)
        account.mark_to_market(price)
        if current_qty is None:
            current_qty = float(account.position_qty if account.in_position else 0.0)
        if equity_usdt is None:
            equity_usdt = float(account.equity)
    elif source == "manual":
        if current_qty is None:
            current_qty = 0.0
        if equity_usdt is None:
            equity_usdt = float(cfg.get("trading", {}).get("initial_equity", 1000.0))
    else:
        raise ValueError(f"Unsupported preview source for offline builder: {source}")

    plan = build_target_position_plan(
        cfg,
        reference_price=price,
        equity_usdt=float(equity_usdt),
        target_exposure=float(row.get("target_exposure", 0.0)),
        current_qty=float(current_qty or 0.0),
        timestamp=timestamp,
        leverage=float(cfg.get("ensemble_demo_execution", {}).get("leverage", cfg.get("trading", {}).get("leverage", 3.0))),
        reason="latest_ensemble_target_exposure",
        apply_demo_order_cap=apply_demo_order_cap,
        include_protective_plan=include_protective_plan,
    )
    latest_signal = {
        "timestamp": timestamp,
        "close": price,
        "target_exposure": float(row.get("target_exposure", 0.0)),
        "ensemble_score": float(row.get("ensemble_score", 0.0)),
        "signal": int(row.get("signal", 0)),
        "candidate_active_count": float(row.get("candidate_active_count", 0.0)),
        "candidate_active_fraction": float(row.get("candidate_active_fraction", 0.0)),
        "candidate_count": int(len(candidates)),
    }
    return TargetExecutionPreview(
        plan=plan,
        source=source,
        account_equity=float(equity_usdt),
        current_qty=float(current_qty or 0.0),
        latest_signal=latest_signal,
    )


def execute_target_position_plan(
    cfg: dict[str, Any],
    plan: TargetPositionPlan,
    *,
    execute: bool = False,
    confirmation: str | None = None,
) -> TargetExecutionResult:
    """Preview or submit a target-position plan through Binance Futures Demo/Testnet."""
    intents = plan.intents
    if not intents:
        return TargetExecutionResult(
            mode="binance_futures_demo",
            status="no_order_required",
            dry_run=True,
            plan=plan.to_dict(),
            order_results=None,
            message=f"Target action={plan.action!r}; no exchange intent was generated.",
        )
    if not execute:
        # Fully offline dry-run: do not instantiate CCXT or require credentials.
        result = {
            "status": "preview",
            "dry_run": True,
            "symbol": plan.symbol,
            "num_orders": len(intents),
            "orders": [
                {
                    "status": "preview",
                    "dry_run": True,
                    "intent": intent.to_dict(),
                    "response": None,
                    "message": "Offline dry-run only. No exchange order was sent.",
                }
                for intent in intents
            ],
        }
        return TargetExecutionResult(
            mode="binance_futures_demo",
            status="preview",
            dry_run=True,
            plan=plan.to_dict(),
            order_results=result,
            message="Offline dry-run preview only. No exchange order was sent.",
        )

    broker = BinanceFuturesDemoBroker(cfg, require_private=True)
    result = broker.place_order_intents(
        intents,
        reference_price=float(plan.reference_price),
        execute=True,
        confirmation=confirmation,
    )
    return TargetExecutionResult(
        mode="binance_futures_demo",
        status=str(result.get("status")),
        dry_run=bool(result.get("dry_run", True)),
        plan=plan.to_dict(),
        order_results=result,
        message="Submitted to Demo/Testnet.",
    )
