# V3.1.0 Version Status And Service Console

V3.1.0 moves BTC Quant Framework from a mostly script-driven local console toward a controlled local operations console.

## What Changed

The main addition is a managed-service layer:

- `src/crypto_quant/ui/service_manager.py`
- `scripts/manage_services.py`
- `managed_services` config block
- Streamlit **服务控制台** page
- service-state files under `reports/services`
- service logs under `logs/services`

The first managed services are:

- `okx_realtime_listener`
- `paper_ensemble_loop`

These are deliberately limited to public market data and local paper trading.

## Current Position

The framework now supports three operating modes:

| Mode | Interface | Use |
| --- | --- | --- |
| One-shot scripts | `scripts/*.py` | Research, reports, backtests and bounded diagnostics. |
| Workflow buttons | Streamlit **流程中心** | Guided manual operation without memorizing commands. |
| Managed services | Streamlit **服务控制台** / `manage_services.py` | Long-running local listeners and paper loops. |

This is still a local research and paper-trading framework. It is not a production hosted trading system.

## Stability Improvements

V3.1.0 improves stability in four ways:

- Long-running tasks now have explicit process status files.
- Logs are centralized under `logs/services`.
- The WebUI can stop stale or unwanted background processes.
- `run_stability_check.py` validates managed service configuration.

The service manager also detects when a saved PID is no longer running and marks it as `exited_or_stale`.

## Recommended Workflow

1. Start the dashboard with `start_dashboard.bat`.
2. Run **软件审查** -> **运行稳定性检查**.
3. Use **实时行情** for bounded WebSocket sampling.
4. Use **服务控制台** to start `okx_realtime_listener` only after sampling is stable.
5. Use **服务控制台** to start `paper_ensemble_loop` only after the paper account and ensemble artifacts are ready.
6. Use **运营日报** and **软件审查** to review results.

## Risk Boundary

Low-risk service candidates:

- public WebSocket listeners
- local SQLite paper loops
- local health monitors
- report builders

Do not run these as managed services yet:

- live order execution
- demo/testnet order execution with private API keys
- leverage-changing scripts
- recovery execution scripts
- anything requiring manual confirmation phrases

Those need a separate service approval gate before they are safe to expose.

## Next Development Suggestions

### V3.1.1 Service UX Polish

- show elapsed runtime
- show last log update time
- add per-service stale warnings
- add a confirmation checkbox for stop/restart
- add a clearer realtime freshness badge

### V3.2 Artifact Registry

Create one registry that records freshness for:

- latest raw candle
- latest realtime candle
- latest feature dataset
- latest trained model
- latest backtest
- latest paper step
- latest operations report

This will make the front page more trustworthy.

### V3.3 Paper Operation Hardening

- add paper-loop heartbeat
- add stale-signal alerts
- add paper replay profiles
- add baseline comparison against buy-and-hold
- add drawdown and skipped-signal summaries

### Later: Execution Services

Execution should remain outside the service console until the system has:

- dedicated OKX demo adapter
- strict dry-run proof
- private API permission audit
- manual operator approval
- service-level kill switch
- maximum notional and leverage caps

Live trading should remain disabled by default.
