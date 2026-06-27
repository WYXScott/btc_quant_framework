# Release Notes V3.1.0

V3.1.0 introduces managed local services for the BTC Quant Framework WebUI.

## Added

- New `managed_services` configuration block.
- New `crypto_quant.ui.service_manager` module.
- New `scripts/manage_services.py` CLI for service list/status/start/stop/restart/logs.
- New Streamlit **服务控制台** page.
- Service state files under `reports/services`.
- Service log files under `logs/services`.
- New service operations documentation.
- New V3.1.0 version status and next-step document.

## Initial Services

- `okx_realtime_listener`: runs the OKX public WebSocket candle listener with extended reconnect settings.
- `paper_ensemble_loop`: runs the local SQLite-backed ensemble paper-trading loop.

## Stability

- `scripts/run_stability_check.py` now checks managed-service configuration.
- Service PID records are verified against the process command line before stop/restart, reducing PID-reuse mis-kill risk.
- Stale PID records are marked as `exited_or_stale` or `stale_pid_mismatch`.
- Service logs can be inspected directly from the WebUI.
- Paper ensemble loops stop after repeated consecutive failures instead of silently running forever in a broken state.
- `requests` is now declared explicitly in `requirements.txt` for the OKX REST downloader.

## Safety

The service console does not enable real-money trading. The first service whitelist is limited to public market data and local paper trading.

Additional V3.1.0 hardening:

- `data_quality.require_pass_before_training` is enabled so feature/model generation is blocked by critical OHLCV quality failures.
- Realtime-to-history K-line merges validate the merged OHLCV before writing when the quality gate is enabled.
- OKX-focused configs remain in `local_paper`; the legacy `binance_futures_demo` path now fails fast if `broker.provider` is not Binance/Binance USD-M.
- CCXT factory supports OKX read-only private snapshots with passphrase env support, but OKX order execution remains intentionally unimplemented.

Do not add live execution, demo execution or private-API recovery scripts to `managed_services.allowed` until a separate service approval gate exists.
