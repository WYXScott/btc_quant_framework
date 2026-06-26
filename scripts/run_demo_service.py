from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT

from crypto_quant.config import load_config
from crypto_quant.deploy.logging_setup import setup_runtime_logging
from crypto_quant.deploy.service import DemoServiceRunner


def main() -> None:
    parser = argparse.ArgumentParser(description="Run guarded V1.0 Demo/Testnet supervisor service.")
    parser.add_argument("--max-iterations", type=int, default=None, help="Finite iteration count; default from config.")
    parser.add_argument("--interval-seconds", type=float, default=None, help="Loop interval; default from config.")
    parser.add_argument("--fetch-private", action="store_true", help="Fetch Demo/Testnet private account snapshots.")
    parser.add_argument("--execute-recovery", action="store_true", help="Allow whitelisted recovery actions if config permits.")
    parser.add_argument("--confirm", default=None, help="Required confirmation phrase for testnet recovery execution.")
    parser.add_argument("--exchange-qty", type=float, default=None, help="Offline simulated exchange position quantity.")
    parser.add_argument("--open-order-count", type=int, default=None, help="Offline simulated open-order count.")
    parser.add_argument("--skip-health-failures", action="store_true", help="Do not block start on health failures. Not recommended.")
    args = parser.parse_args()

    cfg = load_config()
    log_path = setup_runtime_logging(cfg, component="demo_service")
    print(f"Log file: {log_path}")
    runner = DemoServiceRunner(cfg)
    summary = runner.run(
        max_iterations=args.max_iterations,
        interval_seconds=args.interval_seconds,
        fetch_private=args.fetch_private,
        execute_recovery=args.execute_recovery,
        confirmation=args.confirm,
        offline_exchange_qty=args.exchange_qty,
        offline_open_order_count=args.open_order_count,
        skip_health_failures=args.skip_health_failures,
    )
    out = ROOT / "reports" / "deployment" / "last_demo_service_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(summary.to_dict(), f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2, default=str))
    print(f"Run summary written: {out}")


if __name__ == "__main__":
    main()
