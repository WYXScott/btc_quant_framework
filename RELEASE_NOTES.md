# Release Notes

## V2.4

V2.4 是数据质量检查、回测真实性增强和严格时间序列验证版本。

新增内容：

- 新增 `crypto_quant.data.quality`：检查缺失K线、重复时间戳、OHLC一致性、NaN/Inf、极端跳价和异常成交量；
- 新增 `crypto_quant.realism.market`：生成资金费率、强平缓冲区和回测真实性报告；
- 新增 `crypto_quant.realism.funding`：可选下载 Binance USD-M funding rate 历史数据；
- 新增 `crypto_quant.realism.validation`：Purged / Embargo 时间序列交叉验证；
- 新增前端页面“数据质量与真实性”；
- 新增脚本：`run_data_quality_check.py`、`download_funding_rates.py`、`run_market_realism_report.py`、`run_purged_embargo_cv.py`；
- `run_safe_research_pipeline.py` 已加入数据质量检查、严格CV和真实性报告。

边界：

- V2.4 仍然不是实盘版本；
- 强平价格为研究用途近似估算，不能替代交易所真实公式；
- 资金费率下载失败不影响其他研究流程；
- 前端仍不提供真实下单入口。

## V1.9

V1.9 是订单状态机与部分成交风险控制增强版。

新增内容：

- 新增 `crypto_quant.exchange.order_state_machine`：统一订单生命周期状态机；
- 新增 `crypto_quant.exchange.partial_fill`：部分成交后的仓位对账与保护单数量重算；
- 新增 `crypto_quant.exchange.cancel_recovery`：撤单失败分类与恢复动作建议；
- SQLite 新增 `exchange_order_lifecycle`、`order_state_transitions`、`protection_recalc_plans`、`cancel_failure_events`；
- `ExchangeStateSynchronizer.ingest_event()` 现在会同时写入订单状态机表；
- 新增演示脚本：`demo_order_state_replay.py`、`demo_partial_fill_protection_recalc.py`、`demo_cancel_failure_recovery.py`、`demo_order_lifecycle_audit.py`；
- 新增文档 `docs/ORDER_STATE_MACHINE.md`。

边界：

- V1.9 仍然不是实盘版本；
- 部分成交后的保护单重算默认只生成计划，不自动替换真实订单；
- 撤单失败默认只生成保守恢复建议；
- 对未知订单状态，仍要求先对账再继续。

## V1.0

V1.0 是部署版 Demo 系统，重点不是新增交易策略，而是把已有研究、回测、模拟盘、Demo/Testnet 组件整理为可运行、可检查、可观察、可导出的工程包。

新增内容：

- 新增 `crypto_quant.deploy` 模块；
- 新增部署健康检查 `scripts/deploy_check.py`；
- 新增运行状态面板 `scripts/status_panel.py`；
- 新增守护进程启动器 `scripts/run_demo_service.py`；
- 新增运行诊断包导出 `scripts/export_runtime_bundle.py`；
- 新增日志轮转配置与 `logs/` 目录；
- 新增 Windows 一键启动、状态查看、诊断导出脚本；
- 新增 Windows Task Scheduler 创建脚本；
- 新增 `docs/DEPLOYMENT_DEMO.md` 和 `docs/SAFETY_CHECKLIST.md`；
- 配置文件新增 `deployment`、`logging`、`service` 小节；
- `pyproject.toml` 版本升级到 1.0.0。

边界：

- V1.0 仍然不是实盘版本；
- 默认不连接真实资金账户；
- 默认不真实下单；
- Demo/Testnet 执行动作仍需显式确认；
- Live trading 安全开关仍默认禁止。

## V0.9

- 自动撤单预览；
- 异常告警；
- 恢复动作审计；
- 无人值守 Demo 守护进程雏形。

## V0.8

- 交易所用户数据流事件解析；
- 订单/仓位同步；
- 断线恢复检查。

## V0.7

- 交易所原生止损、止盈、追踪止损保护单意图。

## V0.6

- 本地止损、止盈、追踪止损与熔断风控。

## V0.5

- 策略信号到执行后端的桥接层。

## V0.4

- Binance Futures Demo/Testnet 适配器雏形。

## V0.3

- SQLite 状态化模拟盘。

## V0.2

- Walk-forward 回测、杠杆扫描和交易记录导出。

## V0.1

- 基础数据、特征、模型、回测和模拟盘骨架。

## V1.2.0

Added strategy and model library research layer:

- Added rule strategy registry: buy-and-hold, MA trend, Donchian breakout, volatility squeeze breakout, RSI mean reversion, and regime-filtered trend.
- Added model registry: ExtraTrees, RandomForest, Logistic L2, HistGradientBoosting, and GradientBoosting.
- Added model library diagnostics with split-level metrics, threshold diagnostics, calibration tables, predictions and feature importances.
- Added model-strategy matrix using walk-forward probabilities converted into one common ML trading rule.
- Added V1.2 HTML report builder and documentation.

New scripts:

```bash
python scripts/run_strategy_library_backtest.py
python scripts/run_model_library_diagnostics.py
python scripts/run_model_strategy_matrix.py
python scripts/build_v12_research_report.py
```

## V2.0 - Live safety gate and read-only shadow live mode

Added:

- `src/crypto_quant/live/live_safety.py`
- Live trading safety gate
- File-based kill switch
- Hard drawdown/daily-loss circuit breaker
- Read-only live-account shadow snapshot helper
- Pre-live validation report builder
- SQLite audit tables for live safety checks and shadow snapshots
- Scripts:
  - `scripts/live_gate_check.py`
  - `scripts/kill_switch.py`
  - `scripts/shadow_live_readonly_check.py`
  - `scripts/build_prelive_validation_report.py`
  - `scripts/hard_circuit_check.py`
  - `scripts/v2_live_readiness_report.py`
- Documentation: `docs/LIVE_SAFETY_SHADOW_MODE.md`

Default behavior remains conservative: live order execution is blocked unless multiple independent gates are explicitly changed and validated. V2.0 is still not a real-money automated trading release.
