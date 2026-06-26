from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_quant.config import resolve_path
from crypto_quant.data.storage import load_parquet
from crypto_quant.paper.account import PaperAccount
from crypto_quant.paper.database import PaperStore
from crypto_quant.paper.dynamic_broker import DynamicPaperBroker
from crypto_quant.research.ensemble import (
    build_dynamic_exposure,
    build_ensemble_signal_table,
    load_candidate_table,
    select_top_candidates,
)
from crypto_quant.risk.protective_orders import ProtectiveOrderManager


@dataclass
class EnsemblePaperStepResult:
    timestamp: str
    price: float
    ensemble_score: float
    signal: int
    target_exposure: float
    current_exposure_before: float
    current_exposure_after: float
    action: str
    reason: str
    equity: float
    cash: float
    position_qty: float
    order: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_path_from_config(cfg: dict[str, Any]) -> Path:
    ens_cfg = cfg.get("ensemble", {})
    rob_cfg = cfg.get("robustness", {})
    default = resolve_path(rob_cfg.get("parameter_search_path", "reports/robustness/parameter_search")) / "strategy_parameter_search_summary.csv"
    return resolve_path(ens_cfg.get("candidate_table_path", str(default)))


def _select_candidates_from_config(cfg: dict[str, Any]):
    ens_cfg = cfg.get("ensemble", {})
    table = load_candidate_table(_candidate_path_from_config(cfg))
    return select_top_candidates(
        table,
        top_n=int(ens_cfg.get("top_n", 5)),
        min_trades=int(ens_cfg.get("min_trades", 5)),
        max_overfit_risk=float(ens_cfg.get("max_overfit_risk", 80.0)),
    )


def build_ensemble_exposure_dataset(cfg: dict[str, Any], dataset: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build full historical ensemble signal/exposure table from V1.3 candidate results."""
    ens_cfg = cfg.get("ensemble", {})
    if dataset is None:
        dataset = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    candidates = _select_candidates_from_config(cfg)
    signal_table, candidate_meta = build_ensemble_signal_table(
        dataset,
        candidates,
        vote_threshold=float(ens_cfg.get("vote_threshold", 0.50)),
    )
    exposure_table = build_dynamic_exposure(
        signal_table,
        timeframe=str(cfg["data"].get("timeframe", "4h")),
        base_leverage=float(ens_cfg.get("base_leverage", cfg["trading"].get("leverage", 3.0))),
        max_exposure=float(ens_cfg.get("max_exposure", cfg["trading"].get("max_notional_fraction", 3.0))),
        vol_target_annual=float(ens_cfg.get("vol_target_annual", 0.45)),
        vol_window_bars=int(ens_cfg.get("vol_window_bars", 42)),
        regime_adjustment=bool(ens_cfg.get("regime_adjustment", True)),
    )
    return exposure_table, candidate_meta


def latest_ensemble_preview(
    cfg: dict[str, Any],
    db_path: str | Path | None = None,
) -> tuple[dict[str, Any], PaperAccount, pd.DataFrame]:
    paper_cfg = cfg.get("paper", {})
    if db_path is None:
        db_path = resolve_path(paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))
    store = PaperStore(db_path)
    account = store.load_account(
        initial_equity=float(cfg["trading"]["initial_equity"]),
        leverage=float(cfg["trading"].get("leverage", 3.0)),
    )
    exposure_table, candidate_meta = build_ensemble_exposure_dataset(cfg)
    if exposure_table.empty:
        raise ValueError("Ensemble exposure table is empty. Run data/feature scripts and run_strategy_parameter_search.py first.")
    row = exposure_table.iloc[-1]
    timestamp = str(exposure_table.index[-1])
    price = float(row["close"])
    account.mark_to_market(price)
    broker = DynamicPaperBroker(
        account,
        fee_rate=float(cfg["trading"].get("fee_rate", 0.0005)),
        slippage_rate=float(cfg["trading"].get("slippage_rate", 0.0005)),
        min_rebalance_notional=float(cfg.get("ensemble_paper", {}).get("min_rebalance_notional", 25.0)),
        max_exposure=float(cfg.get("ensemble_paper", {}).get("max_exposure", cfg.get("ensemble", {}).get("max_exposure", 3.0))),
    )
    plan = broker.plan_rebalance(
        price=price,
        target_exposure=float(row.get("target_exposure", 0.0)),
        timestamp=timestamp,
        reason="ensemble_dynamic_target",
    )
    preview = {
        **plan.to_dict(),
        "ensemble_score": float(row.get("ensemble_score", 0.0)),
        "signal": int(row.get("signal", 0)),
        "candidate_active_count": float(row.get("candidate_active_count", 0.0)),
        "candidate_active_fraction": float(row.get("candidate_active_fraction", 0.0)),
        "candidate_count": int(len(candidate_meta)),
    }
    return preview, account, candidate_meta


def _protective_levels_for_row(cfg: dict[str, Any], row: pd.Series, price: float) -> dict[str, Any] | None:
    ep_cfg = cfg.get("ensemble_paper", {})
    if not bool(ep_cfg.get("attach_local_protective_levels", True)):
        return None
    manager = ProtectiveOrderManager(cfg)
    atr = manager.atr_from_row(row)
    return manager.initial_levels(price, atr).to_dict()


def run_ensemble_paper_step(
    cfg: dict[str, Any],
    db_path: str | Path | None = None,
    new_candle_only: bool | None = None,
) -> EnsemblePaperStepResult:
    paper_cfg = cfg.get("paper", {})
    ep_cfg = cfg.get("ensemble_paper", {})
    if db_path is None:
        db_path = resolve_path(paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))
    if new_candle_only is None:
        new_candle_only = bool(paper_cfg.get("new_candle_only", True))

    store = PaperStore(db_path)
    account = store.load_account(
        initial_equity=float(cfg["trading"]["initial_equity"]),
        leverage=float(cfg["trading"].get("leverage", 3.0)),
    )
    exposure_table, candidate_meta = build_ensemble_exposure_dataset(cfg)
    if exposure_table.empty:
        raise ValueError("Ensemble exposure table is empty. Run data/feature scripts and run_strategy_parameter_search.py first.")
    row = exposure_table.iloc[-1]
    timestamp = str(exposure_table.index[-1])
    price = float(row["close"])

    if new_candle_only and store.has_target_exposure_decision_for_timestamp(timestamp):
        account.mark_to_market(price)
        result = EnsemblePaperStepResult(
            timestamp=timestamp,
            price=price,
            ensemble_score=float(row.get("ensemble_score", 0.0)),
            signal=int(row.get("signal", 0)),
            target_exposure=float(row.get("target_exposure", 0.0)),
            current_exposure_before=account.position_notional(price) / max(account.equity, 1e-12),
            current_exposure_after=account.position_notional(price) / max(account.equity, 1e-12),
            action="skipped",
            reason="latest_candle_already_processed_by_ensemble_paper",
            equity=account.equity,
            cash=account.cash,
            position_qty=account.position_qty,
            order=None,
        )
        return result

    if account.in_position:
        account.bars_held += 1
    account.mark_to_market(price)
    current_exposure_before = account.position_notional(price) / max(account.equity, 1e-12)

    broker = DynamicPaperBroker(
        account,
        fee_rate=float(cfg["trading"].get("fee_rate", 0.0005)),
        slippage_rate=float(cfg["trading"].get("slippage_rate", 0.0005)),
        min_rebalance_notional=float(ep_cfg.get("min_rebalance_notional", 25.0)),
        max_exposure=float(ep_cfg.get("max_exposure", cfg.get("ensemble", {}).get("max_exposure", 3.0))),
    )
    target_exposure = float(row.get("target_exposure", 0.0))
    execution_price = price
    rebalance_reason = "ensemble_dynamic_target"
    protective_exit_info: dict[str, Any] | None = None
    if account.in_position and bool(ep_cfg.get("respect_local_protective_exits", True)):
        exit_check = ProtectiveOrderManager(cfg).evaluate_long_exit(account, row)
        if exit_check.triggered:
            target_exposure = 0.0
            execution_price = float(exit_check.execution_price or price)
            rebalance_reason = f"ensemble_protective_exit:{exit_check.reason}"
            protective_exit_info = exit_check.metadata or {}
            protective_exit_info.update({"trigger_price": exit_check.trigger_price, "execution_price": execution_price})
    metadata = {
        "ensemble_score": float(row.get("ensemble_score", 0.0)),
        "candidate_active_count": float(row.get("candidate_active_count", 0.0)),
        "candidate_active_fraction": float(row.get("candidate_active_fraction", 0.0)),
        "signal": int(row.get("signal", 0)),
        "candidate_count": int(len(candidate_meta)),
        "protective_exit": protective_exit_info,
    }
    protective = _protective_levels_for_row(cfg, row, price) if not account.in_position and target_exposure > 0 else None
    plan, order = broker.rebalance_to_exposure(
        price=execution_price,
        target_exposure=target_exposure,
        timestamp=timestamp,
        reason=rebalance_reason,
        metadata=metadata,
        protective_levels=protective,
    )
    account.last_update_timestamp = timestamp
    account.mark_to_market(price)
    current_exposure_after = account.position_notional(price) / max(account.equity, 1e-12)
    # Store effective leverage approximation for liquidation-warning display.
    account.leverage = max(1.0, current_exposure_after) if account.in_position else float(cfg["trading"].get("leverage", 3.0))
    store.save_account(account)
    if order is not None and order.get("status") == "filled":
        store.append_order(order, equity_after=account.equity)

    decision_row = {
        "timestamp": timestamp,
        "price": price,
        "ensemble_score": metadata["ensemble_score"],
        "signal": metadata["signal"],
        "target_exposure": plan.target_exposure,
        "target_notional": plan.target_notional,
        "current_exposure_before": current_exposure_before,
        "current_exposure_after": current_exposure_after,
        "current_notional_before": plan.current_notional,
        "delta_notional": plan.delta_notional,
        "action": plan.action,
        "reason": plan.reason,
        "equity": account.equity,
        "cash": account.cash,
        "position_qty": account.position_qty,
        "entry_price": account.entry_price,
        "candidate_active_count": metadata["candidate_active_count"],
        "candidate_active_fraction": metadata["candidate_active_fraction"],
        "candidate_count": metadata["candidate_count"],
        "order_json": order,
    }
    store.append_target_exposure_decision(decision_row)
    store.append_equity(
        timestamp=timestamp,
        price=price,
        account=account,
        maintenance_margin_rate=float(cfg["trading"].get("maintenance_margin_rate", 0.005)),
    )

    return EnsemblePaperStepResult(
        timestamp=timestamp,
        price=price,
        ensemble_score=metadata["ensemble_score"],
        signal=metadata["signal"],
        target_exposure=plan.target_exposure,
        current_exposure_before=current_exposure_before,
        current_exposure_after=current_exposure_after,
        action=plan.action,
        reason=plan.reason,
        equity=account.equity,
        cash=account.cash,
        position_qty=account.position_qty,
        order=order,
    )


def replay_ensemble_paper_dataset(
    cfg: dict[str, Any],
    bars: int = 200,
    reset: bool = False,
    db_path: str | Path | None = None,
) -> pd.DataFrame:
    paper_cfg = cfg.get("paper", {})
    ep_cfg = cfg.get("ensemble_paper", {})
    if db_path is None:
        db_path = resolve_path(paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))
    store = PaperStore(db_path)
    if reset:
        store.reset(float(cfg["trading"]["initial_equity"]), leverage=float(cfg["trading"].get("leverage", 3.0)))
    exposure_table, candidate_meta = build_ensemble_exposure_dataset(cfg)
    if bars > 0:
        exposure_table = exposure_table.tail(int(bars))
    rows: list[dict[str, Any]] = []
    account = store.load_account(float(cfg["trading"]["initial_equity"]), leverage=float(cfg["trading"].get("leverage", 3.0)))
    for ts, row in exposure_table.iterrows():
        timestamp = str(ts)
        price = float(row["close"])
        if account.in_position:
            account.bars_held += 1
        account.mark_to_market(price)
        before = account.position_notional(price) / max(account.equity, 1e-12)
        broker = DynamicPaperBroker(
            account,
            fee_rate=float(cfg["trading"].get("fee_rate", 0.0005)),
            slippage_rate=float(cfg["trading"].get("slippage_rate", 0.0005)),
            min_rebalance_notional=float(ep_cfg.get("min_rebalance_notional", 25.0)),
            max_exposure=float(ep_cfg.get("max_exposure", cfg.get("ensemble", {}).get("max_exposure", 3.0))),
        )
        target_exposure = float(row.get("target_exposure", 0.0))
        execution_price = price
        rebalance_reason = "ensemble_replay_dynamic_target"
        protective_exit_info: dict[str, Any] | None = None
        if account.in_position and bool(ep_cfg.get("respect_local_protective_exits", True)):
            exit_check = ProtectiveOrderManager(cfg).evaluate_long_exit(account, row)
            if exit_check.triggered:
                target_exposure = 0.0
                execution_price = float(exit_check.execution_price or price)
                rebalance_reason = f"ensemble_replay_protective_exit:{exit_check.reason}"
                protective_exit_info = exit_check.metadata or {}
                protective_exit_info.update({"trigger_price": exit_check.trigger_price, "execution_price": execution_price})
        metadata = {
            "ensemble_score": float(row.get("ensemble_score", 0.0)),
            "candidate_active_count": float(row.get("candidate_active_count", 0.0)),
            "candidate_active_fraction": float(row.get("candidate_active_fraction", 0.0)),
            "signal": int(row.get("signal", 0)),
            "candidate_count": int(len(candidate_meta)),
            "protective_exit": protective_exit_info,
        }
        protective = _protective_levels_for_row(cfg, row, price) if not account.in_position and target_exposure > 0 else None
        plan, order = broker.rebalance_to_exposure(
            price=execution_price,
            target_exposure=target_exposure,
            timestamp=timestamp,
            reason=rebalance_reason,
            metadata=metadata,
            protective_levels=protective,
        )
        account.last_update_timestamp = timestamp
        account.mark_to_market(price)
        after = account.position_notional(price) / max(account.equity, 1e-12)
        account.leverage = max(1.0, after) if account.in_position else float(cfg["trading"].get("leverage", 3.0))
        store.save_account(account)
        if order is not None and order.get("status") == "filled":
            store.append_order(order, equity_after=account.equity)
        record = {
            "timestamp": timestamp,
            "price": price,
            "ensemble_score": metadata["ensemble_score"],
            "signal": metadata["signal"],
            "target_exposure": plan.target_exposure,
            "target_notional": plan.target_notional,
            "current_exposure_before": before,
            "current_exposure_after": after,
            "current_notional_before": plan.current_notional,
            "delta_notional": plan.delta_notional,
            "action": plan.action,
            "reason": plan.reason,
            "equity": account.equity,
            "cash": account.cash,
            "position_qty": account.position_qty,
            "entry_price": account.entry_price,
            "candidate_active_count": metadata["candidate_active_count"],
            "candidate_active_fraction": metadata["candidate_active_fraction"],
            "candidate_count": metadata["candidate_count"],
            "order_json": order,
        }
        store.append_target_exposure_decision(record)
        store.append_equity(
            timestamp=timestamp,
            price=price,
            account=account,
            maintenance_margin_rate=float(cfg["trading"].get("maintenance_margin_rate", 0.005)),
        )
        rows.append(record)
    return pd.DataFrame(rows)
