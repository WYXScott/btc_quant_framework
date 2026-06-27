# V3.0.8 Version Status And Next Steps

This document closes the current BTC Quant Framework version into a more stable research-and-paper-trading baseline.

## Current Position

V3.0.8 is a safety-first BTC/USDT perpetual-swap quant research framework focused on OKX public market data, local modeling, local paper trading, operational reports and a Streamlit control console.

The system is currently suitable for:

- OKX public REST historical candle download.
- OKX public WebSocket realtime candle ingestion.
- Local parquet and SQLite data storage.
- Feature generation and supervised direction-model research.
- Walk-forward validation and probability calibration.
- Strategy research, parameter search and ensemble backtesting.
- SQLite-backed local paper trading and replay.
- Operations reports and signal hit-rate diagnostics.
- Read-only safety checks and pre-live review workflows.

The system is not currently suitable for:

- Real-money unattended live trading.
- High-frequency execution.
- Production-grade hosted multi-user operation.
- Fully automated capital allocation.

## Stability Closure In V3.0.8

V3.0.8 adds a release-readiness check:

```powershell
python scripts/run_stability_check.py
```

It writes:

```text
reports/stability/stability_report.json
reports/stability/stability_checks.csv
```

The Streamlit **软件审查** page can run and display the same check.

The stability check focuses on:

- repository structure
- release-note consistency
- UI script whitelist consistency
- critical safety switches
- key runtime artifact paths
- realtime SQLite schema

Warnings are expected when runtime data, reports or models have not been generated locally. Failures should be fixed before treating a release as stable.

## Current Risk Profile

### Low Risk

- Public market-data ingestion.
- Offline feature/model research.
- Local paper-trading replay.
- Report generation.
- WebUI workflow buttons constrained by `ui.allowed_button_scripts`.

### Medium Risk

- Long-running realtime WebSocket ingestion, because OKX/network disconnects can still occur.
- Model and strategy interpretation, because current performance remains observational rather than production-grade.
- Generated local artifacts, because large parquet, SQLite, model and report files are intentionally not committed.

### High Risk

- Real-money live execution.
- Private exchange API use.
- Automatic leverage changes.
- Any workflow that bypasses the current safety switches.

## Recommended Operating Flow

For normal research:

```powershell
start_dashboard.bat
```

Then use the Streamlit **流程中心**:

1. 稳定性收口检查
2. 下载公开K线
3. 检查K线质量
4. 构建特征与标签
5. 训练方向模型
6. Walk-forward校准
7. 策略参数搜索
8. 组合策略回测
9. 初始化/回放模拟盘
10. 生成运营日报

For realtime data:

1. Open **实时行情**.
2. Run **OKX REST连通性诊断**.
3. Run **采样实时行情** with bounded message and reconnect settings.
4. Only after sampling is stable, run the listener continuously from a terminal.

## Development Recommendations

### Next: V3.1 Background Services

Add a controlled background-service layer:

- realtime listener service wrapper
- service status file
- stop/restart scripts
- Windows Task Scheduler notes
- WebUI service-state display

This should come before any new trading features.

### Next: Data Freshness And Artifact Registry

Add a single artifact registry that tracks:

- latest raw candle timestamp
- latest realtime candle timestamp
- latest dataset build time
- latest model train time
- latest paper replay time
- latest report generation time

This will make the WebUI easier to trust at a glance.

### Next: Paper Trading Hardening

Before demo/live execution, improve paper mode:

- persistent paper run loop status
- configurable replay windows
- paper account reset confirmation
- drawdown and stale-signal alerts
- daily baseline comparison against buy-and-hold

### Next: Model Improvement

Current model quality should be treated as watchlist/research level. Prioritize:

- cleaner target definitions
- regime filters
- feature stability analysis
- stronger walk-forward score gates
- calibration drift monitoring
- paper-candidate promotion rules

### Later: Execution Interfaces

Only after stable realtime and long paper validation:

- OKX demo trading adapter
- order intent preview only
- private API permission audit
- manual approval workflow
- strict notional and leverage caps

Live execution should remain disabled by default.

## Release Gate

A future version should be considered releasable only when:

- `python tests/smoke_test.py` passes.
- `python scripts/run_stability_check.py` returns `status: pass`.
- Streamlit opens successfully.
- Git working tree is clean after commit.
- Safety switches remain in their default blocked state.
