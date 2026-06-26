from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.resilient_executor import ResilientExchangeExecutor
from crypto_quant.exchange.synced_target_execution import (
    build_offline_synced_state,
    build_synced_target_preview,
    fetch_synced_state,
)
from crypto_quant.paper.database import PaperStore
from crypto_quant.paper.ensemble_runner import build_ensemble_exposure_dataset


def _latest_signal(cfg: dict) -> dict:
    exposure_table, candidates = build_ensemble_exposure_dataset(cfg)
    if exposure_table.empty:
        raise ValueError("Ensemble exposure table is empty. Run build_features.py and run_strategy_parameter_search.py first.")
    row = exposure_table.iloc[-1]
    timestamp = str(exposure_table.index[-1])
    return {
        "timestamp": timestamp,
        "close": float(row["close"]),
        "target_exposure": float(row.get("target_exposure", 0.0)),
        "ensemble_score": float(row.get("ensemble_score", 0.0)),
        "signal": int(row.get("signal", 0)),
        "candidate_active_count": float(row.get("candidate_active_count", 0.0)),
        "candidate_active_fraction": float(row.get("candidate_active_fraction", 0.0)),
        "candidate_count": int(len(candidates)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute latest synced ensemble target plan through resilient idempotent Demo layer.")
    parser.add_argument("--fetch-private", action="store_true")
    parser.add_argument("--exchange-qty", type=float, default=0.0)
    parser.add_argument("--equity", type=float, default=None)
    parser.add_argument("--open-order-count", type=int, default=0)
    parser.add_argument("--with-protection", action="store_true")
    parser.add_argument("--allow-warning", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default=None)
    args = parser.parse_args()

    cfg = load_config()
    latest = _latest_signal(cfg)
    state = fetch_synced_state(cfg) if args.fetch_private else build_offline_synced_state(
        cfg,
        exchange_qty=args.exchange_qty,
        equity_usdt=args.equity,
        open_order_count=args.open_order_count,
        mark_price=float(latest["close"]),
    )
    preview = build_synced_target_preview(
        cfg,
        latest_signal=latest,
        state=state,
        reference_price=float(latest["close"]),
        include_protective_plan=args.with_protection,
    )
    if bool(cfg.get("ensemble_demo_sync", {}).get("persist_pretrade_checks", True)):
        PaperStore(resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))).append_target_execution_precheck(preview.pretrade.to_dict())

    if not preview.pretrade.allow_execution:
        payload = {
            "status": "blocked_by_pretrade_check",
            "pretrade": preview.pretrade.to_dict(),
            "plan": preview.plan.to_dict(),
            "message": "No resilient execution attempted because pre-trade check blocked the plan.",
        }
    elif preview.pretrade.status == "warning" and args.execute and not args.allow_warning:
        payload = {
            "status": "blocked_by_pretrade_warning",
            "pretrade": preview.pretrade.to_dict(),
            "plan": preview.plan.to_dict(),
            "message": "Re-run with --allow-warning to execute on Demo/Testnet.",
        }
    else:
        executor = ResilientExchangeExecutor(cfg)
        execution = executor.submit_intents(
            preview.plan.intents,
            reference_price=float(preview.plan.reference_price),
            execute=args.execute,
            confirmation=args.confirm,
            time_bucket=str(latest["timestamp"]),
        )
        payload = {
            "status": execution["status"],
            "pretrade": preview.pretrade.to_dict(),
            "plan": preview.plan.to_dict(),
            "resilient_execution": execution,
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
