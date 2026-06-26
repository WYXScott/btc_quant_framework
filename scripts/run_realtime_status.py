from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.realtime import RealtimeKlineStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Print realtime market-data SQLite status and latest candles.")
    parser.add_argument("--db", default=None, help="SQLite database path.")
    parser.add_argument("--inst-id", default=None)
    parser.add_argument("--channel", default=None)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    cfg = load_config()
    realtime_cfg = cfg.get("realtime", {})
    db_path = resolve_path(args.db or realtime_cfg.get("database_path", "data/database/realtime_market.sqlite"))
    inst_id = args.inst_id or realtime_cfg.get("inst_id") or cfg.get("symbol", {}).get("okx_inst_id") or "BTC-USDT-SWAP"
    channel = args.channel
    store = RealtimeKlineStore(db_path)
    status = store.latest_status(str(realtime_cfg.get("status_component", "okx_realtime_ws")))
    latest = store.latest_klines(inst_id=inst_id, channel=channel, limit=args.limit)
    print("Realtime DB:", db_path)
    print("Status:")
    print(json.dumps(status or {}, ensure_ascii=False, indent=2, default=str))
    print("Latest klines:")
    if latest.empty:
        print("<empty>")
    else:
        print(latest.to_string(index=False))


if __name__ == "__main__":
    main()
