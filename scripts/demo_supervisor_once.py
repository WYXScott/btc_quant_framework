from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.alerts import AlertRouter
from crypto_quant.config import load_config, project_root, resolve_path
from crypto_quant.daemon import DemoSupervisor
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one supervised Demo/Testnet reconciliation iteration.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch private Demo/Testnet snapshots. Requires API keys.")
    parser.add_argument("--execute-recovery", action="store_true", help="Attempt enabled recovery actions on Demo/Testnet.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase for Demo/Testnet execution.")
    parser.add_argument("--exchange-qty", type=float, default=None, help="Offline simulated exchange position quantity.")
    parser.add_argument("--open-order-count", type=int, default=None, help="Offline simulated open order count.")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path.")
    args = parser.parse_args()

    cfg = load_config()
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    supervisor = DemoSupervisor(cfg, store, alert_router=AlertRouter.from_config(cfg, project_root=project_root()))
    result = supervisor.run_once(
        fetch_private=args.fetch_private,
        execute_recovery=args.execute_recovery,
        confirmation=args.confirm,
        offline_exchange_qty=args.exchange_qty,
        offline_open_order_count=args.open_order_count,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
