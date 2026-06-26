from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.alerts import AlertRouter
from crypto_quant.config import load_config, project_root, resolve_path
from crypto_quant.exchange.recovery_executor import RecoveryActionExecutor
from crypto_quant.exchange.sync import ExchangeStateSynchronizer
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one reconciliation pass and preview/execute safe recovery actions.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch private Demo/Testnet snapshots. Requires API keys.")
    parser.add_argument("--exchange-qty", type=float, default=None, help="Offline simulated exchange position quantity.")
    parser.add_argument("--open-order-count", type=int, default=None, help="Offline simulated open order count.")
    parser.add_argument("--execute-recovery", action="store_true", help="Attempt enabled recovery actions on Demo/Testnet.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase for Demo/Testnet execution.")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path.")
    args = parser.parse_args()

    cfg = load_config()
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    sync = ExchangeStateSynchronizer(cfg, store)
    router = AlertRouter.from_config(cfg, project_root=project_root())
    executor = RecoveryActionExecutor(cfg, store, alert_router=router)

    report = sync.fetch_and_record_snapshot() if args.fetch_private else sync.build_offline_report(
        exchange_qty=args.exchange_qty,
        open_order_count=args.open_order_count,
    )
    results = executor.execute_report_actions(
        report,
        execute=args.execute_recovery,
        confirmation=args.confirm,
    )
    print(json.dumps({
        "report": report.to_dict(),
        "recovery_results": [r.to_dict() for r in results],
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
