from __future__ import annotations

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.data.okx_downloader import update_okx_ohlcv_file


def main() -> None:
    cfg = load_config()
    output_path = resolve_path(cfg["data"]["raw_path"])
    download_cfg = cfg.get("download", {})
    inst_id = download_cfg.get("inst_id") or cfg.get("symbol", {}).get("okx_inst_id") or "BTC-USDT-SWAP"
    df = update_okx_ohlcv_file(
        inst_id=inst_id,
        timeframe=cfg["data"]["timeframe"],
        since_iso=cfg["data"]["since"],
        output_path=output_path,
        downloader_config=download_cfg,
    )
    print(df.tail())
    print(f"Saved {len(df)} OKX rows to {output_path}")


if __name__ == "__main__":
    main()
