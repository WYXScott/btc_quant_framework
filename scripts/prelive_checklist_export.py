from __future__ import annotations

import argparse
import json

from _bootstrap import ROOT
from crypto_quant.config import load_config
from crypto_quant.live.prelive_workflow import PreLiveWorkflowStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Export V2.2 pre-live checklist and approvals to CSV.")
    parser.add_argument("--output-dir", default=None, help="Default: prelive_operator_workflow.output_path")
    args = parser.parse_args()
    cfg = load_config()
    db_path = ROOT / cfg.get("paper", {}).get("database_path", "data/database/paper_trading.sqlite")
    output_dir = ROOT / (args.output_dir or cfg.get("prelive_operator_workflow", {}).get("output_path", "reports/prelive_operator"))
    store = PreLiveWorkflowStore(db_path)
    store.initialize_default_checklist(reset=False)
    paths = store.export_tables(output_dir)
    print(json.dumps({"status": "ok", "paths": {k: str(v) for k, v in paths.items()}}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
