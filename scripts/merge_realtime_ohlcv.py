from __future__ import annotations

import argparse

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.realtime import merge_realtime_ohlcv_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge confirmed realtime OKX candles into a historical OHLCV parquet file.")
    parser.add_argument("--db", default=None, help="SQLite database path.")
    parser.add_argument("--inst-id", default=None)
    parser.add_argument("--channel", default=None, help="Realtime channel to merge, e.g. candle4H.")
    parser.add_argument("--input", default=None, help="Historical parquet path. Defaults to data.raw_path.")
    parser.add_argument("--output", default=None, help="Output parquet path. Defaults to realtime.merge_output_path or input.")
    parser.add_argument("--include-unconfirmed", action="store_true", help="Merge unconfirmed candles too. Not recommended for research data.")
    args = parser.parse_args()

    cfg = load_config()
    realtime_cfg = cfg.get("realtime", {})
    inst_id = args.inst_id or realtime_cfg.get("inst_id") or cfg.get("symbol", {}).get("okx_inst_id") or "BTC-USDT-SWAP"
    channel = args.channel or realtime_cfg.get("merge_channel", "candle4H")
    historical_path = resolve_path(args.input or cfg.get("data", {}).get("raw_path", "data/raw/OKX_BTC_USDT_SWAP_4h.parquet"))
    output_path = resolve_path(args.output or realtime_cfg.get("merge_output_path") or historical_path)
    db_path = resolve_path(args.db or realtime_cfg.get("database_path", "data/database/realtime_market.sqlite"))

    merged = merge_realtime_ohlcv_file(
        historical_path=historical_path,
        db_path=db_path,
        inst_id=inst_id,
        channel=channel,
        output_path=output_path,
        confirmed_only=not args.include_unconfirmed,
    )
    print(f"Merged rows={len(merged)} output={output_path}")
    if not merged.empty:
        print(merged.tail(10).to_string())


if __name__ == "__main__":
    main()
