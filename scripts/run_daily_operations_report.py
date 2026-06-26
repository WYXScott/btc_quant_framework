from __future__ import annotations

from _bootstrap import ROOT

from crypto_quant.config import load_config
from crypto_quant.ops.daily_report import build_operations_daily_report


def main() -> None:
    cfg = load_config()
    summary = build_operations_daily_report(cfg)
    out_dir = ROOT / cfg.get("operations", {}).get("output_path", "reports/operations")
    print("V3.0 daily operations report completed")
    print(f"Output: {out_dir}")
    print(f"HTML: {out_dir / 'daily_operations_report.html'}")
    print(summary)


if __name__ == "__main__":
    main()
