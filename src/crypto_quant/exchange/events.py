from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


EventKind = Literal["order", "account", "unknown"]


@dataclass(frozen=True)
class NormalizedExchangeEvent:
    """Venue-neutral view of a Binance futures user-data event.

    The raw websocket/REST payload is always kept so that early Demo/Testnet
    observations can be audited without losing exchange-specific fields.
    """

    event_time: str | int | None
    kind: EventKind
    symbol: str | None = None
    side: str | None = None
    order_type: str | None = None
    order_status: str | None = None
    client_order_id: str | None = None
    exchange_order_id: str | int | None = None
    execution_type: str | None = None
    quantity: float | None = None
    filled_quantity: float | None = None
    last_fill_quantity: float | None = None
    average_price: float | None = None
    last_fill_price: float | None = None
    realized_pnl: float | None = None
    reduce_only: bool | None = None
    position_side: str | None = None
    position_amount: float | None = None
    entry_price: float | None = None
    mark_price: float | None = None
    raw_event_type: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_filled_order(self) -> bool:
        return self.kind == "order" and str(self.order_status or "").upper() == "FILLED"

    @property
    def is_reduce_only_exit_fill(self) -> bool:
        return self.is_filled_order and bool(self.reduce_only)

    @property
    def is_flat_position(self) -> bool:
        return self.position_amount is not None and abs(float(self.position_amount)) <= 1e-12

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def parse_binance_user_data_event(event: dict[str, Any]) -> list[NormalizedExchangeEvent]:
    """Parse Binance USD-M user-data stream events into normalized records.

    Supported high-value event types:
    - ORDER_TRADE_UPDATE: order status/fill updates;
    - ACCOUNT_UPDATE: position/account deltas.

    Unknown event types are retained as kind="unknown" so they still enter the
    audit trail instead of being silently dropped.
    """
    event_type = str(event.get("e") or event.get("eventType") or "")
    event_time = event.get("E") or event.get("eventTime")

    if event_type == "ORDER_TRADE_UPDATE":
        order = event.get("o", {}) or {}
        return [
            NormalizedExchangeEvent(
                event_time=event_time,
                kind="order",
                symbol=order.get("s"),
                side=order.get("S"),
                order_type=order.get("o"),
                order_status=order.get("X"),
                client_order_id=order.get("c"),
                exchange_order_id=order.get("i"),
                execution_type=order.get("x"),
                quantity=_float_or_none(order.get("q")),
                filled_quantity=_float_or_none(order.get("z")),
                last_fill_quantity=_float_or_none(order.get("l")),
                average_price=_float_or_none(order.get("ap")),
                last_fill_price=_float_or_none(order.get("L")),
                realized_pnl=_float_or_none(order.get("rp")),
                reduce_only=_bool_or_none(order.get("R")),
                position_side=order.get("ps"),
                raw_event_type=event_type,
                raw=event,
            )
        ]

    if event_type == "ACCOUNT_UPDATE":
        account = event.get("a", {}) or {}
        positions = account.get("P", []) or []
        parsed: list[NormalizedExchangeEvent] = []
        for pos in positions:
            parsed.append(
                NormalizedExchangeEvent(
                    event_time=event_time,
                    kind="account",
                    symbol=pos.get("s"),
                    position_side=pos.get("ps"),
                    position_amount=_float_or_none(pos.get("pa")),
                    entry_price=_float_or_none(pos.get("ep")),
                    mark_price=_float_or_none(pos.get("mt")),
                    raw_event_type=event_type,
                    raw=event,
                )
            )
        if parsed:
            return parsed

    return [
        NormalizedExchangeEvent(
            event_time=event_time,
            kind="unknown",
            raw_event_type=event_type or None,
            raw=event,
        )
    ]


def sample_order_trade_update_fill() -> dict[str, Any]:
    """Small built-in sample used by offline smoke/replay scripts."""
    return {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1760000000000,
        "T": 1760000000000,
        "o": {
            "s": "BTCUSDT",
            "c": "btcq_sl_sample",
            "S": "SELL",
            "o": "STOP_MARKET",
            "f": "GTC",
            "q": "0.001",
            "p": "0",
            "ap": "49500.0",
            "sp": "49500.0",
            "x": "TRADE",
            "X": "FILLED",
            "i": 123456789,
            "l": "0.001",
            "z": "0.001",
            "L": "49500.0",
            "n": "0.02",
            "N": "USDT",
            "T": 1760000000000,
            "t": 987654321,
            "b": "0",
            "a": "0",
            "m": False,
            "R": True,
            "wt": "MARK_PRICE",
            "ot": "STOP_MARKET",
            "ps": "BOTH",
            "cp": False,
            "rp": "-5.0",
        },
    }


def sample_account_update_flat() -> dict[str, Any]:
    return {
        "e": "ACCOUNT_UPDATE",
        "E": 1760000001000,
        "T": 1760000001000,
        "a": {
            "m": "ORDER",
            "B": [],
            "P": [
                {
                    "s": "BTCUSDT",
                    "pa": "0",
                    "ep": "0.0",
                    "bep": "0.0",
                    "cr": "0",
                    "up": "0",
                    "mt": "isolated",
                    "iw": "0",
                    "ps": "BOTH",
                }
            ],
        },
    }
