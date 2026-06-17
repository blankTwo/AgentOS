# Workflow Selection

Select the workflow after Context Layer classification.

## Decision Order

1. If the task changes Agent OS itself, use Agent OS Evolution Workflow.
2. If behavior differs across platform, client, role, environment, or tenant, use Cross-Platform Issue Workflow.
3. If root cause is unclear or behavior is abnormal, use Bug Diagnosis Workflow.
4. If API/data/auth/quota/billing/schema/compatibility is affected, use API Contract Change Workflow.
5. If a capability is new, missing, partial, broken-chain, or unconfirmed, use Feature Implementation Workflow.
6. If all direct-execution criteria are met, use Simple Change Workflow.

## Direct Execution Criteria

Direct execution is allowed only when:

- goal is explicit
- impact is local
- behavior is already understood
- validation is simple
- no business contract, data, auth, quota, payment, state flow, cross-platform, cross-service, production, or unclear root cause risk exists

## User-Visible Output Rule

Every workflow starts with user-visible intent.

The agent must not say:

- "the plan is ready"
- "the plan is set"
- "policy is decided"
- "I will start implementing"

unless the concrete intent or plan has already been shown.

