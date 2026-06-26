from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_quant.config import resolve_path
from crypto_quant.data.ohlcv_downloader import update_ohlcv_file
from crypto_quant.data.storage import load_parquet, save_parquet
from crypto_quant.execution.bridge import ExecutionBridge, ExecutionBridgeResult
from crypto_quant.execution.decision import StrategyDecision
from crypto_quant.features.feature_builder import build_features
from crypto_quant.features.labels import add_future_return_label
from crypto_quant.models.predict import add_model_probability
from crypto_quant.paper.account import PaperAccount
from crypto_quant.paper.database import PaperStore
from crypto_quant.risk.circuit_breaker import CircuitBreaker
from crypto_quant.risk.protective_orders import ProtectiveOrderManager
from crypto_quant.risk.risk_manager import RiskDecision, RiskManager


@dataclass
class PaperStepResult:
    timestamp: str
    price: float
    prob_up: float | None
    signal: int
    action: str
    reason: str
    equity: float
    cash: float
    position_qty: float
    order: dict | None = None
    execution: dict | None = None


def refresh_dataset(cfg: dict[str, Any]) -> pd.DataFrame:
    """Update OHLCV data and rebuild feature/label dataset.

    This uses public market data only. It is optional in paper mode because many
    development runs should use already-downloaded local data.
    """
    raw = update_ohlcv_file(
        exchange_name=cfg["exchange"]["name"],
        market_type=cfg["exchange"]["market_type"],
        symbol=cfg["symbol"]["ccxt_symbol"],
        timeframe=cfg["data"]["timeframe"],
        since_iso=cfg["data"]["since"],
        output_path=resolve_path(cfg["data"]["raw_path"]),
    )
    feat = build_features(
        raw,
        windows=cfg["features"]["windows"],
        atr_window=cfg["features"]["atr_window"],
        rsi_window=cfg["features"]["rsi_window"],
        dropna=cfg["features"]["dropna"],
    )
    dataset = add_future_return_label(
        feat,
        horizon_bars=cfg["labels"]["horizon_bars"],
        positive_return_threshold=cfg["labels"]["positive_return_threshold"],
    ).dropna()
    save_parquet(feat, resolve_path(cfg["data"]["feature_path"]))
    save_parquet(dataset, resolve_path(cfg["data"]["dataset_path"]))
    return dataset


def load_signal_dataset(cfg: dict[str, Any], update_data: bool = False) -> pd.DataFrame:
    if update_data:
        df = refresh_dataset(cfg)
    else:
        df = load_parquet(resolve_path(cfg["data"]["dataset_path"]))
    return add_model_probability(
        df,
        model_path=resolve_path(cfg["model"]["model_path"]),
        feature_list_path=resolve_path(cfg["model"]["feature_list_path"]),
    )


def _trend_ok(row: pd.Series) -> bool:
    if {"ma_24", "ma_120", "close"}.issubset(row.index):
        return bool(row["close"] > row["ma_120"] and row["ma_24"] > row["ma_120"])
    return True


def _risk_manager_from_config(cfg: dict[str, Any]) -> RiskManager:
    return RiskManager(
        max_leverage=cfg["trading"]["max_leverage"],
        max_margin_fraction=cfg["trading"]["max_margin_fraction"],
        max_notional_fraction=cfg["trading"]["max_notional_fraction"],
        min_liquidation_buffer=cfg["trading"]["min_liquidation_buffer"],
    )


def _decision_for_current_bar(
    account: PaperAccount,
    row: pd.Series,
    cfg: dict[str, Any],
    risk_decision: RiskDecision,
    timestamp: str,
) -> tuple[str, str, int, dict[str, Any]]:
    """Return action, reason, desired signal and decision metadata for latest bar."""
    price = float(row["close"])
    prob = float(row["prob_up"])
    trend_ok = _trend_ok(row)
    buy_threshold = float(cfg["model"]["probability_buy_threshold"])
    exit_threshold = float(cfg["model"]["probability_exit_threshold"])
    protective = ProtectiveOrderManager(cfg)
    circuit = CircuitBreaker(cfg)

    base_meta: dict[str, Any] = {
        "trend_ok": trend_ok,
        "stop_loss_price": account.stop_loss_price,
        "take_profit_price": account.take_profit_price,
        "trailing_stop_price": account.trailing_stop_price,
        "highest_price_since_entry": account.highest_price_since_entry,
        "risk_pause_until": account.risk_pause_until,
        "consecutive_losses": account.consecutive_losses,
        "daily_realized_pnl": account.daily_realized_pnl,
    }

    if not account.in_position:
        circuit_decision = circuit.can_open_position(account, timestamp)
        base_meta["circuit_breaker"] = circuit_decision.reason
        if prob >= buy_threshold and trend_ok and risk_decision.allowed and circuit_decision.allowed:
            atr = protective.atr_from_row(row)
            levels = protective.initial_levels(price, atr).to_dict()
            base_meta.update({"atr": atr, "protective_levels": levels})
            return "buy", "entry_probability_and_trend", 1, base_meta
        if prob >= buy_threshold and trend_ok and not risk_decision.allowed:
            return "hold_cash", f"risk_blocked:{risk_decision.reason}", 0, base_meta
        if prob >= buy_threshold and trend_ok and not circuit_decision.allowed:
            return "hold_cash", f"circuit_breaker:{circuit_decision.reason}", 0, base_meta
        if not trend_ok:
            return "hold_cash", "trend_filter_not_satisfied", 0, base_meta
        return "hold_cash", "probability_below_buy_threshold", 0, base_meta

    # Position management: protective orders are evaluated against the candle high/low
    # before slower probability/trend exits. This is more realistic for leveraged paper
    # trading than close-only stops.
    protective_exit = protective.evaluate_long_exit(account, row)
    base_meta.update({
        "stop_loss_price": account.stop_loss_price,
        "take_profit_price": account.take_profit_price,
        "trailing_stop_price": account.trailing_stop_price,
        "highest_price_since_entry": account.highest_price_since_entry,
    })
    if protective_exit.triggered:
        base_meta.update({
            "trigger_price": protective_exit.trigger_price,
            "execution_price": protective_exit.execution_price,
            "protective_exit": protective_exit.metadata or {},
        })
        return "sell", protective_exit.reason, 0, base_meta

    if prob <= exit_threshold:
        return "sell", "probability_exit", 0, base_meta
    if not trend_ok:
        return "sell", "trend_exit", 0, base_meta
    if account.bars_held >= int(cfg["risk"]["max_holding_bars"]):
        return "sell", "max_holding_bars_exit", 0, base_meta
    return "hold_position", "position_still_valid", 1, base_meta

def build_latest_strategy_decision(
    cfg: dict[str, Any],
    account: PaperAccount,
    row: pd.Series,
    timestamp: str,
) -> StrategyDecision:
    """Create a broker-neutral StrategyDecision for the latest candle."""
    risk = _risk_manager_from_config(cfg)
    risk_decision = risk.validate_order(
        leverage=float(cfg["trading"]["leverage"]),
        margin_fraction=float(cfg["trading"]["max_margin_fraction"]),
    )
    action, reason, signal, metadata = _decision_for_current_bar(account, row, cfg, risk_decision, timestamp)
    prob = float(row["prob_up"])
    price = float(row["close"])
    return StrategyDecision(
        timestamp=timestamp,
        symbol=str(cfg["symbol"]["ccxt_symbol"]),
        price=price,
        action=action,
        reason=reason,
        signal=signal,
        prob_up=prob,
        equity=float(account.equity),
        position_qty=float(account.position_qty),
        leverage=float(risk_decision.leverage),
        margin_fraction=float(risk_decision.margin_fraction),
        notional_fraction=float(risk_decision.notional_fraction),
        risk_allowed=bool(risk_decision.allowed),
        metadata=metadata,
    )


def latest_decision_preview(
    cfg: dict[str, Any],
    db_path: str | Path | None = None,
    update_data: bool = False,
) -> tuple[StrategyDecision, dict | None, PaperAccount]:
    """Return latest strategy decision and optional OrderIntent dict without executing."""
    paper_cfg = cfg.get("paper", {})
    if db_path is None:
        db_path = resolve_path(paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))
    store = PaperStore(db_path)
    account = store.load_account(
        initial_equity=float(cfg["trading"]["initial_equity"]),
        leverage=float(cfg["trading"]["leverage"]),
    )
    df = load_signal_dataset(cfg, update_data=update_data)
    if df.empty:
        raise ValueError("Signal dataset is empty. Run scripts/download_ohlcv.py, build_features.py and train_model.py first.")
    latest = df.iloc[-1]
    timestamp = str(df.index[-1])
    price = float(latest["close"])
    account.mark_to_market(price)
    decision = build_latest_strategy_decision(cfg, account, latest, timestamp)
    bridge = ExecutionBridge(cfg, account, mode=str(cfg.get("execution", {}).get("mode", "local_paper")))
    intent = bridge.build_intent(decision)
    return decision, None if intent is None else intent.to_dict(), account


def run_paper_step(
    cfg: dict[str, Any],
    db_path: str | Path | None = None,
    update_data: bool = False,
    new_candle_only: bool | None = None,
    execution_mode: str | None = None,
    execute: bool = False,
    confirmation: str | None = None,
) -> PaperStepResult:
    paper_cfg = cfg.get("paper", {})
    if db_path is None:
        db_path = resolve_path(paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))
    if new_candle_only is None:
        new_candle_only = bool(paper_cfg.get("new_candle_only", True))

    store = PaperStore(db_path)
    account = store.load_account(
        initial_equity=float(cfg["trading"]["initial_equity"]),
        leverage=float(cfg["trading"]["leverage"]),
    )

    df = load_signal_dataset(cfg, update_data=update_data)
    if df.empty:
        raise ValueError("Signal dataset is empty. Run scripts/download_ohlcv.py, build_features.py and train_model.py first.")
    latest = df.iloc[-1]
    timestamp = str(df.index[-1])
    price = float(latest["close"])
    prob = float(latest["prob_up"])

    last_ts = store.last_processed_timestamp()
    if new_candle_only and last_ts is not None and timestamp <= str(last_ts):
        account.mark_to_market(price)
        return PaperStepResult(
            timestamp=timestamp,
            price=price,
            prob_up=prob,
            signal=1 if account.in_position else 0,
            action="skipped",
            reason="latest_candle_already_processed",
            equity=account.equity,
            cash=account.cash,
            position_qty=account.position_qty,
            order=None,
            execution=None,
        )

    if account.in_position:
        account.bars_held += 1
    account.mark_to_market(price)

    decision = build_latest_strategy_decision(cfg, account, latest, timestamp)
    bridge = ExecutionBridge(
        cfg,
        account,
        mode=execution_mode or str(cfg.get("execution", {}).get("mode", "local_paper")),
    )
    if decision.requires_order and store.has_execution_for_timestamp(timestamp, decision.action):
        exec_result = ExecutionBridgeResult(
            mode=bridge.mode,
            status="duplicate_order_blocked",
            dry_run=True,
            decision=decision.to_dict(),
            message="Duplicate order blocked for the same candle timestamp/action.",
        )
    else:
        exec_result = bridge.execute(
            decision,
            execute=execute,
            confirmation=confirmation,
        )

    order = exec_result.order if isinstance(exec_result.order, dict) else None
    if order is not None and exec_result.mode == "local_paper" and order.get("status") == "filled" and order.get("side") == "sell":
        CircuitBreaker(cfg).update_after_closed_trade(account, float(order.get("pnl") or 0.0), timestamp)
    account.last_update_timestamp = timestamp
    account.mark_to_market(price)
    store.save_account(account)
    if order is not None and exec_result.mode == "local_paper":
        store.append_order(order, equity_after=account.equity)
    store.append_execution_event(exec_result.to_dict())

    decision_row = {
        "timestamp": timestamp,
        "price": price,
        "prob_up": prob,
        "signal": decision.signal,
        "action": decision.action,
        "reason": decision.reason,
        "risk_allowed": decision.risk_allowed,
        "leverage": decision.leverage,
        "margin_fraction": decision.margin_fraction,
        "notional_fraction": decision.notional_fraction,
        "equity": account.equity,
        "position_qty": account.position_qty,
        "stop_loss_price": account.stop_loss_price,
        "take_profit_price": account.take_profit_price,
        "trailing_stop_price": account.trailing_stop_price,
        "risk_pause_until": account.risk_pause_until,
    }
    store.append_decision(decision_row)
    store.append_equity(
        timestamp=timestamp,
        price=price,
        account=account,
        maintenance_margin_rate=float(cfg["trading"].get("maintenance_margin_rate", 0.005)),
    )

    return PaperStepResult(
        timestamp=timestamp,
        price=price,
        prob_up=prob,
        signal=decision.signal,
        action=decision.action,
        reason=decision.reason,
        equity=account.equity,
        cash=account.cash,
        position_qty=account.position_qty,
        order=order,
        execution=exec_result.to_dict(),
    )
