from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.exchange.synced_target_execution import build_offline_synced_state, build_synced_target_preview, fetch_synced_state
from crypto_quant.paper.ensemble_runner import build_ensemble_exposure_dataset
from crypto_quant.paper.database import PaperStore


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
    parser = argparse.ArgumentParser(description="Build latest ensemble target-position preview using synchronized exchange state.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch real Demo/Testnet private snapshot using testnet API keys.")
    parser.add_argument("--exchange-qty", type=float, default=0.0, help="Offline simulated exchange position qty.")
    parser.add_argument("--equity", type=float, default=None, help="Offline simulated USDT equity.")
    parser.add_argument("--open-order-count", type=int, default=0, help="Offline simulated protective open order count.")
    parser.add_argument("--no-demo-cap", action="store_true", help="Do not cap by broker.safety.max_order_notional_usdt in preview.")
    parser.add_argument("--with-protection", action="store_true", help="Also generate native SL/TP protection intents.")
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
        apply_demo_order_cap=not args.no_demo_cap,
    )
    if bool(cfg.get("ensemble_demo_sync", {}).get("persist_pretrade_checks", True)):
        db_path = resolve_path(cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite"))
        PaperStore(db_path).append_target_execution_precheck(preview.pretrade.to_dict())
    print(json.dumps(preview.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
