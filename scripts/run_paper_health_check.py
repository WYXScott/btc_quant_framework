from __future__ import annotations

import json

from _bootstrap import ROOT

from crypto_quant.config import load_config, resolve_path
from crypto_quant.ops.daily_report import summarize_paper_account, _ops_cfg


def main() -> None:
    cfg = load_config()
    ocfg = _ops_cfg(cfg)
    out_dir = resolve_path(ocfg.output_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary, equity, orders, target = summarize_paper_account(cfg)
    (out_dir / "paper_health_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    if not equity.empty:
        equity.tail(int(ocfg.max_table_rows)).to_csv(out_dir / "paper_health_equity_tail.csv", index=False)
    if not orders.empty:
        orders.tail(int(ocfg.max_table_rows)).to_csv(out_dir / "paper_health_orders_tail.csv", index=False)
    if not target.empty:
        target.tail(int(ocfg.max_table_rows)).to_csv(out_dir / "paper_health_target_exposure_tail.csv", index=False)
    print("Paper health check completed")
    print(f"Output: {out_dir}")
    print(summary)


if __name__ == "__main__":
    main()
