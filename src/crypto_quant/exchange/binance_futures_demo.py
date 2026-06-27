from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crypto_quant.exchange.ccxt_factory import create_ccxt_exchange
from crypto_quant.exchange.order_intent import OrderIntent
from crypto_quant.exchange.protective_orders import NativeProtectiveOrderPlan
from crypto_quant.exchange.recovery import ExchangePositionSnapshot
from crypto_quant.exchange.safety import ExecutionSafetyGuard


@dataclass
class DemoExecutionResult:
    status: str
    dry_run: bool
    intent: dict[str, Any]
    response: dict[str, Any] | None = None
    message: str = ""


class BinanceFuturesDemoBroker:
    """Binance USD-M Futures demo/testnet adapter.

    The adapter is deliberately conservative. Its primary use is to verify
    connectivity, preview orders, and optionally place very small orders on
    Binance's demo/testnet environment after explicit confirmation.

    V0.7 adds native protective-order helpers. The scripts still default to
    offline dry-run preview, so importing this module does not imply live or
    testnet execution.
    """

    def __init__(self, cfg: dict[str, Any], *, require_private: bool = False):
        self.cfg = cfg
        provider = str((cfg.get("broker", {}) or {}).get("provider", (cfg.get("exchange", {}) or {}).get("name", "binanceusdm"))).lower()
        if provider not in {"binance", "binanceusdm"}:
            raise ValueError(
                "BinanceFuturesDemoBroker requires broker.provider='binanceusdm' or 'binance'. "
                f"Current provider is {provider!r}. Keep execution.mode='local_paper' for OKX-focused research, "
                "or add a dedicated OKX execution adapter before enabling exchange orders."
            )
        self.safety = ExecutionSafetyGuard.from_config(cfg)
        self.safety.validate_environment()
        self.exchange = create_ccxt_exchange(cfg, require_private=require_private)

    @property
    def symbol(self) -> str:
        return str(self.cfg["symbol"]["ccxt_symbol"])

    def describe(self) -> dict[str, Any]:
        broker_cfg = self.cfg.get("broker", {})
        return {
            "provider": broker_cfg.get("provider", "binanceusdm"),
            "environment": broker_cfg.get("environment", "testnet"),
            "market_type": self.cfg.get("exchange", {}).get("market_type", "future"),
            "symbol": self.symbol,
            "default_dry_run": broker_cfg.get("safety", {}).get("default_dry_run", True),
        }

    def public_connectivity_check(self) -> dict[str, Any]:
        server_time = self.exchange.fetch_time()
        markets = self.exchange.load_markets()
        symbol_exists = self.symbol in markets
        ticker = self.exchange.fetch_ticker(self.symbol) if symbol_exists else None
        return {
            "server_time": server_time,
            "symbol": self.symbol,
            "symbol_exists": symbol_exists,
            "last": None if ticker is None else ticker.get("last"),
        }

    def private_connectivity_check(self) -> dict[str, Any]:
        balance = self.exchange.fetch_balance()
        return {
            "free": balance.get("free", {}),
            "total": balance.get("total", {}),
            "info_keys": sorted(list(balance.get("info", {}).keys()))[:20] if isinstance(balance.get("info"), dict) else [],
        }

    def fetch_position_snapshot(self) -> ExchangePositionSnapshot:
        """Fetch one symbol position snapshot through CCXT when private access is available."""
        positions = self.exchange.fetch_positions([self.symbol])
        selected: dict[str, Any] | None = None
        for pos in positions:
            if pos.get("symbol") == self.symbol or pos.get("info", {}).get("symbol") == self.cfg["symbol"].get("raw_symbol"):
                selected = pos
                break
        if selected is None:
            selected = {"symbol": self.symbol, "contracts": 0.0, "side": None, "entryPrice": None, "notional": None, "info": {}}
        contracts = selected.get("contracts")
        if contracts is None:
            info = selected.get("info", {}) or {}
            contracts = info.get("positionAmt") or info.get("positionAmt") or 0.0
        return ExchangePositionSnapshot(
            symbol=str(selected.get("symbol") or self.symbol),
            contracts=float(contracts or 0.0),
            side=selected.get("side"),
            entry_price=None if selected.get("entryPrice") is None else float(selected.get("entryPrice")),
            notional=None if selected.get("notional") is None else float(selected.get("notional")),
            raw=selected,
        )

    def fetch_open_orders_snapshot(self) -> list[dict[str, Any]]:
        return list(self.exchange.fetch_open_orders(self.symbol))

    def set_leverage(self, leverage: float, *, execute: bool = False, confirmation: str | None = None) -> dict[str, Any]:
        self.safety.validate_order_limits(quantity=1e-8, reference_price=1.0, leverage=float(leverage))
        self.safety.validate_confirmation(execute=execute, confirmation=confirmation)
        if not execute:
            return {
                "status": "preview",
                "dry_run": True,
                "symbol": self.symbol,
                "leverage": float(leverage),
                "message": "Dry-run leverage update preview only.",
            }
        response = self.exchange.set_leverage(int(leverage), self.symbol)
        return {"status": "submitted", "dry_run": False, "symbol": self.symbol, "response": response}

    @staticmethod
    def _ccxt_order_type(order_type: str) -> str:
        mapping = {
            "market": "market",
            "limit": "limit",
            "stop_market": "STOP_MARKET",
            "take_profit_market": "TAKE_PROFIT_MARKET",
            "trailing_stop_market": "TRAILING_STOP_MARKET",
        }
        if order_type not in mapping:
            raise ValueError(f"Unsupported order_type for Binance futures demo: {order_type}")
        return mapping[order_type]

    @staticmethod
    def _ccxt_params(intent: OrderIntent) -> dict[str, Any]:
        params: dict[str, Any] = dict(intent.extra_params or {})
        if intent.reduce_only:
            params["reduceOnly"] = True
        if intent.client_order_id:
            params["newClientOrderId"] = intent.client_order_id
        if intent.stop_price is not None:
            params["stopPrice"] = float(intent.stop_price)
        if intent.activation_price is not None:
            params["activationPrice"] = float(intent.activation_price)
        if intent.callback_rate is not None:
            params["callbackRate"] = float(intent.callback_rate)
        if intent.working_type:
            params["workingType"] = intent.working_type
        if intent.close_position:
            params["closePosition"] = "true"
            params.pop("reduceOnly", None)
        if intent.position_side:
            params["positionSide"] = intent.position_side
        if intent.time_in_force:
            params["timeInForce"] = intent.time_in_force
        return params

    @property
    def raw_symbol(self) -> str:
        return str(self.cfg.get("symbol", {}).get("raw_symbol") or self.symbol.replace("/", "").replace(":USDT", ""))

    @staticmethod
    def _is_conditional(intent: OrderIntent) -> bool:
        return intent.order_type in {"stop_market", "take_profit_market", "trailing_stop_market"}

    def _algo_order_payload(self, intent: OrderIntent) -> dict[str, Any]:
        """Build payload for Binance USD-M Futures algo conditional order endpoint.

        Binance migrated USD-M conditional orders to the Algo Service. Therefore
        V0.7 uses this raw endpoint for SL/TP/trailing orders instead of assuming
        CCXT's create_order route will always remain compatible.
        """
        payload: dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": self.raw_symbol,
            "side": intent.side.upper(),
            "type": self._ccxt_order_type(intent.order_type),
        }
        if not intent.close_position:
            payload["quantity"] = float(intent.quantity)
        if intent.stop_price is not None:
            payload["triggerPrice"] = float(intent.stop_price)
        if intent.activation_price is not None:
            payload["activatePrice"] = float(intent.activation_price)
        if intent.callback_rate is not None:
            payload["callbackRate"] = float(intent.callback_rate)
        if intent.working_type:
            payload["workingType"] = intent.working_type
        if intent.position_side:
            payload["positionSide"] = intent.position_side
        if intent.close_position:
            payload["closePosition"] = "true"
        elif intent.reduce_only:
            payload["reduceOnly"] = "true"
        if intent.client_order_id:
            payload["clientAlgoId"] = intent.client_order_id
        if intent.time_in_force:
            payload["timeInForce"] = intent.time_in_force
        payload.update(intent.extra_params or {})
        return payload

    def _submit_algo_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        method = getattr(self.exchange, "fapiPrivatePostAlgoOrder", None)
        if method is None:
            # Older CCXT versions may not expose the newly generated raw method.
            # Falling back to create_order is intentionally avoided for conditionals
            # because Binance now documents the Algo Service as the TP/SL route.
            raise NotImplementedError(
                "This CCXT build does not expose fapiPrivatePostAlgoOrder. "
                "Upgrade ccxt before submitting native protective orders."
            )
        return method(payload)

    def place_order(
        self,
        intent: OrderIntent,
        *,
        reference_price: float,
        execute: bool = False,
        confirmation: str | None = None,
    ) -> DemoExecutionResult:
        intent.validate()
        self.safety.validate_order_limits(
            quantity=max(float(intent.quantity), 1e-12),
            reference_price=float(reference_price),
            leverage=intent.leverage,
        )
        self.safety.validate_confirmation(execute=execute, confirmation=confirmation)

        intent_dict = intent.to_dict()
        if not execute:
            return DemoExecutionResult(
                status="preview",
                dry_run=True,
                intent=intent_dict,
                message="Dry-run only. No exchange order was sent.",
            )

        if self._is_conditional(intent):
            payload = self._algo_order_payload(intent)
            response = self._submit_algo_order(payload)
        else:
            params = self._ccxt_params(intent)
            response = self.exchange.create_order(
                symbol=intent.symbol,
                type=self._ccxt_order_type(intent.order_type),
                side=intent.side,
                amount=None if intent.close_position else float(intent.quantity),
                price=None if intent.order_type != "limit" else intent.price,
                params=params,
            )
        return DemoExecutionResult(status="submitted", dry_run=False, intent=intent_dict, response=response)

    def place_protective_order_plan(
        self,
        plan: NativeProtectiveOrderPlan,
        *,
        execute: bool = False,
        confirmation: str | None = None,
    ) -> dict[str, Any]:
        """Preview or submit all protective order intents in a plan."""
        results: list[dict[str, Any]] = []
        for intent in plan.intents:
            reference_price = (
                float(intent.stop_price)
                if intent.stop_price is not None
                else float(intent.activation_price or plan.entry_price)
            )
            res = self.place_order(
                intent,
                reference_price=reference_price,
                execute=execute,
                confirmation=confirmation,
            )
            results.append({
                "status": res.status,
                "dry_run": res.dry_run,
                "intent": res.intent,
                "response": res.response,
                "message": res.message,
            })
        return {
            "status": "submitted" if execute else "preview",
            "dry_run": not execute,
            "symbol": plan.symbol,
            "num_orders": len(results),
            "warnings": plan.warnings,
            "orders": results,
        }

    def place_order_intents(
        self,
        intents: list[OrderIntent],
        *,
        reference_price: float,
        execute: bool = False,
        confirmation: str | None = None,
    ) -> dict[str, Any]:
        """Preview or submit a list of neutral order intents sequentially.

        This helper is used by V1.6 target-position execution. It keeps the
        broker safety guard centralized and returns a uniform audit payload.
        """
        results: list[dict[str, Any]] = []
        for intent in intents:
            res = self.place_order(
                intent,
                reference_price=float(reference_price),
                execute=execute,
                confirmation=confirmation,
            )
            results.append({
                "status": res.status,
                "dry_run": res.dry_run,
                "intent": res.intent,
                "response": res.response,
                "message": res.message,
            })
        return {
            "status": "submitted" if execute else "preview",
            "dry_run": not execute,
            "symbol": self.symbol,
            "num_orders": len(results),
            "orders": results,
        }

    def cancel_open_orders(
        self,
        *,
        execute: bool = False,
        confirmation: str | None = None,
        include_algo: bool = True,
    ) -> dict[str, Any]:
        self.safety.validate_confirmation(execute=execute, confirmation=confirmation)
        if not execute:
            return {
                "status": "preview",
                "dry_run": True,
                "symbol": self.symbol,
                "include_algo": include_algo,
                "message": "Dry-run cancel-all preview only. No network request was made.",
            }
        responses: dict[str, Any] = {"standard_orders": self.exchange.cancel_all_orders(self.symbol)}
        if include_algo:
            method = getattr(self.exchange, "fapiPrivateDeleteAlgoOpenOrders", None)
            if method is None:
                responses["algo_orders"] = {
                    "status": "skipped",
                    "message": "CCXT build does not expose fapiPrivateDeleteAlgoOpenOrders.",
                }
            else:
                responses["algo_orders"] = method({"symbol": self.raw_symbol})
        return {"status": "submitted", "dry_run": False, "symbol": self.symbol, "response": responses}
