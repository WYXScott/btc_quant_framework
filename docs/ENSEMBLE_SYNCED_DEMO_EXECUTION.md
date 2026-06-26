# V1.7 交易所仓位同步版组合执行说明

V1.7 的目标是把 V1.6 的 `target_exposure -> OrderIntent` 执行桥接进一步安全化：

```text
组合策略 target_exposure
→ 获取 Demo/Testnet 仓位、权益、开放订单快照
→ 用交易所真实 current_qty 构造 TargetPositionPlan
→ 执行前 PreTradeCheck
→ 通过后才允许 Demo/Testnet dry-run/受控提交
```

## 为什么必须这样做

V1.6 可以手动输入 `current_qty` 或读取本地模拟盘仓位，但真实 Demo/Testnet 中可能出现：

- 本地以为无仓，交易所有仓；
- 本地以为有仓，交易所已被止损平仓；
- 保护单成交后，对侧保护单未撤销；
- 交易所有未处理的普通挂单；
- 断线恢复后仓位数量与本地状态不一致。

这些问题在 3–10 倍杠杆下会明显放大风险。因此 V1.7 在执行前引入交易所快照和 PreTradeCheck。

## 新增脚本

### 1. 查看交易所执行状态快照

离线模拟：

```bash
python scripts/demo_exchange_state_snapshot.py --exchange-qty 0.001 --open-order-count 1 --equity 1000
```

连接 Binance Futures Demo/Testnet：

```bash
python scripts/demo_exchange_state_snapshot.py --fetch-private
```

### 2. 同步版组合策略预览

离线模拟：

```bash
python scripts/demo_ensemble_synced_preview.py --exchange-qty 0 --equity 1000 --open-order-count 0
```

连接 Demo/Testnet：

```bash
python scripts/demo_ensemble_synced_preview.py --fetch-private
```

### 3. 同步版组合策略执行预览

默认 dry-run，不下单：

```bash
python scripts/demo_ensemble_synced_execute.py --fetch-private
```

受控提交到 Demo/Testnet：

```bash
python scripts/demo_ensemble_synced_execute.py --fetch-private --execute --confirm I_UNDERSTAND_TESTNET_ORDER
```

如果 PreTradeCheck 只有 warning 而没有 critical，且你确认可以继续：

```bash
python scripts/demo_ensemble_synced_execute.py --fetch-private --execute --allow-warning --confirm I_UNDERSTAND_TESTNET_ORDER
```

## PreTradeCheck 阻断条件

默认会阻断：

- 计划中的 `current_qty` 与交易所快照数量不一致；
- 检测到空头仓位，因为当前系统仍是 long-only；
- 有仓但保护单不足，且当前不是平仓/减仓；
- 存在非保护性开放订单；
- 计划减仓/平仓但交易所快照为空仓；
- 计划加仓但没有生成订单意图。

## 当前边界

V1.7 仍然是 Demo/Testnet 准备版本，不是实盘版本。它解决的是执行前同步和安全门控问题，但还没有完成真实长期无人值守的全部交易所错误码处理、网络重连压力测试、实盘级 kill switch 和多通道告警。
