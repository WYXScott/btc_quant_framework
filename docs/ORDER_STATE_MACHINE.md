# V1.9 订单状态机与部分成交处理说明

V1.9 的目标是把交易所执行从“提交成功/失败”升级为完整生命周期管理。

## 1. 核心状态

订单状态机将交易所状态归一化为：

```text
created
submitted
new
partially_filled
filled
cancel_requested
canceled
expired
rejected
cancel_failed
unknown
```

其中：

- `partially_filled`：最需要关注，因为真实仓位已经变化，但保护单数量可能还没有同步；
- `unknown`：通常来自网络异常、请求超时或交易所状态不确定，必须先对账；
- `filled / canceled / expired / rejected`：终态，但如果后续收到非终态事件，会写入告警式 transition。

## 2. 新增 SQLite 表

```text
exchange_order_lifecycle
order_state_transitions
protection_recalc_plans
cancel_failure_events
```

用途：

| 表 | 作用 |
|---|---|
| `exchange_order_lifecycle` | 每个订单的最新生命周期状态 |
| `order_state_transitions` | 每次状态变化的审计流水 |
| `protection_recalc_plans` | 部分成交/仓位变化后的保护单重算计划 |
| `cancel_failure_events` | 撤单失败后的分类与恢复动作 |

## 3. 部分成交后的安全逻辑

当订单进入 `partially_filled`：

```text
1. 记录订单生命周期状态；
2. 要求交易所仓位对账；
3. 检查当前持仓数量与 reduce-only 保护单数量是否匹配；
4. 如果保护单不足，生成 add/replace protection 的计划；
5. 不自动真实下单，仍需显式 Demo/Testnet 确认。
```

## 4. 撤单失败后的安全逻辑

撤单失败被分为：

```text
order_not_found
network_error
rate_limited
exchange_not_available
request_timeout
temporary_exchange_error
invalid_order
unknown_exchange_error
```

推荐动作：

- `order_not_found`：先查开放订单和历史订单，不要盲目重新撤单；
- 临时错误：允许重试撤单，但必须阻断新开仓直到确认；
- 非重试错误：停止执行并人工对账。

## 5. 推荐测试命令

```bash
python scripts/demo_order_state_replay.py
python scripts/demo_partial_fill_protection_recalc.py --position-qty 0.004 --entry-price 50000 --existing-protection-qty 0
python scripts/demo_cancel_failure_recovery.py --category network_error
python scripts/demo_order_lifecycle_audit.py
```

## 6. 实盘前要求

V1.9 仍然不是实盘版本。进入真实资金前至少还需要：

```text
长期 Demo/Testnet 成交回报验证
部分成交后保护单真实替换测试
撤单失败重试与对账压力测试
API 限频下的守护进程稳定性测试
真实账户权限隔离与 kill switch
```
