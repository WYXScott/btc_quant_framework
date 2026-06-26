from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from crypto_quant.exchange.ccxt_factory import create_ccxt_exchange
from crypto_quant.exchange.safety import ExecutionSafetyGuard


@dataclass(frozen=True)
class ListenKeySession:
    listen_key: str | None
    websocket_url: str | None
    status: str
    dry_run: bool
    message: str
    created_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BinanceFuturesUserDataStream:
    """Conservative Binance USD-M Futures user-data stream helper.

    V0.8 intentionally makes the stream layer explicit and opt-in. The default
    scripts can preview the listen-key workflow offline. Real listen-key creation
    requires testnet API keys and an explicit --execute flag.
    """

    def __init__(self, cfg: dict[str, Any], *, require_private: bool = False):
        self.cfg = cfg
        self.safety = ExecutionSafetyGuard.from_config(cfg)
        self.safety.validate_environment()
        # Keep dry-run previews fully offline. The CCXT object is only needed
        # when a script explicitly requests a real Demo/Testnet listen-key action.
        self.exchange = create_ccxt_exchange(cfg, require_private=require_private) if require_private else None

    @property
    def base_ws_url(self) -> str:
        stream_cfg = self.cfg.get("user_stream", {})
        override = stream_cfg.get("websocket_base_url")
        if override:
            return str(override).rstrip("/")
        env = str(self.cfg.get("broker", {}).get("environment", "testnet")).lower()
        # Binance USD-M Futures testnet stream base. Kept configurable because
        # exchanges occasionally change hostnames.
        if env == "testnet":
            return "wss://fstream.binancefuture.com/ws"
        # Current USD-M Futures user-data stream path uses the private route.
        return "wss://fstream.binance.com/private/ws"

    def build_websocket_url(self, listen_key: str) -> str:
        return f"{self.base_ws_url}/{listen_key}"

    def _raw_method(self, name: str):
        if self.exchange is None:
            self.exchange = create_ccxt_exchange(self.cfg, require_private=True)
        method = getattr(self.exchange, name, None)
        if method is None:
            raise NotImplementedError(
                f"This CCXT build does not expose {name}. Upgrade ccxt or implement the raw endpoint adapter."
            )
        return method

    def create_listen_key(self, *, execute: bool = False, confirmation: str | None = None) -> ListenKeySession:
        self.safety.validate_confirmation(execute=execute, confirmation=confirmation)
        created_at = datetime.now(timezone.utc).isoformat()
        if not execute:
            return ListenKeySession(
                listen_key=None,
                websocket_url=None,
                status="preview",
                dry_run=True,
                message="Dry-run only. No listen key was requested from Binance.",
                created_at_utc=created_at,
            )
        method = self._raw_method("fapiPrivatePostListenKey")
        response = method({})
        listen_key = response.get("listenKey") if isinstance(response, dict) else None
        return ListenKeySession(
            listen_key=listen_key,
            websocket_url=None if not listen_key else self.build_websocket_url(str(listen_key)),
            status="created",
            dry_run=False,
            message="Listen key created. Keep it alive periodically while the stream runs.",
            created_at_utc=created_at,
        )

    def keepalive_listen_key(
        self,
        listen_key: str,
        *,
        execute: bool = False,
        confirmation: str | None = None,
    ) -> dict[str, Any]:
        self.safety.validate_confirmation(execute=execute, confirmation=confirmation)
        if not execute:
            return {"status": "preview", "dry_run": True, "listen_key": listen_key, "message": "No keepalive sent."}
        method = self._raw_method("fapiPrivatePutListenKey")
        response = method({"listenKey": listen_key})
        return {"status": "submitted", "dry_run": False, "listen_key": listen_key, "response": response}

    def close_listen_key(
        self,
        listen_key: str,
        *,
        execute: bool = False,
        confirmation: str | None = None,
    ) -> dict[str, Any]:
        self.safety.validate_confirmation(execute=execute, confirmation=confirmation)
        if not execute:
            return {"status": "preview", "dry_run": True, "listen_key": listen_key, "message": "No close request sent."}
        method = self._raw_method("fapiPrivateDeleteListenKey")
        response = method({"listenKey": listen_key})
        return {"status": "submitted", "dry_run": False, "listen_key": listen_key, "response": response}
