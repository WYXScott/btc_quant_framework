from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from _bootstrap import ROOT

from crypto_quant.config import load_config
from crypto_quant.deploy.health import DeploymentHealthChecker
from crypto_quant.deploy.status import RuntimeStatusBuilder
from crypto_quant.paper.database import PaperStore


def copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a runtime diagnostic bundle for review/debugging.")
    parser.add_argument("--include-logs", action="store_true", help="Include logs directory.")
    parser.add_argument("--include-database", action="store_true", help="Include SQLite database file. Avoid sharing if it contains sensitive data.")
    args = parser.parse_args()

    cfg = load_config()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bundle_dir = ROOT / "reports" / "runtime_bundle" / f"bundle_{ts}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    checker = DeploymentHealthChecker(cfg, root=ROOT)
    health = checker.run()
    (bundle_dir / "health_report.json").write_text(json.dumps(health.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    status = RuntimeStatusBuilder(cfg, root=ROOT).build()
    (bundle_dir / "runtime_status.json").write_text(json.dumps(status.to_dict(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    copy_if_exists(ROOT / "config" / "config.yaml", bundle_dir / "config" / "config.yaml")
    copy_if_exists(ROOT / "README.md", bundle_dir / "README.md")
    copy_if_exists(ROOT / "RELEASE_NOTES.md", bundle_dir / "RELEASE_NOTES.md")

    paper_cfg = cfg.get("paper", {}) or {}
    db_path = Path(paper_cfg.get("database_path", "data/database/paper_trading.sqlite"))
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    store = PaperStore(db_path)
    csv_dir = bundle_dir / "paper_csv"
    exported = store.export_csvs(csv_dir)
    (bundle_dir / "exported_tables.json").write_text(json.dumps({k: str(v) for k, v in exported.items()}, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.include_logs:
        copy_if_exists(ROOT / "logs", bundle_dir / "logs")
    if args.include_database:
        copy_if_exists(db_path, bundle_dir / "database" / db_path.name)

    archive = shutil.make_archive(str(bundle_dir), "zip", bundle_dir)
    print(f"Runtime bundle directory: {bundle_dir}")
    print(f"Runtime bundle zip      : {archive}")


if __name__ == "__main__":
    main()
