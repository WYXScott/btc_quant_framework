from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from _bootstrap import ROOT  # noqa: E402,F401

from crypto_quant.config import load_config
from crypto_quant.exchange.safety import ExecutionSafetyGuard


def main() -> None:
    cfg = load_config()
    guard = ExecutionSafetyGuard.from_config(cfg)
    broker_cfg = cfg.get("broker", {})
    exchange_cfg = cfg.get("exchange", {})
    symbol_cfg = cfg.get("symbol", {})
    api_key_env = str(broker_cfg.get("api_key_env", "BINANCE_TESTNET_API_KEY"))
    secret_env = str(broker_cfg.get("secret_env", "BINANCE_TESTNET_API_SECRET"))

    print("=== Demo broker config ===")
    print(f"provider: {broker_cfg.get('provider', 'binanceusdm')}")
    print(f"environment: {broker_cfg.get('environment', 'testnet')}")
    print(f"market_type: {exchange_cfg.get('market_type', 'future')}")
    print(f"symbol: {symbol_cfg.get('ccxt_symbol', 'BTC/USDT:USDT')}")
    print("\n=== Safety guard ===")
    print(f"environment: {guard.cfg.environment}")
    print(f"default_dry_run: {guard.cfg.default_dry_run}")
    print(f"allow_live_trading: {guard.cfg.allow_live_trading}")
    print(f"max_order_notional_usdt: {guard.cfg.max_order_notional_usdt}")
    print(f"max_leverage: {guard.cfg.max_leverage}")
    print("\n=== Credential environment variables ===")
    print(f"{api_key_env}: {'set' if os.environ.get(api_key_env) else 'missing'}")
    print(f"{secret_env}: {'set' if os.environ.get(secret_env) else 'missing'}")
    print("\nNo network request was made by this script. CCXT is not required for this check.")


if __name__ == "__main__":
    main()
