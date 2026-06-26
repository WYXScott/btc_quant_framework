# V1.0 Demo 部署说明

本项目 V1.0 的目标是：在不接真实资金账户的前提下，把 BTC 低频杠杆策略系统整理为可检查、可启动、可观察、可导出的 Demo 运行包。

## 1. 安装

```bash
cd btc_quant_framework_v1_0
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Linux/macOS 使用：

```bash
source .venv/bin/activate
```

## 2. 首次准备数据与模型

```bash
python scripts/download_ohlcv.py
python scripts/build_features.py
python scripts/train_model.py
python scripts/paper_init.py --reset
```

## 3. 部署前检查

```bash
python scripts/deploy_check.py
```

检查结果会写入：

```text
reports/deployment/health_report.json
```

如果存在 `FAIL`，不要启动长期服务。常见原因包括：Python 版本过低、依赖缺失、误把交易环境配置为 live、数据库不可访问等。

## 4. 查看运行状态

```bash
python scripts/status_panel.py
```

状态快照会写入：

```text
reports/deployment/runtime_status.json
```

## 5. 启动一次 Demo 守护检查

默认只运行一轮：

```bash
python scripts/run_demo_service.py --max-iterations 1
```

如果要离线模拟交易所存在仓位但无保护单的异常状态：

```bash
python scripts/run_demo_service.py --max-iterations 1 --exchange-qty 0.001 --open-order-count 0
```

## 6. Windows 一键脚本

```bat
scripts\windows\windows_start_demo.bat
scripts\windows\windows_status.bat
scripts\windows\windows_export_bundle.bat
```

创建 Windows 计划任务示例：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\create_windows_task.ps1 -IntervalMinutes 15
```

## 7. 导出诊断包

```bash
python scripts/export_runtime_bundle.py --include-logs
```

默认会导出：

- 健康检查结果；
- 运行状态快照；
- 配置文件副本；
- SQLite 各表 CSV；
- 可选日志文件。

除非明确需要，不建议使用 `--include-database` 分享原始 SQLite 数据库。

## 8. 长期 Demo 运行原则

1. 先至少运行本地模拟盘和 Demo/Testnet 一段时间；
2. 每次改策略后重新回测和 walk-forward；
3. 不要把 `broker.environment` 改成 `live`；
4. 不要把 API Key 写入配置文件；
5. 所有真实账户相关操作都必须新增独立安全层后再考虑。
