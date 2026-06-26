from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from crypto_quant.exchange.binance_futures_demo import BinanceFuturesDemoBroker
from crypto_quant.exchange.recovery import ExchangePositionSnapshot


@dataclass(frozen=True)
class OpenOrderClassification:
    total_count: int
    protective_count: int
    reduce_only_count: int
    stop_loss_count: int
    take_profit_count: int
    trailing_stop_count: int
    non_protective_count: int
    raw_orders: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExchangeExecutionState:
    """Execution-time snapshot used by V1.7 synchronized target execution.

    The object is intentionally small and serializable. It can be built from a
    real Binance Demo/Testnet private snapshot or from offline values for tests.
    """

    timestamp_utc: str
    source: str
    symbol: str
    equity_usdt: float
    position: ExchangePositionSnapshot
    open_orders: list[dict[str, Any]]
    order_classification: OpenOrderClassification
    mark_price: float | None = None
    raw_balance: dict[str, Any] | None = None

    @property
    def current_qty(self) -> float:
        return max(0.0, float(self.position.contracts or 0.0))

    @property
    def in_position(self) -> bool:
        return self.current_qty > 0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["position"] = self.position.to_dict()
        d["order_classification"] = self.order_classification.to_dict()
        return d


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def classify_open_orders(open_orders: list[dict[str, Any]] | None) -> OpenOrderClassification:
    orders = list(open_orders or [])
    protective_count = 0
    reduce_only_count = 0
    stop_loss_count = 0
    take_profit_count = 0
    trailing_stop_count = 0

    for order in orders:
        info = order.get("info", {}) if isinstance(order.get("info"), dict) else {}
        order_type = str(order.get("type") or order.get("order_type") or info.get("type") or info.get("origType") or "").upper()
        reduce_only = order.get("reduceOnly")
        if reduce_only is None:
            reduce_only = order.get("reduce_only")
        if reduce_only is None:
            reduce_only = info.get("reduceOnly")
        is_reduce_only = _truthy(reduce_only)
        if is_reduce_only:
            reduce_only_count += 1

        is_stop = order_type in {"STOP", "STOP_MARKET"}
        is_tp = order_type in {"TAKE_PROFIT", "TAKE_PROFIT_MARKET"}
        is_trailing = order_type == "TRAILING_STOP_MARKET"
        if is_stop:
            stop_loss_count += 1
        if is_tp:
            take_profit_count += 1
        if is_trailing:
            trailing_stop_count += 1
        if is_reduce_only or is_stop or is_tp or is_trailing:
            protective_count += 1

    return OpenOrderClassification(
        total_count=len(orders),
        protective_count=protective_count,
        reduce_only_count=reduce_only_count,
        stop_loss_count=stop_loss_count,
        take_profit_count=take_profit_count,
        trailing_stop_count=trailing_stop_count,
        non_protective_count=max(0, len(orders) - protective_count),
        raw_orders=orders,
    )


def _parse_usdt_equity(balance: dict[str, Any], default_equity: float) -> float:
    """Best-effort extraction of USDT equity from CCXT/Binance futures balance."""
    candidates: list[Any] = []
    total = balance.get("total") if isinstance(balance, dict) else None
    free = balance.get("free") if isinstance(balance, dict) else None
    if isinstance(total, dict):
        candidates.append(total.get("USDT"))
    if isinstance(free, dict):
        candidates.append(free.get("USDT"))
    info = balance.get("info", {}) if isinstance(balance.get("info"), dict) else {}
    for key in ["totalWalletBalance", "totalMarginBalance", "availableBalance", "totalCrossWalletBalance"]:
        candidates.append(info.get(key))
    assets = info.get("assets")
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, dict) and str(asset.get("asset", "")).upper() == "USDT":
                for key in ["marginBalance", "walletBalance", "availableBalance"]:
                    candidates.append(asset.get(key))
    for value in candidates:
        try:
            f = float(value)
            if f > 0:
                return f
        except (TypeError, ValueError):
            continue
    return float(default_equity)


def build_offline_execution_state(
    cfg: dict[str, Any],
    *,
    exchange_qty: float = 0.0,
    equity_usdt: float | None = None,
    open_order_count: int = 0,
    mark_price: float | None = None,
) -> ExchangeExecutionState:
    symbol = str(cfg.get("symbol", {}).get("ccxt_symbol", "BTC/USDT:USDT"))
    qty = float(exchange_qty or 0.0)
    equity = float(equity_usdt if equity_usdt is not None else cfg.get("trading", {}).get("initial_equity", 1000.0))
    position = ExchangePositionSnapshot(
        symbol=symbol,
        contracts=qty,
        side="long" if qty > 0 else None,
        entry_price=None,
        notional=None if mark_price is None else abs(qty) * float(mark_price),
        raw={"offline_simulated": True},
    )
    orders = [{"type": "STOP_MARKET", "reduceOnly": True, "offline_simulated": True} for _ in range(int(open_order_count or 0))]
    classification = classify_open_orders(orders)
    return ExchangeExecutionState(
        timestamp_utc=utc_now_iso(),
        source="offline_simulated_exchange",
        symbol=symbol,
        equity_usdt=equity,
        position=position,
        open_orders=orders,
        order_classification=classification,
        mark_price=None if mark_price is None else float(mark_price),
        raw_balance=None,
    )


def fetch_demo_execution_state(cfg: dict[str, Any]) -> ExchangeExecutionState:
    """Fetch Demo/Testnet balance, position and open-order state through CCXT.

    This requires private testnet credentials. The function performs no trading;
    it is safe for pre-trade synchronization checks.
    """
    broker = BinanceFuturesDemoBroker(cfg, require_private=True)
    position = broker.fetch_position_snapshot()
    open_orders = broker.fetch_open_orders_snapshot()
    balance = broker.exchange.fetch_balance()
    default_equity = float(cfg.get("trading", {}).get("initial_equity", 1000.0))
    equity = _parse_usdt_equity(balance, default_equity=default_equity)
    mark_price = None
    try:
        ticker = broker.exchange.fetch_ticker(broker.symbol)
        if ticker and ticker.get("last") is not None:
            mark_price = float(ticker.get("last"))
    except Exception:
        mark_price = None
    return ExchangeExecutionState(
        timestamp_utc=utc_now_iso(),
        source="binance_futures_demo_private_snapshot",
        symbol=broker.symbol,
        equity_usdt=equity,
        position=position,
        open_orders=open_orders,
        order_classification=classify_open_orders(open_orders),
        mark_price=mark_price,
        raw_balance=balance,
    )
