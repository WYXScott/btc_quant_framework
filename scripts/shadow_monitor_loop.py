from __future__ import annotations

import argparse
import json
import time

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.shadow_monitor import ShadowLivePaperMonitor


def main() -> None:
    parser = argparse.ArgumentParser(description="Finite shadow-vs-paper monitor loop.")
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=None)
    parser.add_argument("--fetch-live-readonly", action="store_true")
    parser.add_argument("--no-offline-fallback", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    loop_cfg = cfg.get("shadow_monitor", {})
    interval = float(args.interval_seconds if args.interval_seconds is not None else loop_cfg.get("interval_seconds", 300))
    monitor = ShadowLivePaperMonitor(cfg, root=ROOT)

    last = None
    for i in range(max(1, int(args.max_iterations))):
        monitor.maybe_refresh_shadow_snapshot(
            fetch_private=args.fetch_live_readonly,
            offline_fallback=not args.no_offline_fallback,
        )
        report = monitor.build_report()
        paths = monitor.write_outputs(report)
        last = {"iteration": i + 1, "status": report.status, "summary": report.summary, "paths": {k: str(v) for k, v in paths.items()}}
        print(json.dumps(last, ensure_ascii=False, indent=2, default=str))
        if i < int(args.max_iterations) - 1:
            time.sleep(interval)
    if last is not None:
        print("shadow_monitor_loop completed")


if __name__ == "__main__":
    main()
