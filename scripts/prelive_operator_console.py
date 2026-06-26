from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.prelive_workflow import PreLiveReviewBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the V2.2 pre-live operator console and review report.")
    parser.add_argument("--refresh-shadow", action="store_true", help="Refresh the shadow monitor report before building console.")
    parser.add_argument("--fetch-live-readonly", action="store_true", help="Fetch live read-only snapshot using BINANCE_LIVE_READONLY_* env vars.")
    parser.add_argument("--output-dir", default=None, help="Default: prelive_operator_workflow.output_path")
    args = parser.parse_args()
    cfg = load_config()
    builder = PreLiveReviewBuilder(cfg, root=ROOT)
    report = builder.build(refresh_shadow=args.refresh_shadow, fetch_live_readonly=args.fetch_live_readonly)
    paths = builder.write_outputs(report, args.output_dir)
    print(json.dumps({
        "status": report.status,
        "decision": report.decision,
        "summary": report.summary,
        "paths": {k: str(v) for k, v in paths.items()},
        "blockers": [b.to_dict() for b in report.blockers],
        "warnings": [w.to_dict() for w in report.warnings],
    }, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
