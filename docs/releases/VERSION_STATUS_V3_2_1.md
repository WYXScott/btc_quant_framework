# V3.2.1 Version Status — OKX-First Cleanup And Dashboard Noise Reduction

## Status

V3.2.1 keeps the V3.2.0 frontend/navigation improvements and tightens the project around the intended operating model: OKX public data plus local paper trading.

## Main changes

- Project version updated to `3.2.1`.
- Default downloader remains `okx_native`; fallback defaults no longer point to Binance.
- `execution.mode` is documented as `local_paper` for the supported main workflow.
- Legacy demo/private-execution sections are disabled or documented as future adapter placeholders.
- `.env.example` now uses OKX variables instead of Binance testnet variables.
- Optional funding-rate output path changed to `data/raw/OKX_BTC_USDT_SWAP_funding_rates.parquet`.
- Funding-rate helper accepts the configured exchange market type, so OKX swap funding can be attempted through CCXT when available.
- Streamlit tables are routed through an Arrow-safe display helper to remove mixed-type dataframe serialization noise.
- Deprecated Streamlit `use_container_width` calls are replaced with `width="stretch"`.
- Deprecated `pd.Timestamp.utcnow()` calls are replaced with timezone-aware `pd.Timestamp.now(tz="UTC")`.

## Current supported path

```text
OKX public candles
→ data quality gate
→ feature/label generation
→ direction model training
→ calibration and walk-forward validation
→ local SQLite paper trading
→ operations reports
```

## Known boundaries

- OKX private order submission is still not implemented.
- The remaining exchange/demo files are archival or future-interface scaffolding, not the default user path.
- Funding-rate download is optional and may depend on CCXT/venue support.
