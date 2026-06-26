from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT

from crypto_quant.config import load_config
from crypto_quant.deploy.status import RuntimeStatusBuilder


def print_text(snapshot) -> None:
    data = snapshot.to_dict()
    derived = data["derived"]
    print("BTC Quant Runtime Status")
    print("=" * 72)
    print(f"timestamp_utc     : {data['timestamp_utc']}")
    print(f"database_path     : {data['database_path']}")
    print(f"equity            : {derived.get('equity')}")
    print(f"cash              : {derived.get('cash')}")
    print(f"realized_pnl      : {derived.get('realized_pnl')}")
    print(f"in_position       : {derived.get('in_position')}")
    print(f"position_qty      : {derived.get('position_qty')}")
    print(f"consecutive_losses: {derived.get('consecutive_losses')}")
    print(f"risk_pause_until  : {derived.get('risk_pause_until')}")
    print("-" * 72)
    for label in ["latest_decision", "latest_order", "latest_equity", "latest_alert", "latest_heartbeat"]:
        print(f"{label}:")
        print(json.dumps(data.get(label), ensure_ascii=False, indent=2, default=str))
    print("-" * 72)
    print("table_counts:")
    print(json.dumps(data["table_counts"], ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Print current paper/Demo runtime status.")
    parser.add_argument("--json", action="store_true", help="Print full JSON status snapshot.")
    parser.add_argument("--no-write", action="store_true", help="Do not write reports/deployment/runtime_status.json.")
    args = parser.parse_args()

    cfg = load_config()
    builder = RuntimeStatusBuilder(cfg, root=ROOT)
    snapshot = builder.build()
    if not args.no_write:
        path = builder.write_snapshot(snapshot)
        print(f"Status written: {path}")
    if args.json:
        print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print_text(snapshot)


if __name__ == "__main__":
    main()
