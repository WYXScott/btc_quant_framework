from __future__ import annotations

import argparse
import json

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.realtime import run_okx_realtime_listener


def main() -> None:
    parser = argparse.ArgumentParser(description="Listen to OKX public WebSocket candles and persist them to SQLite.")
    parser.add_argument("--inst-id", default=None, help="OKX instrument id, e.g. BTC-USDT-SWAP.")
    parser.add_argument("--channels", nargs="+", default=None, help="OKX channels, e.g. candle1m candle4H.")
    parser.add_argument("--db", default=None, help="SQLite database path for realtime market data.")
    parser.add_argument("--url", default=None, help="Override OKX WebSocket URL.")
    parser.add_argument("--proxy", default=None, help="Optional proxy URL, e.g. http://127.0.0.1:7890.")
    parser.add_argument("--max-messages", type=int, default=None, help="Stop after this many WS messages. Omit for long-running mode.")
    parser.add_argument("--no-auto-merge", action="store_true", help="Disable confirmed 4H realtime-to-history merge.")
    args = parser.parse_args()

    cfg = load_config()
    realtime_cfg = cfg.get("realtime", {})
    download_cfg = cfg.get("download", {})
    inst_id = args.inst_id or realtime_cfg.get("inst_id") or download_cfg.get("inst_id") or cfg.get("symbol", {}).get("okx_inst_id") or "BTC-USDT-SWAP"
    channels = args.channels or realtime_cfg.get("channels") or ["candle1m", "candle4H"]
    db_path = resolve_path(args.db or realtime_cfg.get("database_path", "data/database/realtime_market.sqlite"))

    auto_merge_enabled = bool(realtime_cfg.get("auto_merge_history", True)) and not args.no_auto_merge
    auto_merge_config = {
        "enabled": auto_merge_enabled,
        "channel": realtime_cfg.get("merge_channel", "candle4H"),
        "historical_path": resolve_path(cfg.get("data", {}).get("raw_path", "data/raw/OKX_BTC_USDT_SWAP_4h.parquet")),
        "output_path": resolve_path(realtime_cfg.get("merge_output_path") or cfg.get("data", {}).get("raw_path", "data/raw/OKX_BTC_USDT_SWAP_4h.parquet")),
        "confirmed_only": bool(realtime_cfg.get("confirmed_only_merge", True)),
    }

    result = run_okx_realtime_listener(
        db_path=db_path,
        inst_id=inst_id,
        channels=list(channels),
        ws_url=args.url or realtime_cfg.get("ws_url"),
        proxy_url=args.proxy,
        use_env_proxy=bool(realtime_cfg.get("use_env_proxy", True)),
        prefer_base_volume=bool(realtime_cfg.get("prefer_base_volume", True)),
        max_messages=args.max_messages,
        component=str(realtime_cfg.get("status_component", "okx_realtime_ws")),
        auto_merge_config=auto_merge_config,
        reconnects=int(realtime_cfg.get("max_reconnects", 0)),
        reconnect_sleep_seconds=float(realtime_cfg.get("reconnect_sleep_seconds", 3.0)),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
