from __future__ import annotations

import os
from typing import Any



def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def create_ccxt_exchange(cfg: dict[str, Any], *, require_private: bool = False):
    """Create a CCXT exchange instance from project config.

    In v0.4 this is used for Binance USD-M Futures demo/testnet checks. API keys
    are read from environment variables only; they are never stored in config files.
    """
    exchange_cfg = cfg.get("exchange", {})
    broker_cfg = cfg.get("broker", {})
    provider = str(broker_cfg.get("provider", exchange_cfg.get("name", "binance"))).lower()
    market_type = str(exchange_cfg.get("market_type", "future")).lower()
    use_testnet = str(broker_cfg.get("environment", "testnet")).lower() == "testnet"

    if provider not in {"binance", "binanceusdm"}:
        raise ValueError(f"v0.4 only implements Binance/Binance USD-M demo adapter, got {provider!r}")

    try:
        import ccxt  # type: ignore
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "The ccxt package is required for exchange connectivity. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    # For USD-M futures, CCXT exposes a dedicated binanceusdm class. It maps the
    # BTC/USDT perpetual symbol to BTC/USDT:USDT.
    exchange_cls = ccxt.binanceusdm if market_type in {"future", "futures", "swap"} else ccxt.binance

    api_key_var = broker_cfg.get("api_key_env", "BINANCE_TESTNET_API_KEY")
    secret_var = broker_cfg.get("secret_env", "BINANCE_TESTNET_API_SECRET")
    api_key = _env(str(api_key_var))
    secret = _env(str(secret_var))

    if require_private and (not api_key or not secret):
        raise EnvironmentError(
            f"Missing API credentials. Set {api_key_var} and {secret_var} in your shell environment."
        )

    exchange = exchange_cls({
        "apiKey": api_key,
        "secret": secret,
        "enableRateLimit": bool(exchange_cfg.get("rate_limit", True)),
        "options": {
            "defaultType": "future" if market_type in {"future", "futures", "swap"} else "spot",
            "adjustForTimeDifference": True,
        },
    })

    if use_testnet:
        # CCXT maps sandbox mode to the exchange's testnet/demo endpoints.
        exchange.set_sandbox_mode(True)

    return exchange
