from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import numpy as np
import pandas as pd

from crypto_quant.backtest.engine import LeveragedBacktester
from crypto_quant.backtest.metrics import performance_summary, period_performance
from crypto_quant.backtest.trades import extract_long_trades, trade_summary
from crypto_quant.features.feature_builder import build_features
from crypto_quant.features.labels import add_future_return_label
from crypto_quant.models.walk_forward import WalkForwardConfig, walk_forward_predict

from crypto_quant.paper.account import PaperAccount
from crypto_quant.paper.broker import PaperBroker
from crypto_quant.paper.database import PaperStore
from crypto_quant.research.scans import ml_threshold_leverage_scan
from crypto_quant.strategy.ml_strategy import probability_signal
from crypto_quant.strategy.rule_strategy import ma_trend_signal


def make_sample_ohlcv(periods: int = 220) -> pd.DataFrame:
    idx = pd.date_range("2022-01-01", periods=periods, freq="4h", tz="UTC")
    x = np.arange(periods)
    close = 40000 + 400 * np.sin(x / 12) + x * 0.8
    close = pd.Series(close, index=idx).astype(float)
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": 100 + 10 * np.sin(x / 7),
    })


def make_ml_dataset(periods: int = 180) -> pd.DataFrame:
    idx = pd.date_range("2021-01-01", periods=periods, freq="4h", tz="UTC")
    x = np.arange(periods)
    y = (np.sin(x / 6) > 0).astype(int)
    return pd.DataFrame({
        "close": 40000 + x,
        "ma_24": 40000 + x - 10,
        "ma_120": 40000 + x - 20,
        "f1": np.sin(x / 6),
        "f2": np.cos(x / 5),
        "f3": np.sin(x / 9),
        "label_up": y,
    }, index=idx)


def test_smoke() -> None:
    df = make_sample_ohlcv()
    feat = build_features(df, windows=[3, 6, 12, 24, 48, 120])
    dataset = add_future_return_label(feat, horizon_bars=6)

    signal_df = ma_trend_signal(dataset)
    result = LeveragedBacktester().run(signal_df)
    assert not result.empty
    assert "equity" in result.columns

    summary = performance_summary(result)
    assert "max_drawdown" in summary
    annual = period_performance(result, freq="YE")
    assert not annual.empty

    trades = extract_long_trades(result)
    tsummary = trade_summary(trades)
    assert "num_trades" in tsummary

    ml_dataset = make_ml_dataset()
    wf_data, folds = walk_forward_predict(
        ml_dataset,
        ["f1", "f2", "f3"],
        WalkForwardConfig(train_window_days=20, test_window_days=7, min_train_bars=50),
    )
    assert not wf_data.empty
    assert "prob_up_wf" in wf_data.columns
    assert not folds.empty

    wf_signal = probability_signal(wf_data, prob_col="prob_up_wf", buy_threshold=0.55, exit_threshold=0.48)
    wf_result = LeveragedBacktester(leverage=3).run(wf_signal)
    assert not wf_result.empty

    scan = ml_threshold_leverage_scan(
        wf_data,
        leverages=[3, 5],
        buy_thresholds=[0.55, 0.60],
        exit_thresholds=[0.48],
        timeframe="4h",
        initial_equity=1000,
        max_margin_fraction=0.30,
        max_notional_fraction=3.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
        max_drawdown_stop_fraction=0.20,
        prob_col="prob_up_wf",
    )
    assert not scan.empty
    assert {"leverage", "buy_threshold", "sharpe"}.issubset(scan.columns)


    # Stateful paper-trading storage and broker smoke test.
    db_path = ROOT / "data" / "database" / "smoke_paper.sqlite"
    if db_path.exists():
        db_path.unlink()
    store = PaperStore(db_path)
    account = store.reset(initial_equity=1000.0, leverage=3.0)
    broker = PaperBroker(account, fee_rate=0.0005, slippage_rate=0.0005)
    buy = broker.buy_with_margin_fraction(
        price=40000.0,
        margin_fraction=0.30,
        leverage=3.0,
        timestamp="2022-01-01 00:00:00+00:00",
        reason="smoke_entry",
        metadata={"prob_up": 0.61, "signal": 1},
    )
    assert buy["status"] == "filled"
    store.save_account(account)
    store.append_order(buy, equity_after=account.equity)
    store.append_decision({
        "timestamp": "2022-01-01 00:00:00+00:00",
        "price": 40000.0,
        "prob_up": 0.61,
        "signal": 1,
        "action": "buy",
        "reason": "smoke_entry",
        "risk_allowed": True,
        "leverage": 3.0,
        "margin_fraction": 0.30,
        "notional_fraction": 0.90,
        "equity": account.equity,
        "position_qty": account.position_qty,
    })
    store.append_equity("2022-01-01 00:00:00+00:00", 40000.0, account)
    loaded = store.load_account()
    assert loaded.in_position
    sell = broker.close_long(
        price=40500.0,
        timestamp="2022-01-01 04:00:00+00:00",
        reason="smoke_exit",
        metadata={"prob_up": 0.45, "signal": 0},
    )
    assert sell["status"] == "filled"
    store.save_account(account)
    store.append_order(sell, equity_after=account.equity)
    store.append_equity("2022-01-01 04:00:00+00:00", 40500.0, account)
    orders = store.read_table("orders")
    equity_curve = store.read_table("equity_curve")
    assert len(orders) == 2
    assert len(equity_curve) == 2


    # Exchange adapter safety smoke tests; no network calls are made here.
    from crypto_quant.exchange.order_intent import OrderIntent
    from crypto_quant.exchange.position_sizing import btc_quantity_from_notional
    from crypto_quant.exchange.safety import ExecutionSafetyConfig, ExecutionSafetyGuard

    qty = btc_quantity_from_notional(
        equity_usdt=1000.0,
        reference_price=50000.0,
        margin_fraction=0.30,
        leverage=3.0,
        max_notional_fraction=3.0,
        max_order_notional_usdt=50.0,
    )
    assert 0 < qty <= 50.0 / 50000.0 + 1e-12

    intent = OrderIntent(
        symbol="BTC/USDT:USDT",
        side="buy",
        order_type="market",
        quantity=qty,
        leverage=3.0,
        reason="smoke_demo_preview",
    )
    assert intent.to_dict()["symbol"] == "BTC/USDT:USDT"

    guard = ExecutionSafetyGuard(ExecutionSafetyConfig(max_order_notional_usdt=50.0, max_leverage=10.0))
    guard.validate_environment()
    guard.validate_order_limits(quantity=qty, reference_price=50000.0, leverage=3.0)


    # V0.5 execution bridge smoke test: strategy decision -> OrderIntent -> local PaperBroker.
    from crypto_quant.execution.bridge import ExecutionBridge
    from crypto_quant.execution.decision import StrategyDecision

    bridge_account = PaperAccount(equity=1000.0, cash=1000.0, leverage=3.0)
    bridge_cfg = {
        "symbol": {"ccxt_symbol": "BTC/USDT:USDT"},
        "trading": {
            "fee_rate": 0.0005,
            "slippage_rate": 0.0005,
            "max_notional_fraction": 3.0,
        },
        "execution": {"mode": "local_paper", "order_type": "market"},
        "broker": {
            "environment": "testnet",
            "safety": {
                "default_dry_run": True,
                "allow_live_trading": False,
                "require_confirmation_phrase": "I_UNDERSTAND_TESTNET_ORDER",
                "max_order_notional_usdt": 50.0,
                "max_leverage": 10.0,
            },
        },
    }
    decision = StrategyDecision(
        timestamp="2022-01-02 00:00:00+00:00",
        symbol="BTC/USDT:USDT",
        price=40000.0,
        action="buy",
        reason="smoke_bridge_entry",
        signal=1,
        prob_up=0.62,
        equity=1000.0,
        position_qty=0.0,
        leverage=3.0,
        margin_fraction=0.30,
        notional_fraction=0.90,
        risk_allowed=True,
    )
    bridge = ExecutionBridge(bridge_cfg, bridge_account, mode="local_paper")
    intent = bridge.build_intent(decision)
    assert intent is not None and intent.side == "buy"
    exec_result = bridge.execute(decision)
    assert exec_result.status == "filled"
    assert bridge_account.in_position


    # V0.6 protective orders, circuit breaker, and pending-order lifecycle smoke tests.
    from crypto_quant.risk.protective_orders import ProtectiveOrderManager
    from crypto_quant.risk.circuit_breaker import CircuitBreaker
    from crypto_quant.execution.order_lifecycle import OrderLifecycleSimulator, PendingOrder

    risk_cfg = {
        "data": {"timeframe": "4h"},
        "features": {"atr_window": 14},
        "trading": {
            "initial_equity": 1000.0,
            "slippage_rate": 0.0005,
            "maintenance_margin_rate": 0.005,
        },
        "risk": {
            "stop_loss_atr_multiple": 2.5,
            "take_profit_atr_multiple": 4.0,
            "enable_trailing_stop": True,
            "trailing_stop_atr_multiple": 3.0,
            "pause_after_consecutive_losses": 2,
            "pause_bars_after_consecutive_losses": 3,
            "max_daily_loss_fraction": 0.05,
            "conservative_same_bar_exit": "stop_first",
        },
    }
    po = ProtectiveOrderManager(risk_cfg)
    acct = PaperAccount(equity=1000.0, cash=1000.0, position_qty=0.1, entry_price=100.0, leverage=3.0)
    levels = po.attach_initial_levels(acct, entry_reference_price=100.0, atr=2.0)
    assert levels.stop_loss_price == 95.0
    bar = pd.Series({"high": 101.0, "low": 94.5, "close": 96.0, "atr_14": 2.0})
    protective_exit = po.evaluate_long_exit(acct, bar)
    assert protective_exit.triggered and "stop" in protective_exit.reason

    cb = CircuitBreaker(risk_cfg)
    acct2 = PaperAccount(equity=1000.0, cash=1000.0, leverage=3.0, consecutive_losses=1)
    cb.update_after_closed_trade(acct2, pnl=-10.0, timestamp="2022-01-03 00:00:00+00:00")
    assert acct2.risk_pause_until is not None
    assert not cb.can_open_position(acct2, "2022-01-03 04:00:00+00:00").allowed

    pending = PendingOrder(
        order_id="smoke_pending",
        created_timestamp="2022-01-04 00:00:00+00:00",
        side="buy",
        order_type="limit",
        price=100.0,
        qty=1.0,
        reason="smoke_limit",
    )
    lifecycle = OrderLifecycleSimulator(max_order_age_bars=1, slippage_rate=0.0005)
    updated = lifecycle.update(pending, timestamp="2022-01-04 04:00:00+00:00", high=101.0, low=99.5)
    assert updated.status == "filled"


    # V0.7 native exchange protective-order intent and recovery check smoke tests.
    from crypto_quant.exchange.protective_orders import build_long_protective_order_plan
    from crypto_quant.exchange.recovery import ExchangePositionSnapshot, compare_local_and_exchange_state

    plan = build_long_protective_order_plan(
        symbol="BTC/USDT:USDT",
        quantity=0.001,
        entry_price=50000.0,
        stop_loss_price=49000.0,
        take_profit_price=52000.0,
        trailing_activation_price=50500.0,
        trailing_callback_rate=1.0,
        leverage=3.0,
        enable_trailing_stop=True,
    )
    assert len(plan.intents) == 3
    assert plan.stop_loss_intent is not None and plan.stop_loss_intent.order_type == "stop_market"
    assert plan.take_profit_intent is not None and plan.take_profit_intent.reduce_only
    assert plan.trailing_stop_intent is not None and plan.trailing_stop_intent.callback_rate == 1.0

    local = PaperAccount(equity=1000.0, cash=1000.0, position_qty=0.001, entry_price=50000.0, leverage=3.0)
    ex_pos = ExchangePositionSnapshot(
        symbol="BTC/USDT:USDT",
        contracts=0.001,
        side="long",
        entry_price=50000.0,
        notional=50.0,
        raw={},
    )
    recovery = compare_local_and_exchange_state(
        local_account=local,
        exchange_position=ex_pos,
        open_orders=[{"type": "STOP_MARKET", "reduceOnly": True}],
    )
    assert recovery.status == "ok"

    recovery_missing = compare_local_and_exchange_state(
        local_account=local,
        exchange_position=ex_pos,
        open_orders=[],
    )
    assert recovery_missing.status == "warning"
    assert recovery_missing.missing_native_protection is True


    # V0.8/V0.9 exchange event ingestion, recovery executor, alerts, and supervisor smoke tests.
    from crypto_quant.exchange.events import parse_binance_user_data_event, sample_order_trade_update_fill
    from crypto_quant.exchange.sync import ExchangeStateSynchronizer
    from crypto_quant.exchange.recovery_executor import RecoveryActionExecutor
    from crypto_quant.alerts import AlertRouter
    from crypto_quant.daemon import DemoSupervisor

    normalized = parse_binance_user_data_event(sample_order_trade_update_fill())
    assert normalized and normalized[0].is_reduce_only_exit_fill

    v9_db = ROOT / "data" / "database" / "smoke_v9.sqlite"
    if v9_db.exists():
        v9_db.unlink()
    v9_store = PaperStore(v9_db)
    v9_store.reset(initial_equity=1000.0, leverage=3.0)
    v9_cfg = {
        "symbol": {"ccxt_symbol": "BTC/USDT:USDT"},
        "trading": {"initial_equity": 1000.0, "leverage": 3.0},
        "native_protection": {"min_protective_order_count": 1},
        "alerts": {"console": False, "jsonl_path": None, "webhook": {"enabled": False}},
        "auto_recovery": {"enabled": False, "allow_execute_actions": ["cancel_remaining_protective_orders"]},
        "broker": {
            "environment": "testnet",
            "safety": {
                "default_dry_run": True,
                "allow_live_trading": False,
                "require_confirmation_phrase": "I_UNDERSTAND_TESTNET_ORDER",
                "max_order_notional_usdt": 50.0,
                "max_leverage": 10.0,
            },
        },
    }
    sync = ExchangeStateSynchronizer(v9_cfg, v9_store)
    report = sync.build_offline_report(exchange_qty=0.001, open_order_count=0)
    assert report.status == "warning"
    router = AlertRouter.from_config(v9_cfg, project_root=ROOT)
    executor = RecoveryActionExecutor(v9_cfg, v9_store, alert_router=router)
    recovery_results = executor.execute_report_actions(report, execute=False)
    assert recovery_results
    assert any(r.status in {"blocked", "manual_required", "preview", "record_only"} for r in recovery_results)
    supervisor = DemoSupervisor(v9_cfg, v9_store, alert_router=router)
    sup = supervisor.run_once(iteration=1, offline_exchange_qty=0.001, offline_open_order_count=0)
    assert sup.status == "warning"
    assert not v9_store.read_table("recovery_actions").empty
    assert not v9_store.read_table("daemon_heartbeats").empty


    # V1.0 deployment health, status snapshot, and guarded service smoke tests.
    from crypto_quant.deploy.health import DeploymentHealthChecker
    from crypto_quant.deploy.status import RuntimeStatusBuilder
    from crypto_quant.deploy.service import DemoServiceRunner

    v10_db = ROOT / "data" / "database" / "smoke_v10.sqlite"
    if v10_db.exists():
        v10_db.unlink()
    v10_cfg = {
        "paper": {"database_path": str(v10_db)},
        "trading": {"initial_equity": 1000.0, "leverage": 3.0},
        "symbol": {"ccxt_symbol": "BTC/USDT:USDT"},
        "model": {"model_path": "models/missing.joblib", "feature_list_path": "models/missing_features.txt"},
        "data": {"dataset_path": "data/processed/missing.parquet"},
        "execution": {"mode": "local_paper", "execute_demo_orders": False},
        "broker": {
            "environment": "testnet",
            "api_key_env": "BINANCE_TESTNET_API_KEY",
            "secret_env": "BINANCE_TESTNET_API_SECRET",
            "safety": {
                "default_dry_run": True,
                "allow_live_trading": False,
                "require_confirmation_phrase": "I_UNDERSTAND_TESTNET_ORDER",
                "max_order_notional_usdt": 50.0,
                "max_leverage": 10.0,
            },
        },
        "native_protection": {"min_protective_order_count": 1},
        "alerts": {"console": False, "jsonl_path": None, "webhook": {"enabled": False}},
        "auto_recovery": {"enabled": False, "allow_execute_actions": ["cancel_remaining_protective_orders"]},
        "deployment": {
            "health_report_path": str(ROOT / "reports" / "deployment" / "smoke_health.json"),
            "status_report_path": str(ROOT / "reports" / "deployment" / "smoke_status.json"),
        },
        "service": {"mode": "demo_supervisor", "max_iterations_default": 1, "interval_seconds": 0},
        "logging": {"log_dir": str(ROOT / "logs"), "level": "INFO", "max_bytes": 1000000, "backup_count": 1},
    }
    health = DeploymentHealthChecker(v10_cfg, root=ROOT).run()
    assert health.overall_status in {"pass", "warn"}
    status = RuntimeStatusBuilder(v10_cfg, root=ROOT).build()
    assert "account" in status.to_dict()
    runner = DemoServiceRunner(v10_cfg)
    service_summary = runner.run(max_iterations=1, interval_seconds=0, offline_exchange_qty=0.0, offline_open_order_count=0)
    assert service_summary.iterations == 1


    # V1.1 model/strategy diagnostics smoke tests.
    from crypto_quant.research.model_diagnostics import (
        classifier_metric_summary,
        threshold_diagnostics,
        probability_bucket_table,
    )
    from crypto_quant.research.strategy_diagnostics import (
        strategy_diagnostic_tables,
        leverage_risk_table,
        drawdown_event_table,
    )
    from crypto_quant.reporting.html_report import build_research_html_report

    y_true = pd.Series([0, 1, 1, 0, 1], index=pd.date_range("2022-01-01", periods=5, freq="4h", tz="UTC"))
    prob = np.array([0.2, 0.7, 0.62, 0.4, 0.8])
    md = classifier_metric_summary(y_true, prob)
    assert "brier_score" in md
    th = threshold_diagnostics(y_true, prob, thresholds=[0.5, 0.6])
    assert len(th) == 2
    buckets = probability_bucket_table(y_true, prob, bins=5)
    assert not buckets.empty

    diag_tables = strategy_diagnostic_tables(wf_result, timeframe="4h")
    assert "drawdown_events" in diag_tables
    lev_table = leverage_risk_table(wf_result, timeframe="4h", leverages=[1, 3])
    assert {"leverage", "max_drawdown"}.issubset(lev_table.columns)
    _ = drawdown_event_table(wf_result)
    html_path = ROOT / "reports" / "research_report" / "smoke_report.html"
    build_research_html_report(
        html_path,
        title="Smoke Research Report",
        summary={"samples": 5},
        tables={"thresholds": th},
        images=[],
        notes=["smoke"],
    )
    assert html_path.exists()


    # V1.2 strategy/model library smoke tests.
    from crypto_quant.strategy.library import available_strategies, build_strategy_signal
    from crypto_quant.models.registry import available_models, make_model_by_name
    from crypto_quant.research.strategy_library import backtest_strategy_library
    from crypto_quant.research.model_library import evaluate_model_library
    from crypto_quant.research.model_strategy_matrix import run_model_strategy_matrix

    assert "ma_trend" in available_strategies()
    lib_signal = build_strategy_signal(dataset, "donchian_breakout")
    assert "signal" in lib_signal.columns

    assert "extra_trees" in available_models()
    model = make_model_by_name("logistic_l2")
    assert hasattr(model, "fit")

    v12_dir = ROOT / "reports" / "smoke_v12"
    strat_summary = backtest_strategy_library(
        dataset=dataset,
        strategy_names=["ma_trend", "rsi_mean_reversion"],
        output_dir=v12_dir / "strategy_library",
        timeframe="4h",
        initial_equity=1000.0,
        leverage=3.0,
        max_margin_fraction=0.30,
        max_notional_fraction=3.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
        max_drawdown_stop_fraction=0.20,
    )
    assert len(strat_summary) == 2

    model_summary = evaluate_model_library(
        dataset=ml_dataset,
        feature_columns=["f1", "f2", "f3"],
        model_names=["extra_trees", "logistic_l2"],
        train_end="2021-01-20",
        valid_end="2021-02-10",
        output_dir=v12_dir / "model_library",
        thresholds=[0.5, 0.6],
        calibration_bins=5,
    )
    assert {"model", "split", "roc_auc"}.issubset(model_summary.columns)

    matrix_summary = run_model_strategy_matrix(
        dataset=ml_dataset,
        feature_columns=["f1", "f2", "f3"],
        model_names=["extra_trees", "logistic_l2"],
        walk_forward_config=WalkForwardConfig(train_window_days=20, test_window_days=7, min_train_bars=50),
        output_dir=v12_dir / "model_strategy_matrix",
        timeframe="4h",
        initial_equity=1000.0,
        leverage=3.0,
        max_margin_fraction=0.30,
        max_notional_fraction=3.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
        max_drawdown_stop_fraction=0.20,
        buy_threshold=0.55,
        exit_threshold=0.48,
        trend_filter=True,
        max_holding_bars=12,
    )
    assert len(matrix_summary) == 2


    # V1.3 robustness, parameter search, segment/regime diagnostics smoke tests.
    from crypto_quant.research.robustness import (
        default_strategy_param_grid,
        expand_grid,
        strategy_parameter_search,
        evaluate_top_candidate_robustness,
        chronological_segment_performance,
        regime_performance_table,
        ml_walk_forward_threshold_grid,
        overfit_risk_score,
        robust_rank_score,
    )

    grid = default_strategy_param_grid("rsi_mean_reversion")
    assert expand_grid(grid)
    seg = chronological_segment_performance(wf_result, timeframe="4h", n_segments=3)
    assert not seg.empty
    regime = regime_performance_table(wf_result, wf_signal, timeframe="4h")
    assert isinstance(regime, pd.DataFrame)

    v13_dir = ROOT / "reports" / "smoke_v13"
    search_summary = strategy_parameter_search(
        dataset=dataset,
        strategy_names=["rsi_mean_reversion"],
        output_dir=v13_dir / "parameter_search",
        timeframe="4h",
        initial_equity=1000.0,
        leverage=3.0,
        max_margin_fraction=0.30,
        max_notional_fraction=3.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
        max_drawdown_stop_fraction=0.20,
        n_segments=3,
        max_candidates_per_strategy=2,
    )
    assert not search_summary.empty
    assert {"robust_rank_score", "overfit_risk_score"}.issubset(search_summary.columns)

    top = search_summary.iloc[0]
    tables = evaluate_top_candidate_robustness(
        dataset=dataset,
        candidate=top,
        output_dir=v13_dir / "top_candidate",
        timeframe="4h",
        initial_equity=1000.0,
        leverage=3.0,
        leverages=[1, 3],
        max_margin_fraction=0.30,
        max_notional_fraction=3.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
        fee_multipliers=[1, 2],
        slippage_multipliers=[1, 2],
        max_drawdown_stop_fraction=0.20,
        n_segments=3,
    )
    assert "cost_slippage_stress" in tables and not tables["cost_slippage_stress"].empty
    assert "leverage_boundary" in tables and not tables["leverage_boundary"].empty

    ml_grid = ml_walk_forward_threshold_grid(
        pred_df=wf_data,
        output_dir=v13_dir / "ml_threshold_grid",
        timeframe="4h",
        initial_equity=1000.0,
        leverage=3.0,
        max_margin_fraction=0.30,
        max_notional_fraction=3.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
        max_drawdown_stop_fraction=0.20,
        prob_col="prob_up_wf",
        buy_thresholds=[0.55, 0.60],
        exit_thresholds=[0.48],
        trend_filter_values=[True],
        max_holding_values=[6],
        n_segments=3,
    )
    assert not ml_grid.empty
    assert overfit_risk_score(ml_grid.iloc[0]) >= 0
    assert isinstance(robust_rank_score(ml_grid.iloc[0]), float)


    # V1.4 ensemble and dynamic-positioning smoke tests.
    from crypto_quant.research.ensemble import (
        select_top_candidates,
        build_ensemble_signal_table,
        build_dynamic_exposure,
        run_ensemble_backtest,
        dynamic_position_grid,
        apply_strategy_failure_filter,
    )
    from crypto_quant.backtest.dynamic_engine import DynamicExposureBacktester

    cand_table = search_summary.copy()
    candidates = select_top_candidates(cand_table, top_n=2, min_trades=0, max_overfit_risk=100.0)
    assert len(candidates) >= 1
    ens_signal, ens_meta = build_ensemble_signal_table(dataset, candidates, vote_threshold=0.40)
    assert {"ensemble_score", "signal"}.issubset(ens_signal.columns)
    exposure_df = build_dynamic_exposure(
        ens_signal,
        timeframe="4h",
        base_leverage=3.0,
        max_exposure=3.0,
        vol_target_annual=0.45,
        vol_window_bars=24,
    )
    assert "target_exposure" in exposure_df.columns
    dyn_result = DynamicExposureBacktester(initial_equity=1000.0, max_notional_fraction=3.0).run(exposure_df)
    assert "equity" in dyn_result.columns
    _, failure_status = apply_strategy_failure_filter(exposure_df, ens_meta, lookback_bars=30)
    assert "disabled_by_failure_filter" in failure_status.columns

    v14_dir = ROOT / "reports" / "smoke_v14"
    ens_outputs = run_ensemble_backtest(
        dataset=dataset,
        candidates=candidates,
        output_dir=v14_dir / "ensemble",
        timeframe="4h",
        initial_equity=1000.0,
        base_leverage=3.0,
        max_exposure=3.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
        max_drawdown_stop_fraction=0.20,
        vote_threshold=0.40,
        vol_target_annual=0.45,
        vol_window_bars=24,
    )
    assert "summary" in ens_outputs and "max_drawdown" in ens_outputs["summary"]
    dyn_grid = dynamic_position_grid(
        signal_table=ens_signal,
        output_dir=v14_dir / "dynamic_positioning",
        timeframe="4h",
        initial_equity=1000.0,
        base_leverages=[2.0, 3.0],
        max_exposures=[2.0, 3.0],
        vol_targets=[0.30, 0.45],
        vol_windows=[24],
        fee_rate=0.0005,
        slippage_rate=0.0005,
        max_drawdown_stop_fraction=0.20,
    )
    assert not dyn_grid.empty and "risk_adjusted_rank" in dyn_grid.columns


    # V1.6 target-position execution preview smoke tests. No network calls.
    from crypto_quant.exchange.target_position import build_target_position_plan
    from crypto_quant.exchange.target_execution import execute_target_position_plan

    v16_cfg = {
        "symbol": {"ccxt_symbol": "BTC/USDT:USDT"},
        "trading": {"initial_equity": 1000.0, "leverage": 3.0, "max_notional_fraction": 3.0},
        "execution": {"order_type": "market"},
        "ensemble": {"max_exposure": 3.0},
        "ensemble_paper": {"min_rebalance_notional": 25.0},
        "ensemble_demo_execution": {
            "leverage": 3.0,
            "max_exposure": 3.0,
            "min_rebalance_notional": 25.0,
            "order_type": "market",
            "apply_demo_order_cap": True,
            "attach_native_protection": True,
            "client_order_prefix": "smokev16",
        },
        "native_protection": {
            "enabled": True,
            "working_type": "MARK_PRICE",
            "position_side": "BOTH",
            "enable_stop_loss": True,
            "enable_take_profit": True,
            "enable_trailing_stop": False,
            "fallback_stop_loss_pct": 0.02,
            "fallback_take_profit_pct": 0.04,
        },
        "broker": {
            "environment": "testnet",
            "safety": {
                "default_dry_run": True,
                "allow_live_trading": False,
                "require_confirmation_phrase": "I_UNDERSTAND_TESTNET_ORDER",
                "max_order_notional_usdt": 50.0,
                "max_leverage": 10.0,
            },
        },
    }
    target_plan = build_target_position_plan(
        v16_cfg,
        reference_price=50000.0,
        equity_usdt=1000.0,
        target_exposure=1.0,
        current_qty=0.0,
        timestamp="2022-01-05 00:00:00+00:00",
        include_protective_plan=True,
    )
    assert target_plan.action == "increase"
    assert target_plan.order_intent is not None and target_plan.order_intent.side == "buy"
    assert target_plan.order_intent.quantity <= 50.0 / 50000.0 + 1e-12
    assert target_plan.protective_plan is not None
    dry_result = execute_target_position_plan(v16_cfg, target_plan, execute=False)
    assert dry_result.status == "preview"
    assert dry_result.dry_run is True

    reduce_plan = build_target_position_plan(
        v16_cfg,
        reference_price=50000.0,
        equity_usdt=1000.0,
        target_exposure=0.0,
        current_qty=0.002,
        timestamp="2022-01-05 04:00:00+00:00",
        include_protective_plan=False,
    )
    assert reduce_plan.action == "close"
    assert reduce_plan.order_intent is not None and reduce_plan.order_intent.reduce_only


    # V1.7 exchange-synchronized target execution pre-trade gate smoke tests. No network calls.
    from crypto_quant.exchange.synced_target_execution import (
        build_offline_synced_state,
        build_synced_target_preview,
        execute_synced_target_preview,
    )
    from crypto_quant.exchange.state_snapshot import classify_open_orders

    orders_cls = classify_open_orders([
        {"type": "STOP_MARKET", "reduceOnly": True},
        {"type": "LIMIT", "reduceOnly": False},
    ])
    assert orders_cls.protective_count == 1
    assert orders_cls.non_protective_count == 1

    latest_signal = {
        "timestamp": "2022-01-05 08:00:00+00:00",
        "close": 50000.0,
        "target_exposure": 1.0,
        "ensemble_score": 0.8,
        "signal": 1,
    }
    synced_state = build_offline_synced_state(
        v16_cfg,
        exchange_qty=0.0,
        equity_usdt=1000.0,
        open_order_count=0,
        mark_price=50000.0,
    )
    synced_preview = build_synced_target_preview(
        v16_cfg,
        latest_signal=latest_signal,
        state=synced_state,
        reference_price=50000.0,
        include_protective_plan=True,
    )
    assert synced_preview.pretrade.status in {"pass", "warning"}
    assert synced_preview.plan.current_qty == 0.0
    synced_result = execute_synced_target_preview(v16_cfg, synced_preview, execute=False)
    assert synced_result.status in {"preview", "no_order_required"}

    mismatch_state = build_offline_synced_state(
        v16_cfg,
        exchange_qty=0.002,
        equity_usdt=1000.0,
        open_order_count=0,
        mark_price=50000.0,
    )
    mismatch_preview = build_synced_target_preview(
        v16_cfg,
        latest_signal=latest_signal,
        state=mismatch_state,
        reference_price=50000.0,
        include_protective_plan=False,
    )
    # Open position without native protection should be blocked for increase/hold plans.
    assert mismatch_preview.pretrade.status == "blocked"
    blocked = execute_synced_target_preview(v16_cfg, mismatch_preview, execute=True, confirmation="I_UNDERSTAND_TESTNET_ORDER")
    assert blocked.status == "blocked_by_pretrade_check"


    # V1.8 exchange error classification, retry, idempotency and resilient execution smoke tests. No network calls.
    from types import SimpleNamespace
    from crypto_quant.exchange.errors import classify_exchange_exception
    from crypto_quant.exchange.retry import RetryPolicy, RetryExecutor
    from crypto_quant.exchange.idempotency import IdempotencyStore, with_idempotent_client_order_id
    from crypto_quant.exchange.resilient_executor import ResilientExchangeExecutor

    err = classify_exchange_exception(RuntimeError("temporary network timeout while submitting order"))
    assert err.retryable and err.category in {"network_error", "request_timeout"}

    attempts_counter = {"n": 0}
    def flaky_success():
        attempts_counter["n"] += 1
        if attempts_counter["n"] < 3:
            raise RuntimeError("temporary network timeout while submitting order")
        return {"ok": True}
    retry_res = RetryExecutor(RetryPolicy(max_attempts=3, sleep_enabled=False, jitter_seconds=0.0)).run(flaky_success)
    assert retry_res.ok and len(retry_res.attempts) == 3

    v18_db = ROOT / "data" / "database" / "smoke_v18.sqlite"
    if v18_db.exists():
        v18_db.unlink()
    idem_store = IdempotencyStore(v18_db)
    base_intent = OrderIntent(
        symbol="BTC/USDT:USDT",
        side="buy",
        order_type="market",
        quantity=0.001,
        leverage=3.0,
        reason="smoke_v18",
    )
    idem_intent, idem_key, fingerprint = with_idempotent_client_order_id(base_intent, prefix="smokev18", time_bucket="2022-01-06T00")
    assert idem_intent.client_order_id is not None
    reserved, existing = idem_store.reserve(
        key=idem_key,
        client_order_id=str(idem_intent.client_order_id),
        fingerprint=fingerprint,
        intent=idem_intent.to_dict(),
    )
    assert reserved and existing is not None
    idem_store.update_status(idem_key, status="submitted", result={"ok": True})
    reserved_again, existing_again = idem_store.reserve(
        key=idem_key,
        client_order_id=str(idem_intent.client_order_id),
        fingerprint=fingerprint,
        intent=idem_intent.to_dict(),
    )
    assert reserved_again is False and existing_again is not None

    class FakeDemoBroker:
        def __init__(self):
            self.calls = 0
        def place_order(self, intent, *, reference_price, execute=False, confirmation=None):
            self.calls += 1
            return SimpleNamespace(
                status="submitted",
                dry_run=False,
                intent=intent.to_dict(),
                response={"orderId": "fake_order", "clientOrderId": intent.client_order_id},
                message="fake submitted",
            )

    fake_broker = FakeDemoBroker()
    v18_cfg = dict(v16_cfg)
    v18_cfg["exchange_resilience"] = {
        "client_order_prefix": "smokev18",
        "idempotency_db_path": str(v18_db),
        "retry": {"max_attempts": 2, "sleep_enabled": False, "jitter_seconds": 0.0},
    }
    executor18 = ResilientExchangeExecutor(v18_cfg, db_path=v18_db, broker_factory=lambda require_private: fake_broker)
    res1 = executor18.submit_intent(base_intent, reference_price=50000.0, execute=True, confirmation="I_UNDERSTAND_TESTNET_ORDER", time_bucket="2022-01-06T04")
    assert res1.status == "submitted"
    res2 = executor18.submit_intent(base_intent, reference_price=50000.0, execute=True, confirmation="I_UNDERSTAND_TESTNET_ORDER", time_bucket="2022-01-06T04")
    assert res2.status == "duplicate_blocked"
    assert len(IdempotencyStore(v18_db).read_attempts()) >= 1


    # V1.9 order lifecycle, partial-fill protection recalculation and cancel-failure smoke tests. No network calls.
    from crypto_quant.exchange.events import parse_binance_user_data_event
    from crypto_quant.exchange.order_state_machine import ExchangeOrderStateMachine
    from crypto_quant.exchange.partial_fill import build_protection_recalc_plan
    from crypto_quant.exchange.cancel_recovery import build_cancel_failure_plan

    partial_raw = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1760000000000,
        "o": {
            "s": "BTCUSDT",
            "c": "smokev19_entry",
            "S": "BUY",
            "o": "MARKET",
            "q": "0.010",
            "x": "TRADE",
            "X": "PARTIALLY_FILLED",
            "i": 1900019,
            "l": "0.004",
            "z": "0.004",
            "L": "50000",
            "ap": "50000",
            "R": False,
            "ps": "BOTH",
        },
    }
    event = parse_binance_user_data_event(partial_raw)[0]
    update = ExchangeOrderStateMachine().apply_event(event)
    assert update.lifecycle.state == "partially_filled"
    assert abs(update.lifecycle.remaining_quantity - 0.006) < 1e-12

    recalc = build_protection_recalc_plan(
        symbol="BTC/USDT:USDT",
        position_qty=0.004,
        entry_price=50000.0,
        open_orders=[],
        cfg={
            "symbol": {"ccxt_symbol": "BTC/USDT:USDT"},
            "native_protection": {"fallback_stop_loss_pct": 0.02, "fallback_take_profit_pct": 0.04},
            "trading": {"leverage": 3.0},
            "exchange_resilience": {"client_order_prefix": "smokev19"},
        },
        attach_new_intents=True,
    )
    assert recalc.status == "under_protected"
    assert recalc.new_protective_intents

    cancel_plan = build_cancel_failure_plan(
        None,
        order_id="1900019",
        client_order_id="smokev19_sl",
        exchange_response={"error_category": "network_error", "retryable": True, "message": "simulated"},
    )
    assert cancel_plan.status == "retryable_cancel_failure"
    assert any(a["action"] == "block_new_entries_until_cancel_resolved" for a in cancel_plan.actions)


    # V2.0 live safety gate, kill switch, hard circuit and shadow-live preview smoke tests. No network calls.
    from crypto_quant.live import (
        HardCircuitBreaker,
        KillSwitch,
        LiveSafetyGate,
        PreLiveValidationBuilder,
        ShadowLiveReadOnlyClient,
    )

    v20_cfg = dict(v16_cfg)
    v20_cfg["paper"] = {"database_path": str(v9_db)}
    v20_cfg["broker"] = {
        "environment": "testnet",
        "safety": {
            "default_dry_run": True,
            "allow_live_trading": False,
            "require_confirmation_phrase": "I_UNDERSTAND_TESTNET_ORDER",
            "max_order_notional_usdt": 50.0,
            "max_leverage": 10.0,
        },
    }
    v20_cfg["live_trading"] = {
        "master_enable": False,
        "kill_switch_path": str(ROOT / "data" / "database" / "smoke_kill_switch.json"),
        "max_live_leverage": 3.0,
        "max_daily_loss_fraction": 0.02,
        "max_total_drawdown_fraction": 0.10,
        "allow_live_without_prelive_report": True,
    }
    v20_cfg["shadow_live"] = {
        "api_key_env": "BINANCE_LIVE_READONLY_API_KEY",
        "secret_env": "BINANCE_LIVE_READONLY_API_SECRET",
    }
    kill_path = ROOT / "data" / "database" / "smoke_kill_switch.json"
    if kill_path.exists():
        kill_path.unlink()
    ks = KillSwitch(kill_path)
    assert not ks.is_triggered()
    triggered = ks.trigger("smoke")
    assert triggered["enabled"] is True and ks.is_triggered()
    ks.clear("smoke_clear")
    assert not ks.is_triggered()

    live_gate = LiveSafetyGate(v20_cfg, root=ROOT).evaluate()
    assert live_gate.status == "blocked"
    assert any(item.name == "live_master_enable" for item in live_gate.blockers)

    eq_curve = pd.DataFrame({
        "timestamp": pd.date_range("2022-01-01", periods=3, freq="4h", tz="UTC"),
        "equity": [1000.0, 990.0, 970.0],
    })
    hard = HardCircuitBreaker(max_daily_loss_fraction=0.02, max_total_drawdown_fraction=0.10).evaluate_equity_curve(eq_curve)
    assert hard.status == "blocked"

    shadow = ShadowLiveReadOnlyClient(v20_cfg).offline_snapshot()
    assert shadow["dry_run"] is True and shadow["source"] == "offline_shadow_live_preview"
    prelive = PreLiveValidationBuilder(v20_cfg, root=ROOT).build()
    assert "checks" in prelive


if __name__ == "__main__":
    test_smoke()
    print("smoke_test passed")
