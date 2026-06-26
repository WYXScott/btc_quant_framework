from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.prelive_workflow import build_v22_readiness_payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the V2.2 go-live readiness review payload.")
    parser.add_argument("--refresh-shadow", action="store_true", help="Refresh shadow monitor before building the review.")
    parser.add_argument("--fetch-live-readonly", action="store_true", help="Fetch live read-only snapshot using BINANCE_LIVE_READONLY_* env vars.")
    parser.add_argument("--output", default=None, help="Optional output JSON path.")
    args = parser.parse_args()
    cfg = load_config()
    payload = build_v22_readiness_payload(cfg, root=ROOT, refresh_shadow=args.refresh_shadow, fetch_live_readonly=args.fetch_live_readonly)
    out = ROOT / (args.output or cfg.get("prelive_operator_workflow", {}).get("readiness_report_path", "reports/prelive_operator/v2_2_go_live_review_report.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": payload.get("status"), "decision": payload.get("decision"), "output": str(out), "summary": payload.get("summary")}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
