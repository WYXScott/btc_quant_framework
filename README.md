# BTC Quant Framework

A safety-first Python framework for BTC/USDT perpetual-swap quantitative research, walk-forward validation, local paper trading, operations reporting, and OKX public market-data ingestion.

当前版本：**V3.1.0**

> This project is for research, backtesting, local paper trading, and read-only safety monitoring. It does not enable real-money automated trading by default.

## Overview

BTC Quant Framework 是一套面向 **BTC/USDT 永续合约低频量化研究** 的工程化框架。它把数据下载、数据质量检查、特征工程、模型训练、概率校准、策略回测、组合策略、SQLite 本地模拟盘、运营日报、只读影子监控和 Streamlit 前端控制台放在一个可迭代的项目里。

V3.1.0 的主线是 **本地后台服务控制台**：

- 新增 `managed_services` 白名单配置
- 新增本地服务管理器和 `scripts/manage_services.py`
- 前端新增“服务控制台”，支持启动、停止、重启、刷新和查看日志
- 第一批托管服务覆盖 OKX 实时行情监听和本地组合模拟盘循环
- 稳定性检查扩展到服务配置和服务脚本

V3.0.8 的主线是 **版本收口与稳定性自检**：

- 新增离线稳定性检查脚本与报告
- 前端软件审查页展示稳定性收口状态
- 流程中心加入稳定性检查步骤
- 补齐当前版本说明和后续开发建议

V3.0.7 的主线是 **实时行情连接恢复与前端体验增强**：

- OKX WebSocket `ConnectionResetError(10054)` 识别为可恢复网络错误
- 实时状态记录重连尝试、错误分类和恢复详情
- Streamlit 实时行情页展示连接健康、10054 说明和重连参数
- 前端按钮执行器捕获超时和系统异常，避免页面崩溃

V3.0.6 的主线是 **WebUI 流程中心与按钮化操作**：

- Streamlit 新增按阶段组织的流程中心
- 常用命令行流程可从界面选择步骤并运行
- 运行结果、输出日志和关键产物状态在界面内展示
- 实时行情采样和模拟盘回放支持界面参数

V3.0.5 的主线是 **OKX 实时行情落库**：

- OKX WebSocket `candle1m` / `candle4H` 接入
- 实时 K 线写入 SQLite `realtime_klines`
- 连接状态写入 `realtime_status`
- 前端展示 OKX 最新价格、连接状态和最近 K 线
- 已确认的 `candle4H` 可合并回历史 4H parquet 数据

## Features

- **OKX public market data**: native REST historical candles and WebSocket realtime candles.
- **Data quality**: OHLCV validation, missing/duplicate timestamp checks, extreme move warnings, and non-finite feature checks.
- **Feature engineering**: returns, moving averages, volatility, ATR-style features, volume features, candle structure, RSI.
- **Model research**: ExtraTrees, RandomForest, Logistic Regression, HistGradientBoosting, optional LightGBM/XGBoost, and sequence-model experiments.
- **Validation**: fixed split, walk-forward prediction, walk-forward probability calibration, purged/embargo CV.
- **Backtesting**: leveraged long-only research engine, dynamic target-exposure engine, fee/slippage assumptions, drawdown metrics.
- **Strategy library**: trend, breakout, mean-reversion, volatility compression, model-driven, and ensemble strategies.
- **Local paper trading**: SQLite-backed account, orders, decisions, equity curve, target-exposure replay.
- **Operations layer**: daily paper-health reports, signal hit-rate reports, admission snapshots, operational alerts.
- **Safety layer**: dry-run defaults, live gate, kill switch, hard circuit breaker, read-only shadow mode, manual pre-live workflow.
- **Frontend**: Streamlit research console for data, models, reports, paper trading, realtime data, managed local services, and safety checks.

## Architecture

```text
config/config.yaml
        |
        v
scripts/                     CLI entrypoints
        |
        v
src/crypto_quant/
  data/                      REST downloaders, realtime WebSocket storage, parquet utilities
  features/                  feature generation and labels
  models/                    training, prediction, calibration, walk-forward
  strategy/                  rule and ML signals
  backtest/                  fixed and dynamic exposure engines
  research/                  diagnostics, model libraries, robustness, ensembles
  paper/                     SQLite-backed local paper trading
  exchange/                  demo/testnet intent, safety, reconciliation, order lifecycle
  live/                      live safety gate, kill switch, read-only shadow workflows
  ops/                       daily operations reports
  ui/                        Streamlit helper layer
frontend/app.py              Streamlit console
```

## Quick Start

Windows users can start the Streamlit console from the repository root:

```bat
start_dashboard.bat
```

Or double-click `start_dashboard.bat`.

Manual setup:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/run_dashboard.py
```

Open:

```text
http://localhost:8501
```

The dashboard is the easiest way to inspect data, run safe scripts, view reports, monitor realtime OKX candles, and run the staged workflow center.

## OKX Market Data

Download/update historical 4H BTC-USDT-SWAP candles:

```bash
python scripts/download_okx_ohlcv.py
```

Sample realtime WebSocket candles and persist them to SQLite:

```bash
python scripts/run_okx_realtime_listener.py --max-messages 5
python scripts/run_realtime_status.py
```

Run the realtime listener continuously:

```bash
python scripts/run_okx_realtime_listener.py
```

Merge confirmed realtime `candle4H` rows into the historical 4H parquet dataset:

```bash
python scripts/merge_realtime_ohlcv.py
```

More details: [docs/OKX_REALTIME_MARKET_DATA.md](docs/OKX_REALTIME_MARKET_DATA.md)

## Research Pipeline

Recommended baseline flow:

```bash
python scripts/download_ohlcv.py
python scripts/run_data_quality_check.py
python scripts/build_features.py
python scripts/train_model.py
python scripts/run_model_diagnostics.py
python scripts/train_calibrated_model.py
python scripts/run_signal_confidence_report.py
python scripts/run_calibrated_ml_backtest.py
python scripts/run_walk_forward_calibration.py
python scripts/run_strategy_parameter_search.py
python scripts/run_ensemble_strategy.py
```

One-shot safe pipeline:

```bash
python scripts/run_safe_research_pipeline.py --include-download
```

## Paper Trading And Operations

Initialize and replay local paper trading:

```bash
python scripts/paper_init.py --reset
python scripts/paper_ensemble_replay_dataset.py --bars 300 --reset
```

Generate operations reports:

```bash
python scripts/run_paper_health_check.py
python scripts/run_signal_hit_rate_report.py
python scripts/run_daily_operations_report.py
python scripts/build_v30_operations_report.py
```

## Optional Model Backends

The default environment does not require LightGBM, XGBoost, or PyTorch.

Optional tabular backends:

```bash
pip install -r requirements-optional.txt
python scripts/check_model_backends.py
```

Optional sequence-model experiments:

```bash
pip install -r requirements-sequence.txt
python scripts/check_sequence_model_backends.py
python scripts/run_sequence_model_experiments.py
python scripts/run_sequence_walk_forward.py
```

Sequence-model outputs are research-only and are not wired directly into execution.

## Repository Hygiene

The repository tracks source code, docs, configs, templates, scripts, tests, and `.gitkeep` placeholders.

The following local/runtime artifacts are intentionally ignored:

- `.venv/`
- real `.env` files and private keys
- raw and processed market data
- SQLite databases
- trained `.joblib` models
- generated reports
- logs
- Python caches

This keeps GitHub lightweight and avoids publishing local data, credentials, or model artifacts.

## Safety Boundaries

- Real-money automated trading is disabled by default.
- Streamlit does not expose live order buttons.
- Demo/testnet execution paths default to dry-run unless explicit flags and confirmation phrases are provided.
- Live gate blocks real trading unless multiple config switches and manual workflows are changed.
- Read-only shadow mode is separated from order submission.
- Public market-data ingestion does not require API keys.

## Key Docs

- [Documentation index](docs/INDEX.md)
- [System architecture](docs/SYSTEM_ARCHITECTURE.md)
- [Operating model](docs/OPERATING_MODEL.md)
- [Extension interfaces](docs/EXTENSION_INTERFACES.md)
- [Data and artifacts](docs/DATA_AND_ARTIFACTS.md)
- [Roadmap](docs/ROADMAP.md)
- [OKX realtime market data](docs/OKX_REALTIME_MARKET_DATA.md)
- [OKX data access](docs/OKX_DATA_ACCESS.md)
- [Data quality and market realism](docs/DATA_QUALITY_MARKET_REALISM.md)
- [Walk-forward calibration](docs/WALK_FORWARD_CALIBRATION.md)
- [Model strategy admission](docs/MODEL_STRATEGY_ADMISSION.md)
- [Operations daily reports](docs/OPERATIONS_DAILY_REPORTS.md)
- [Safety checklist](docs/SAFETY_CHECKLIST.md)

## Version Notes

- **V3.1.0**: managed local services, WebUI service console, service status/log files and service-config stability checks.
- **V3.0.8**: stability closure check, WebUI stability report entry, current-version status document and next-development recommendations.
- **V3.0.7**: realtime connection recovery metadata, 10054 handling, Streamlit connection health panel and safer UI script runner.
- **V3.0.6**: Streamlit workflow center, run history, artifact status tables, and UI controls for realtime sampling and paper replay.
- **V3.0.5**: OKX realtime WebSocket candle persistence, realtime Streamlit page, confirmed 4H merge path.
- **V3.0**: long-running paper-trading operations layer and daily reports.
- **V2.9**: unified model/strategy leaderboard and admission layer.
- **V2.8**: sequence-model experiment layer.
- **V2.7**: enhanced model library and optional backend handling.

See [RELEASE_NOTES_V3_1_0.md](RELEASE_NOTES_V3_1_0.md), [docs/VERSION_STATUS_V3_1_0.md](docs/VERSION_STATUS_V3_1_0.md), and the older release-note files for details.

## Roadmap

- Harden OKX realtime reconnect and proxy diagnostics.
- Add background service wrappers for realtime ingestion.
- Add realtime-to-paper signal handoff after sufficient monitoring.
- Improve model performance beyond observation/watchlist status.
- Add richer dashboard status cards for data freshness and pipeline health.

## Disclaimer

This repository is for engineering research and educational experimentation. It is not financial advice and does not guarantee trading performance. Use real-money trading only after independent review, long paper validation, and explicit safety configuration.
