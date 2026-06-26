# V2.0 Live Safety Gate and Shadow Live Mode

V2.0 adds the safety layer that should exist before any real-money trading is considered. It is intentionally conservative: **real order execution remains blocked by default**.

## What V2.0 adds

- Live-trading master gate
- File-based kill switch
- Hard daily-loss and total-drawdown circuit breaker
- Read-only live-account shadow mode
- Pre-live validation report
- SQLite audit tables for safety checks and shadow snapshots

## Default behavior

The default config keeps all live trading blocked:

```yaml
live_trading:
  master_enable: false
broker:
  environment: testnet
  safety:
    allow_live_trading: false
```

This is intentional. V2.0 is for verification, not for live automatic execution.

## Basic commands

Evaluate the live safety gate:

```bash
python scripts/live_gate_check.py
```

Trigger the kill switch:

```bash
python scripts/kill_switch.py --trigger --reason "manual emergency stop"
```

Clear the kill switch after investigation:

```bash
python scripts/kill_switch.py --clear --reason "issue resolved"
```

Build a pre-live validation report:

```bash
python scripts/build_prelive_validation_report.py
```

Run a read-only shadow live preview without network access:

```bash
python scripts/shadow_live_readonly_check.py
```

Query real live read-only account endpoints only after setting read-only API keys:

```bash
set BINANCE_LIVE_READONLY_API_KEY=your_readonly_key
set BINANCE_LIVE_READONLY_API_SECRET=your_readonly_secret
python scripts/shadow_live_readonly_check.py --fetch-private
```

Use **read-only API keys only**. Do not use an API key with trading permission for shadow mode.

## Pre-live validation philosophy

Before live trading, the system should demonstrate at least:

1. Stable simulated/paper execution.
2. Stable Demo/Testnet execution.
3. No unresolved unknown order states.
4. No active kill switch.
5. No hard-circuit breach.
6. No missing required research and deployment reports.
7. At least 30 days of Demo/shadow observation unless explicitly overridden.

## Hard circuit breaker

The hard circuit breaker reads the local equity curve and blocks live gate status if:

- daily loss exceeds `live_trading.max_daily_loss_fraction`; or
- total drawdown from peak exceeds `live_trading.max_total_drawdown_fraction`.

Run:

```bash
python scripts/hard_circuit_check.py
```

## Readiness report

Generate a consolidated V2.0 readiness report:

```bash
python scripts/v2_live_readiness_report.py
```

Output:

```text
reports/live_safety/v2_live_readiness_report.json
```

## Important limitation

V2.0 does **not** make the system a live trading bot. It creates the safety gate and shadow-readiness layer that must be passed before a future live adapter can be considered.
