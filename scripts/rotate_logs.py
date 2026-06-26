from __future__ import annotations

import argparse
from pathlib import Path

from _bootstrap import ROOT

from crypto_quant.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual cleanup for old runtime logs.")
    parser.add_argument("--keep", type=int, default=10, help="Number of newest log files to keep.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config()
    log_dir = Path(cfg.get("logging", {}).get("log_dir", "logs"))
    if not log_dir.is_absolute():
        log_dir = ROOT / log_dir
    files = sorted([p for p in log_dir.glob("*.log*") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    to_delete = files[args.keep:]
    for p in to_delete:
        print(("would delete" if args.dry_run else "deleting"), p)
        if not args.dry_run:
            p.unlink(missing_ok=True)
    print(f"Kept {min(len(files), args.keep)} log files; selected {len(to_delete)} for deletion.")


if __name__ == "__main__":
    main()
