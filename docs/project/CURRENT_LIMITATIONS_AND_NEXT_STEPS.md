# Current Limitations And Next Steps

This note summarizes the main gaps in the current V3.2.1 codebase and the most useful follow-up work.

## Current Limitations

1. **Data coverage is still narrow.** The default research dataset focuses on BTC-USDT-SWAP 4H candles. Funding rates are optional, order-book depth is absent, and multi-symbol validation is not yet part of the baseline pipeline.
2. **Realtime and historical data are only loosely integrated.** The OKX realtime listener can persist candles and merge confirmed 4H bars, but there is not yet a fully automated data freshness gate that blocks stale paper decisions.
3. **Feature engineering is mostly technical-indicator based.** The current features are useful baselines, but they do not yet include richer regime, liquidity, calendar, cross-market, derivatives, or order-flow features.
4. **Model admission remains conservative and report-driven.** The project has walk-forward, calibration, purged CV, and leaderboard checks, but there is no single enforced promotion workflow that writes an immutable model card before paper deployment.
5. **Backtests are research approximations.** They include fees, slippage, leverage and drawdown stops, but do not model full exchange microstructure, partial fills, latency, liquidation mechanics, borrow/funding timing, or candle-path ambiguity in depth.
6. **Execution is intentionally incomplete.** The supported main workflow is OKX public data plus local SQLite paper trading. Private OKX execution adapters are placeholders by design and should not be enabled without a separate safety review.
7. **Frontend is useful but still script-centric.** Streamlit organizes the workflow better than earlier versions, but many buttons still launch scripts instead of sharing one typed orchestration API with structured progress and error states.
8. **Testing is broad but not deep enough.** Smoke tests cover many modules, yet there are few focused unit tests for edge cases such as timezone-naive data, missing candles, single-class folds, stale realtime rows, and paper-trading restart recovery.
9. **Documentation has been reorganized, not fully rewritten.** Some older docs still mention Binance demo paths or legacy version context. They should be reviewed as archived or future-adapter material.
10. **Operations evidence is still local-file based.** Reports, logs, and SQLite state are local artifacts. There is no external observability store, alert workflow, or dashboard history suitable for long unattended validation.

## Recommended Next Improvements

1. **Add a dataset manifest and freshness gate.** Record source, symbol, timeframe, start/end, row count, missing bars, quality status, and last update time for every dataset artifact.
2. **Make model promotion explicit.** Require a model card containing training window, feature list hash, walk-forward metrics, calibration metrics, backtest summary, and admission decision before paper use.
3. **Expand out-of-sample validation.** Add multi-period stress tests, market-regime segmentation, fee/slippage stress, funding-aware backtests, and strict comparisons against buy-and-hold and simple trend baselines.
4. **Improve feature set carefully.** Add regime, realized-volatility structure, funding, basis, calendar, and liquidity proxies, with leakage checks for every new feature group.
5. **Harden paper trading loops.** Add data freshness checks, idempotent decision IDs, restart recovery tests, and clear "no new candle" behavior at the service layer.
6. **Unify script orchestration.** Move repeated script logic behind typed Python workflow functions so CLI, Streamlit, and future schedulers all call the same code paths.
7. **Add focused tests.** Create unit tests for data quality edge cases, timezone normalization, walk-forward purge behavior, calibrated folds, and out-of-sample-only backtests.
8. **Archive legacy exchange docs clearly.** Mark Binance demo/private execution documents as legacy or future-adapter references so the OKX-first workflow remains obvious.
9. **Build an OKX private adapter only after paper evidence.** Add it behind an explicit interface with dry-run defaults, permission audit, read-only mode, capped test orders, and manual approval.
10. **Improve operational observability.** Add structured JSON logs, report summaries, alert thresholds, and a simple daily validation digest before considering unattended operation.
