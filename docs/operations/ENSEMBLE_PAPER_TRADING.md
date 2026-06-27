# V1.5 组合策略模拟盘执行桥接

V1.5 的目标是把 V1.4 生成的 `target_exposure` 接入本地 SQLite 模拟盘账户，使模拟盘从“固定仓位开平仓”升级为“按组合策略动态调仓”。

## 核心概念

`target_exposure` 表示目标名义敞口相对于账户权益的倍数：

- `0.0`：空仓；
- `1.0`：1 倍名义敞口；
- `3.0`：3 倍名义敞口；
- 当前默认上限为 `3.0`，由 `ensemble_paper.max_exposure` 控制。

V1.5 只做本地模拟盘调仓，不接真实下单，也不把组合策略自动提交到交易所 Demo/Testnet。

## 推荐运行流程

```bash
python scripts/download_ohlcv.py
python scripts/build_features.py
python scripts/run_strategy_parameter_search.py
python scripts/paper_init.py --reset
python scripts/paper_ensemble_preview.py
python scripts/paper_ensemble_once.py
python scripts/paper_export_report.py
python scripts/run_paper_ensemble_diagnostics.py
```

历史回放：

```bash
python scripts/paper_ensemble_replay_dataset.py --bars 300 --reset
python scripts/run_paper_ensemble_diagnostics.py
```

长期循环模拟：

```bash
python scripts/paper_ensemble_loop.py --max-iterations 2
```

## 新增输出

```text
reports/ensemble_paper/ensemble_paper_summary.csv
reports/ensemble_paper/ensemble_paper_decisions.csv
reports/ensemble_paper/ensemble_paper_orders.csv
reports/ensemble_paper/ensemble_paper_equity_curve.csv
```

SQLite 新增表：

```text
target_exposure_decisions
```

它记录每根 K 线的目标敞口、当前敞口、调仓动作、delta notional 和订单 JSON。

## 安全边界

V1.5 仍然不是实盘版本。它用于验证：

1. 组合信号能否稳定产生目标敞口；
2. 本地账户能否正确按目标敞口调仓；
3. 频繁小额调仓是否被 `min_rebalance_notional` 过滤；
4. 组合策略的权益曲线是否优于固定仓位模型。

真实交易前仍需完成更严格的 Demo/Testnet 长周期验证、交易所错误码处理、网络中断测试和实盘 kill switch。
