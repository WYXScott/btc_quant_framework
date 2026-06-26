from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.ohlcv_downloader import update_ohlcv_file


def main() -> None:
    cfg = load_config()
    output_path = resolve_path(cfg["data"]["raw_path"])
    df = update_ohlcv_file(
        exchange_name=cfg["exchange"]["name"],
        market_type=cfg["exchange"]["market_type"],
        symbol=cfg["symbol"]["ccxt_symbol"],
        raw_symbol=cfg["symbol"].get("raw_symbol"),
        timeframe=cfg["data"]["timeframe"],
        since_iso=cfg["data"]["since"],
        output_path=output_path,
        downloader=cfg.get("download", {}).get("downloader", "binance_native"),
        downloader_config=cfg.get("download", {}),
    )
    print(df.tail())
    print(f"Saved {len(df)} rows to {output_path}")


if __name__ == "__main__":
    main()
