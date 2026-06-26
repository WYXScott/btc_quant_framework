from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.shadow_monitor import ShadowLivePaperMonitor


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare read-only shadow-live snapshot with local paper/ensemble state.")
    parser.add_argument("--fetch-live-readonly", action="store_true", help="Fetch a fresh live read-only snapshot using BINANCE_LIVE_READONLY_* env vars.")
    parser.add_argument("--no-offline-fallback", action="store_true", help="Do not create an offline preview snapshot when none exists.")
    parser.add_argument("--output-dir", default=None, help="Override output directory. Default: config shadow_monitor.output_path.")
    args = parser.parse_args()

    cfg = load_config()
    monitor = ShadowLivePaperMonitor(cfg, root=ROOT)
    monitor.maybe_refresh_shadow_snapshot(
        fetch_private=args.fetch_live_readonly,
        offline_fallback=not args.no_offline_fallback,
    )
    report = monitor.build_report()
    paths = monitor.write_outputs(report, args.output_dir)
    print(json.dumps({
        "status": report.status,
        "summary": report.summary,
        "paths": {k: str(v) for k, v in paths.items()},
        "warnings": [w.to_dict() for w in report.warnings],
        "blockers": [b.to_dict() for b in report.blockers],
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
