# Release Notes — V2.2

## Theme

**Pre-live operator console and manual confirmation workflow.**

V2.2 adds a human review layer for deciding whether the system is ready for a very small real-money trial. It still does not submit live orders.

## New modules

```text
src/crypto_quant/live/prelive_workflow.py
```

Includes:

- `PreLiveWorkflowStore`
- `ApiPermissionAuditor`
- `ShadowDriftTrendAnalyzer`
- `PreLiveReviewBuilder`
- `build_v22_readiness_payload`

## New scripts

```text
scripts/prelive_checklist_init.py
scripts/prelive_checklist_mark.py
scripts/prelive_checklist_export.py
scripts/prelive_manual_approval.py
scripts/api_permission_audit.py
scripts/shadow_drift_trend_report.py
scripts/prelive_operator_console.py
scripts/v22_go_live_review_report.py
```

## New database tables

```text
prelive_checklist_items
prelive_manual_approvals
prelive_review_reports
api_permission_audits
```

## New reports

```text
reports/prelive_operator/prelive_operator_console.html
reports/prelive_operator/prelive_operator_review.json
reports/prelive_operator/prelive_operator_checks.csv
reports/prelive_operator/prelive_checklist_items.csv
reports/prelive_operator/api_permission_audit.json
reports/prelive_operator/shadow_drift_trend.html
reports/prelive_operator/v2_2_go_live_review_report.json
```

## Default decision

The default state remains `blocked`, because:

- live trading master switch is false;
- required manual checklist items are pending;
- no valid manual approval phrase exists;
- extended Demo/Testnet validation may be missing;
- shadow-live checks may be offline unless read-only API keys are configured.

This is intentional.

