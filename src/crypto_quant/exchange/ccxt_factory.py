from __future__ import annotations

import os
from typing import Any


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _default_type(market_type: str) -> str:
    market_type = str(market_type or "swap").lower()
    if market_type in {"swap", "perpetual", "future", "futures"}:
        return "swap" if market_type == "swap" else "future"
    return "spot"


def create_ccxt_exchange(cfg: dict[str, Any], *, require_private: bool = False):
    """Create a CCXT exchange instance from project config.

    Public OKX market data is handled by native modules elsewhere, but this
    factory also supports OKX for read-only private snapshots. Binance USD-M is
    retained for legacy demo/testnet scripts. Exchange-specific order adapters
    must still validate their own provider before submitting orders.
    """
    exchange_cfg = cfg.get("exchange", {}) or {}
    broker_cfg = cfg.get("broker", {}) or {}
    provider = str(broker_cfg.get("provider", exchange_cfg.get("name", "okx"))).lower()
    market_type = str(exchange_cfg.get("market_type", "swap")).lower()
    environment = str(broker_cfg.get("environment", "demo")).lower()
    use_sandbox = environment in {"testnet", "demo", "sandbox"} or bool(exchange_cfg.get("testnet", False))

    try:
        import ccxt  # type: ignore
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "The ccxt package is required for exchange connectivity. Install dependencies with: "
            "pip install -r requirements.txt"
        ) from exc

    if provider in {"binance", "binanceusdm"}:
        exchange_cls = ccxt.binanceusdm if market_type in {"future", "futures", "swap"} else ccxt.binance
        default_api_key_env = "BINANCE_TESTNET_API_KEY"
        default_secret_env = "BINANCE_TESTNET_API_SECRET"
        default_passphrase_env = ""
        options = {
            "defaultType": "future" if market_type in {"future", "futures", "swap"} else "spot",
            "adjustForTimeDifference": True,
        }
    elif provider == "okx":
        exchange_cls = ccxt.okx
        default_api_key_env = "OKX_API_KEY"
        default_secret_env = "OKX_API_SECRET"
        default_passphrase_env = "OKX_API_PASSPHRASE"
        options = {
            "defaultType": _default_type(market_type),
            "adjustForTimeDifference": True,
        }
    else:
        raise ValueError(f"Unsupported CCXT provider: {provider!r}. Supported providers: okx, binanceusdm, binance.")

    api_key_var = str(broker_cfg.get("api_key_env", default_api_key_env))
    secret_var = str(broker_cfg.get("secret_env", default_secret_env))
    passphrase_var = str(broker_cfg.get("passphrase_env", default_passphrase_env))
    api_key = _env(api_key_var)
    secret = _env(secret_var)
    passphrase = _env(passphrase_var) if passphrase_var else ""

    if require_private:
        missing = []
        if not api_key:
            missing.append(api_key_var)
        if not secret:
            missing.append(secret_var)
        if provider == "okx" and not passphrase:
            missing.append(passphrase_var or "OKX_API_PASSPHRASE")
        if missing:
            raise EnvironmentError(f"Missing API credentials for {provider}: set {', '.join(missing)}.")

    params: dict[str, Any] = {
        "apiKey": api_key,
        "secret": secret,
        "enableRateLimit": bool(exchange_cfg.get("rate_limit", True)),
        "options": options,
    }
    if provider == "okx" and passphrase:
        params["password"] = passphrase

    exchange = exchange_cls(params)

    if use_sandbox:
        exchange.set_sandbox_mode(True)

    return exchange
