# V2.2 Pre-live Operator Workflow

V2.2 adds a human review layer before any small real-money launch. It does **not** enable live trading and does **not** submit live orders.

## Core idea

The workflow gathers five inputs into one review package:

1. Manual pre-live checklist
2. API permission/configuration audit
3. Read-only shadow-live vs local paper drift monitor
4. Pre-live validation report and hard-circuit state
5. Manual operator approval record

The default decision is `blocked` until every required item is explicitly approved or waived and all critical checks pass.

## Recommended workflow

```bash
python scripts/prelive_checklist_init.py --reset
python scripts/api_permission_audit.py
python scripts/shadow_drift_check.py
python scripts/shadow_drift_trend_report.py
python scripts/prelive_operator_console.py
python scripts/v22_go_live_review_report.py
```

Open:

```text
reports/prelive_operator/prelive_operator_console.html
```

## Marking checklist items

```bash
python scripts/prelive_checklist_mark.py kill_switch_tested approved --operator Wang --evidence reports/live_safety/live_gate_report.json --notes "Kill switch tested."
```

Allowed statuses:

```text
pending, approved, waived, failed, pass, warn, blocked
```

## Recording manual approval

The expected phrase is configured in `config/config.yaml`:

```yaml
prelive_operator_workflow:
  approval_phrase: I_REVIEWED_AND_ACCEPT_PRELIVE_RISK
```

Example:

```bash
python scripts/prelive_manual_approval.py --operator Wang --decision approve_shadow_only --confirm I_REVIEWED_AND_ACCEPT_PRELIVE_RISK --notes "Continue shadow-live only."
```

`approve_small_live` should only be used after extended Demo/Testnet validation and manual review.

## API permission audit

```bash
python scripts/api_permission_audit.py
```

The audit is conservative and offline. It verifies that:

- live trading is disabled by default;
- credentials are referenced by environment variable names rather than literal secrets;
- shadow-live mode requires read-only credentials and forbids order submission;
- read-only live API environment variables are present when live shadow checks are needed.

## Shadow drift trend

```bash
python scripts/shadow_drift_trend_report.py
```

Outputs:

```text
reports/prelive_operator/shadow_drift_trend.csv
reports/prelive_operator/shadow_drift_trend_summary.json
reports/prelive_operator/shadow_drift_trend.html
```

## Final review report

```bash
python scripts/v22_go_live_review_report.py
```

Output:

```text
reports/prelive_operator/v2_2_go_live_review_report.json
```

A `pass` result means only this:

> eligible for human small-live review.

It does not authorize automatic trading.

## Safety default

The following settings should remain disabled unless there is a final, explicit live launch decision:

```yaml
live_trading:
  master_enable: false

broker:
  safety:
    allow_live_trading: false
```

