# Release Notes V3.2.1

## OKX-first cleanup

- Tightened the default configuration around OKX public market data and local paper trading.
- Removed Binance-oriented credentials from `.env.example`.
- Removed Binance from the default downloader fallback path.
- Marked old private/demo execution sections as disabled future adapter placeholders.
- Updated stability checks so `local_paper` is the only supported main execution mode.

## Dashboard console cleanup

- Added an Arrow-safe dataframe display wrapper for mixed status/config tables.
- Replaced deprecated Streamlit `use_container_width` usage with `width="stretch"`.
- Replaced deprecated `pd.Timestamp.utcnow()` calls with timezone-aware UTC timestamps.

## Market realism

- Switched the default funding-rate file to `OKX_BTC_USDT_SWAP_funding_rates.parquet`.
- Funding download now passes the configured exchange market type to the CCXT funding helper.

## Documentation

- Added `docs/OKX_FIRST_CONFIGURATION.md`.
- Added `docs/VERSION_STATUS_V3_2_1.md`.
