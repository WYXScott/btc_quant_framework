from __future__ import annotations

from _bootstrap import ROOT

from crypto_quant.config import load_config
from crypto_quant.ops.daily_report import build_v30_operations_report


def main() -> None:
    cfg = load_config()
    payload = build_v30_operations_report(cfg)
    out_dir = ROOT / cfg.get("v3_0_report", {}).get("output_path", "reports/v3_0_operations_report")
    print("V3.0 operations report completed")
    print(f"Output: {out_dir}")
    print(f"HTML: {out_dir / 'v3_0_operations_report.html'}")
    print(payload)


if __name__ == "__main__":
    main()
