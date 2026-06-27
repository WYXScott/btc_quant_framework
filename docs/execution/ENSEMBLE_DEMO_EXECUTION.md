# V1.6 组合策略 Demo/Testnet 执行预览层

V1.6 将 V1.4/V1.5 的 `target_exposure` 转换为交易所中性的 `OrderIntent`，用于 Binance Futures Demo/Testnet 的离线预览或受控测试提交。

## 核心概念

`target_exposure` 表示目标名义敞口与账户权益的比例：

- `0.0`：空仓；
- `1.0`：1 倍名义敞口；
- `3.0`：3 倍名义敞口。

V1.6 会比较当前仓位和目标仓位，生成以下动作之一：

- `hold_flat`
- `hold`
- `increase`
- `reduce`
- `close`
- `blocked`

## 重要安全设计

默认仍然不会真实下单。即使是 Demo/Testnet，也需要显式添加 `--execute` 和确认短语。

默认配置还会使用：

```yaml
broker.safety.max_order_notional_usdt: 50.0
ensemble_demo_execution.apply_demo_order_cap: true
```

这意味着每一笔 Demo/Testnet 测试订单默认被限制在很小的名义金额内。

## 手动目标仓位预览

```bash
python scripts/demo_target_position_preview.py --price 50000 --equity 1000 --current-qty 0 --target-exposure 1.0
```

## 最新组合策略目标仓位预览

先运行：

```bash
python scripts/download_ohlcv.py
python scripts/build_features.py
python scripts/run_strategy_parameter_search.py
```

然后运行：

```bash
python scripts/demo_ensemble_target_preview.py --source local_paper
```

## 提交到 Demo/Testnet

仅在配置好测试网 API Key 后使用：

```bash
set BINANCE_TESTNET_API_KEY=your_key
set BINANCE_TESTNET_API_SECRET=your_secret

python scripts/demo_ensemble_target_execute.py --execute --confirm I_UNDERSTAND_TESTNET_ORDER
```

## 原生保护单

可以用 `--with-protection` 同时生成 reduce-only 止损/止盈保护单意图：

```bash
python scripts/demo_ensemble_target_preview.py --with-protection
```

建议先只预览，不要直接提交保护单，直到基础 Demo 开平仓流程已经稳定。
