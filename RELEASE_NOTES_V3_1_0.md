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
- Stale PID records are marked as `exited_or_stale`.
- Service logs can be inspected directly from the WebUI.

## Safety

The service console does not enable real-money trading. The first service whitelist is limited to public market data and local paper trading.

Do not add live execution, demo execution or private-API recovery scripts to `managed_services.allowed` until a separate service approval gate exists.
