from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live import LiveSafetyGate


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the V2.0 live-trading safety gate.")
    parser.add_argument("--mode", default="live_order", choices=["live_order", "shadow_live", "demo"], help="Gate context label.")
    parser.add_argument("--output", default=None, help="Optional output JSON path.")
    args = parser.parse_args()

    cfg = load_config()
    out = args.output or cfg.get("live_trading", {}).get(
        "live_gate_report_path", "reports/live_safety/live_gate_report.json"
    )
    report = LiveSafetyGate(cfg, root=ROOT).write_report(out, mode=args.mode)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str))
    if report.status == "blocked":
        print("\nLIVE ORDER EXECUTION IS BLOCKED. This is the expected default for V2.0.")
    elif report.status == "warn":
        print("\nLive gate has warnings; do not execute without resolving them.")
    else:
        print("\nLive gate passed, but real execution should still require explicit operator confirmation.")


if __name__ == "__main__":
    main()
