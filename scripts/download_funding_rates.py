from __future__ import annotations

import json

import _bootstrap  # noqa: F401

from crypto_quant.config import load_config, resolve_path
from crypto_quant.realism.funding import update_funding_rate_file


def main() -> None:
    cfg = load_config()
    mr_cfg = cfg.get("market_realism", {})
    out_path = resolve_path(mr_cfg.get("funding_path", "data/raw/BTCUSDT_funding_rates.parquet"))
    report_path = resolve_path(mr_cfg.get("output_path", "reports/market_realism")) / "funding_download_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df = update_funding_rate_file(
            exchange_name=cfg["exchange"].get("name", "binance"),
            symbol=cfg["symbol"]["ccxt_symbol"],
            since_iso=cfg["data"]["since"],
            output_path=out_path,
            rate_limit=cfg["exchange"].get("rate_limit", True),
        )
        payload = {"status": "ok", "rows": int(len(df)), "path": str(out_path), "start": str(df.index.min()) if not df.empty else None, "end": str(df.index.max()) if not df.empty else None}
        print(df.tail())
    except Exception as exc:  # noqa: BLE001 - script should write a useful diagnostic report
        payload = {"status": "failed", "path": str(out_path), "error": repr(exc), "note": "Funding download is optional; market realism report can still run with zero funding."}
        print("Funding download failed:", repr(exc))
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("report:", report_path)


if __name__ == "__main__":
    main()
