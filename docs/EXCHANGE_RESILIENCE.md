# V1.8 交易所错误处理、重试与幂等订单层

V1.8 的目标不是提高收益，而是降低 Demo/Testnet 和未来实盘执行中的工程风险。重点处理以下问题：

- 网络超时、连接失败、交易所临时不可用；
- API 限频；
- 订单提交后返回状态不确定；
- 重复运行脚本导致重复下单；
- 参数错误、余额不足、精度错误等不可重试错误；
- 部分成交、撤单失败后必须先对账再继续。

## 核心模块

```text
src/crypto_quant/exchange/errors.py
src/crypto_quant/exchange/retry.py
src/crypto_quant/exchange/idempotency.py
src/crypto_quant/exchange/resilient_executor.py
```

## 关键思想

### 1. 错误分类

所有异常会被归类为：

```text
network_error
rate_limited
request_timeout
exchange_not_available
temporary_exchange_error
insufficient_funds
invalid_order
precision_error
order_not_found
safety_block
unknown_exchange_error
```

只有临时性错误会进入重试；资金不足、参数错误、安全层阻断不会重试。

### 2. 幂等订单

每个订单会基于 `OrderIntent + time_bucket` 生成稳定 fingerprint，再生成确定性的 `client_order_id`。

同一个 `client_order_id` 已经处于：

```text
pending / submitted / success / unknown_order_state
```

时，再次提交会被本地 ledger 阻断，避免重复下单。

### 3. 未知订单状态

如果网络错误发生在提交阶段，系统不假设订单失败，而是标记为：

```text
unknown_order_state
```

此时必须先进行交易所仓位和订单对账，再决定是否重新提交。

## 推荐脚本

离线测试重试策略：

```bash
python scripts/demo_retry_policy_test.py
```

查看幂等 key 生成：

```bash
python scripts/demo_idempotency_check.py --reserve
```

手动订单 dry-run：

```bash
python scripts/demo_resilient_order_preview.py --side buy --price 50000 --notional 20
```

组合策略同步执行 dry-run：

```bash
python scripts/demo_ensemble_resilient_execute.py --exchange-qty 0 --open-order-count 0
```

提交到 Demo/Testnet 仍然必须显式确认：

```bash
python scripts/demo_resilient_order_preview.py --execute --confirm I_UNDERSTAND_TESTNET_ORDER
```

## 实盘前约束

V1.8 仍然不是实盘版本。进入任何真实资金环境前，至少还需要：

1. 长周期 Demo/Testnet 运行；
2. 真实错误码样本回放；
3. 部分成交与撤单失败专项测试；
4. API 权限隔离；
5. kill switch；
6. 资金规模逐级放大。
