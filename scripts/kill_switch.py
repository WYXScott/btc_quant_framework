from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live import KillSwitch, LiveSafetyStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the file-based V2.0 kill switch.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true")
    group.add_argument("--trigger", action="store_true")
    group.add_argument("--clear", action="store_true")
    parser.add_argument("--reason", default="manual")
    parser.add_argument("--actor", default="operator")
    args = parser.parse_args()

    cfg = load_config()
    path = ROOT / cfg.get("live_trading", {}).get("kill_switch_path", "data/database/KILL_SWITCH.json")
    ks = KillSwitch(path)
    if args.trigger:
        payload = ks.trigger(args.reason, actor=args.actor)
        event_type = "kill_switch_triggered"
    elif args.clear:
        payload = ks.clear(args.reason, actor=args.actor)
        event_type = "kill_switch_cleared"
    else:
        payload = ks.status()
        event_type = "kill_switch_status"
    try:
        db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
        LiveSafetyStore(db_path).append_event(event_type, "blocked" if payload.get("enabled") else "pass", str(payload.get("reason", "")), payload)
    except Exception:
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
