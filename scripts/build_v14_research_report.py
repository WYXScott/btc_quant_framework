from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.research.ensemble import build_ensemble_report


def main() -> None:
    cfg = load_config()
    ens_cfg = cfg.get("ensemble", {})
    dyn_cfg = cfg.get("dynamic_positioning", {})
    report_path = resolve_path(ens_cfg.get("report_path", "reports/v1_4_research_report/v1_4_research_report.html"))
    path = build_ensemble_report(
        output_path=report_path,
        ensemble_dir=resolve_path(ens_cfg.get("output_path", "reports/ensemble")),
        grid_dir=resolve_path(dyn_cfg.get("output_path", "reports/dynamic_positioning")),
    )
    print(f"saved report: {path}")


if __name__ == "__main__":
    main()
