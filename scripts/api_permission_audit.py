from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.prelive_workflow import ApiPermissionAuditor, PreLiveWorkflowStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an offline API permission/configuration audit for V2.2.")
    parser.add_argument("--output", default=None, help="Optional output JSON path.")
    args = parser.parse_args()
    cfg = load_config()
    audit = ApiPermissionAuditor(cfg).audit()
    db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
    store = PreLiveWorkflowStore(db_path)
    store.append_api_audit(audit)
    if args.output:
        out = ROOT / args.output
    else:
        out = ROOT / cfg.get("prelive_operator_workflow", {}).get("output_path", "reports/prelive_operator") / "api_permission_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(audit.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": audit.status, "output": str(out), "audit": audit.to_dict()}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
