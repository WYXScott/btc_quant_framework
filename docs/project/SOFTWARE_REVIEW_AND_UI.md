# BTC Quant Framework V2.3 软件包回顾与前端说明

## 1. 当前定位

V2.3 保持当前安全边界：

- 只做 BTC/USDT 低频量化研究、回测、模拟盘和 Demo/Testnet 安全验证；
- 暂时不开放真实实盘自动交易；
- 真实账户相关功能仅保留只读影子检查、安全总闸、人工审核和 Kill Switch；
- Streamlit 前端不会提供真实下单按钮。

## 2. 功能完整性回顾

| 模块 | 当前状态 | 说明 |
|---|---|---|
| 数据下载 | 已具备 | CCXT 获取公开 OHLCV，默认 BTC/USDT:USDT 4h |
| 数据存储 | 已具备 | Parquet 存储 raw/features/dataset |
| 特征工程 | 已具备 | 收益率、趋势、波动率、成交量、K线结构、RSI |
| 标签构造 | 已具备 | 默认预测未来 6 根 4h K线，即约 24h 方向 |
| 模型训练 | 已具备 | ExtraTrees 默认模型，可扩展 RF、Logistic、HGB、GBDT |
| 模型诊断 | 已具备 | ROC-AUC、Brier、log loss、校准、阈值诊断、特征重要性 |
| 规则策略 | 已具备 | 长持、趋势、突破、波动压缩、RSI均值回归、状态过滤 |
| 组合策略 | 已具备 | 多策略加权投票、target_exposure、动态仓位 |
| 回测 | 已具备 | 固定杠杆与动态敞口回测 |
| 模拟盘 | 已具备 | SQLite 状态化模拟盘、组合策略动态调仓 |
| 风控 | 已具备 | 止损、止盈、追踪止损、连续亏损暂停、日内亏损熔断 |
| Demo/Testnet | 已具备但默认关闭 | 订单意图、保护单、仓位同步、幂等、状态机、恢复动作 |
| 实盘 | 暂不开放 | 仅做只读影子、安全总闸、Kill Switch、人工 checklist |
| 前端 | V2.3 新增 | Streamlit 研究控制台 |

## 3. 新增前端

启动方式：

```bash
python scripts/run_dashboard.py
```

或者：

```bash
streamlit run frontend/app.py
```

前端包括：

1. **总览**：核心文件、数据集、模型、模拟盘数据库状态；
2. **数据与模型**：查看数据摘要、训练模型、运行模型诊断；
3. **策略研究**：查看策略库、参数搜索、组合策略输出；
4. **模拟盘**：查看 SQLite 状态、权益曲线、组合模拟盘操作；
5. **风控与只读影子**：查看 Live Gate、硬熔断、影子漂移、pre-live 审核；
6. **一键流程**：运行安全的研究流程；
7. **软件审查**：查看功能覆盖与改进建议。

前端按钮受 `config/config.yaml` 中 `ui.allowed_button_scripts` 限制，不允许执行真实实盘脚本。

## 4. 模型是否可以训练？

可以。训练链路如下：

```bash
python scripts/download_ohlcv.py
python scripts/build_features.py
python scripts/train_model.py
python scripts/model_train_smoke.py  # 可选：离线验证训练链路
python scripts/run_model_diagnostics.py
```

默认模型为 `extra_trees`，配置位于：

```yaml
model:
  model_path: models/btc_direction_model.joblib
  feature_list_path: models/btc_feature_columns.txt
  train_end: '2023-12-31'
  valid_end: '2024-12-31'
```

模型训练需要先存在：

```text
data/processed/BTCUSDT_4h_dataset.parquet
```

如果数据集不存在，先运行 `download_ohlcv.py` 和 `build_features.py`。

## 5. 当前最需要改进的地方

### 高优先级

1. **数据质量检查**：补充缺失 K 线、重复时间戳、异常跳价、交易所维护时段检测；
2. **回测真实性**：加入资金费率、合约保证金模式、真实强平公式、手续费等级；
3. **模型验证**：加入 Purged/Embargo 时间序列交叉验证，降低标签重叠导致的过拟合；
4. **信号可信度**：模型概率需要校准后再用于仓位控制；
5. **模拟盘长期运行**：至少连续运行 30 天以上，再考虑任何小资金真实验证。

### 中优先级

1. 加入 LightGBM/XGBoost 可选模型；
2. 加入 TCN/LSTM 等序列模型实验，但不作为初期主线；
3. 增加更细化的资金管理，例如 Kelly 上限、波动率目标与亏损降杠杆联动；
4. 将报告整合为更完整的研究档案。

## 6. 推荐使用路线

```text
公开行情下载
→ 特征与标签构建
→ 模型训练和诊断
→ 策略库回测
→ 参数稳健性搜索
→ 组合策略回测
→ 本地模拟盘回放
→ 只读影子监控
→ 人工审核报告
```

在当前阶段，不建议开启任何真实自动交易。
