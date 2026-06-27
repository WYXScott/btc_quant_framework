from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config
from crypto_quant.ui.service_manager import (
    get_service_status,
    restart_service,
    service_spec_rows,
    service_status_rows,
    start_service,
    stop_service,
    tail_service_log,
)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage local BTC Quant background services.")
    parser.add_argument("action", choices=["list", "status", "start", "stop", "restart", "logs"])
    parser.add_argument("name", nargs="?", help="Managed service name from config.managed_services.allowed.")
    parser.add_argument("--tail-chars", type=int, default=12000, help="Characters to read from the end of a service log.")
    args = parser.parse_args()

    cfg = load_config()

    if args.action == "list":
        _print_json(service_spec_rows(cfg))
        return

    if args.action == "status" and not args.name:
        _print_json(service_status_rows(cfg))
        return

    if not args.name:
        raise SystemExit(f"{args.action} requires a service name")

    if args.action == "status":
        _print_json(get_service_status(cfg, args.name))
    elif args.action == "start":
        _print_json(start_service(cfg, args.name))
    elif args.action == "stop":
        _print_json(stop_service(cfg, args.name))
    elif args.action == "restart":
        _print_json(restart_service(cfg, args.name))
    elif args.action == "logs":
        print(tail_service_log(cfg, args.name, max_chars=args.tail_chars) or "<no log>")


if __name__ == "__main__":
    main()
