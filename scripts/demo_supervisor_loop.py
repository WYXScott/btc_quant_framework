from __future__ import annotations

import argparse
import json
import _bootstrap  # noqa: F401

from crypto_quant.alerts import AlertRouter
from crypto_quant.config import load_config, project_root, resolve_path
from crypto_quant.daemon import DemoSupervisor
from crypto_quant.paper.database import PaperStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a finite supervised Demo/Testnet monitor loop.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch private Demo/Testnet snapshots. Requires API keys.")
    parser.add_argument("--execute-recovery", action="store_true", help="Attempt enabled recovery actions on Demo/Testnet.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase for Demo/Testnet execution.")
    parser.add_argument("--interval-seconds", type=int, default=None, help="Override supervisor polling interval.")
    parser.add_argument("--max-iterations", type=int, default=1, help="Finite loop length. Keep small until stable.")
    parser.add_argument("--db", default=None, help="Optional SQLite DB path.")
    args = parser.parse_args()

    cfg = load_config()
    supervisor_cfg = cfg.get("supervisor", {}) or {}
    interval = int(args.interval_seconds or supervisor_cfg.get("interval_seconds", cfg.get("sync", {}).get("poll_interval_seconds", 60)))
    store = PaperStore(resolve_path(args.db or cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")))
    supervisor = DemoSupervisor(cfg, store, alert_router=AlertRouter.from_config(cfg, project_root=project_root()))
    results = supervisor.run_loop(
        max_iterations=int(args.max_iterations),
        interval_seconds=interval,
        fetch_private=args.fetch_private,
        execute_recovery=args.execute_recovery,
        confirmation=args.confirm,
    )
    print(json.dumps({"results": [r.to_dict() for r in results]}, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
