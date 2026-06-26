from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.shadow_monitor import build_v21_readiness_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build V2.1 shadow/live readiness report.")
    parser.add_argument("--fetch-live-readonly", action="store_true")
    parser.add_argument("--output", default="reports/shadow_monitor/v2_1_shadow_readiness_report.json")
    args = parser.parse_args()

    cfg = load_config()
    payload = build_v21_readiness_payload(cfg, root=ROOT, fetch_live_readonly=args.fetch_live_readonly)
    out = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": payload["status"], "path": str(out), "summary": payload.get("summary", {})}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
