from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol, runtime_checkable

import pandas as pd

from crypto_quant.execution.decision import StrategyDecision
from crypto_quant.exchange.order_intent import OrderIntent


SignalDirection = Literal[-1, 0, 1]
ExecutionMode = Literal["local_paper", "demo", "live", "shadow", "blocked"]
ExecutionStatus = Literal["preview", "submitted", "filled", "rejected", "blocked", "error", "no_order_required"]


@dataclass(frozen=True)
class MarketCandle:
    exchange: str
    symbol: str
    timeframe: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    confirmed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketSnapshot:
    exchange: str
    symbol: str
    timestamp: str
    mark_price: float | None = None
    last_price: float | None = None
    bid: float | None = None
    ask: float | None = None
    funding_rate: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategySignal:
    timestamp: str
    symbol: str
    direction: SignalDirection
    target_exposure: float
    confidence: float | None = None
    probability_up: float | None = None
    reason: str = "strategy_signal"
    strategy_name: str | None = None
    model_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioState:
    timestamp: str
    equity: float
    cash: float
    position_qty: float
    entry_price: float | None = None
    leverage: float = 1.0
    realized_pnl: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def in_position(self) -> bool:
        return abs(float(self.position_qty)) > 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskCheckResult:
    allowed: bool
    reason: str
    severity: Literal["pass", "warning", "blocked"] = "pass"
    adjusted_target_exposure: float | None = None
    max_order_notional: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionReport:
    timestamp: str
    mode: ExecutionMode
    status: ExecutionStatus
    dry_run: bool
    symbol: str | None = None
    intent: OrderIntent | None = None
    exchange_order_id: str | None = None
    client_order_id: str | None = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        if self.intent is not None:
            out["intent"] = self.intent.to_dict()
        return out


@runtime_checkable
class MarketDataProvider(Protocol):
    name: str

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: str | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Return OHLCV data indexed by UTC timestamp."""

    def stream_candles(
        self,
        *,
        symbol: str,
        channels: list[str],
    ) -> Iterable[MarketCandle]:
        """Yield realtime candles when the provider supports streaming."""


@runtime_checkable
class MarketDataStore(Protocol):
    def write_candles(self, candles: Iterable[MarketCandle]) -> int:
        """Persist candles and return the number accepted by the store."""

    def read_ohlcv(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int | None = None,
        confirmed_only: bool = True,
    ) -> pd.DataFrame:
        """Read normalized OHLCV data."""


@runtime_checkable
class FeaturePipeline(Protocol):
    def build_features(self, ohlcv: pd.DataFrame, config: dict[str, Any] | None = None) -> pd.DataFrame:
        """Build model-ready features from OHLCV data."""


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    def fit(self, dataset: pd.DataFrame, feature_columns: list[str], target_column: str) -> None:
        """Train or update the model."""

    def predict_proba(self, dataset: pd.DataFrame, feature_columns: list[str]) -> pd.Series:
        """Return probability of the positive class indexed like dataset."""

    def save(self, path: str | Path) -> None:
        """Persist the model."""

    def load(self, path: str | Path) -> None:
        """Load the model."""


@runtime_checkable
class StrategyProvider(Protocol):
    name: str

    def generate_signal(
        self,
        *,
        market_data: pd.DataFrame,
        portfolio: PortfolioState,
        model_output: pd.DataFrame | None = None,
        config: dict[str, Any] | None = None,
    ) -> StrategySignal:
        """Generate one strategy signal for the latest market state."""


@runtime_checkable
class RiskPolicy(Protocol):
    name: str

    def evaluate_signal(
        self,
        *,
        signal: StrategySignal,
        portfolio: PortfolioState,
        market: MarketSnapshot | None = None,
    ) -> RiskCheckResult:
        """Evaluate whether a signal is allowed."""

    def evaluate_intent(
        self,
        *,
        intent: OrderIntent,
        portfolio: PortfolioState,
        market: MarketSnapshot | None = None,
    ) -> RiskCheckResult:
        """Evaluate whether an order intent is allowed."""


@runtime_checkable
class ExecutionAdapter(Protocol):
    mode: ExecutionMode

    def preview(self, intent: OrderIntent, *, market: MarketSnapshot | None = None) -> ExecutionReport:
        """Return an execution report without submitting an order."""

    def execute(
        self,
        intent: OrderIntent,
        *,
        market: MarketSnapshot | None = None,
        confirmation: str | None = None,
    ) -> ExecutionReport:
        """Execute or block an order intent."""


@runtime_checkable
class OperationsReporter(Protocol):
    name: str

    def build_report(self, *, config: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
        """Build an operations or audit report and return a summary."""


def signal_to_strategy_decision(
    *,
    signal: StrategySignal,
    portfolio: PortfolioState,
    price: float,
    leverage: float,
    margin_fraction: float,
    risk_allowed: bool,
) -> StrategyDecision:
    """Bridge the future StrategySignal contract to the current StrategyDecision object."""
    if signal.direction > 0 and not portfolio.in_position:
        action = "buy"
    elif signal.direction <= 0 and portfolio.in_position:
        action = "sell"
    elif portfolio.in_position:
        action = "hold_position"
    else:
        action = "hold_cash"
    notional_fraction = abs(float(signal.target_exposure))
    return StrategyDecision(
        timestamp=signal.timestamp,
        symbol=signal.symbol,
        price=float(price),
        action=action,
        reason=signal.reason,
        signal=int(signal.direction),
        prob_up=signal.probability_up,
        equity=float(portfolio.equity),
        position_qty=float(portfolio.position_qty),
        leverage=float(leverage),
        margin_fraction=float(margin_fraction),
        notional_fraction=notional_fraction,
        risk_allowed=bool(risk_allowed),
        metadata={
            "confidence": signal.confidence,
            "strategy_name": signal.strategy_name,
            "model_name": signal.model_name,
            **dict(signal.metadata),
        },
    )
