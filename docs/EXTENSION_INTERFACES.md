# Extension Interfaces

The package now includes `src/crypto_quant/interfaces` as a stable place for future contracts. Existing modules do not need to be rewritten immediately, but new adapters should try to conform to these shapes.

## Why Interfaces Matter

The framework is moving toward a full trading-system architecture. Without contracts, every new exchange, strategy, risk rule or execution mode would force edits across unrelated modules. Interfaces keep the boundaries explicit.

## Primary Contracts

## Market Data

`MarketDataProvider` should provide historical candles and, when supported, realtime candle streams.

Planned implementations:

- OKX REST provider
- OKX WebSocket provider
- Binance public-data provider
- local parquet/SQLite provider for replay

## Signals

`StrategyProvider` should convert market data and optional model outputs into a `StrategySignal`.

Planned implementations:

- rule strategy provider
- ML probability strategy provider
- ensemble target-exposure provider

## Risk

`RiskPolicy` should evaluate whether a signal or order intent is allowed and return a structured `RiskCheckResult`.

Planned implementations:

- local research risk policy
- paper trading risk policy
- live safety gate policy
- hard circuit breaker policy

## Execution

`ExecutionAdapter` should preview or execute `OrderIntent` objects and return an `ExecutionReport`.

Planned implementations:

- local paper adapter
- OKX demo adapter
- Binance demo adapter
- read-only shadow adapter
- blocked live adapter

## Storage

`MarketDataStore` should persist and read candles regardless of storage backend.

Planned implementations:

- parquet historical store
- SQLite realtime store
- merged replay store

## Compatibility Rule

New code may use these interfaces directly. Existing code can be migrated gradually by adding adapter wrappers around current modules. Avoid large rewrites unless an interface removes real duplication or unlocks a new execution mode.

