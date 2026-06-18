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

## Skill Source Rule

After workflow selection, if a skill is needed and the user project contains `.codex/skills/<skill>/SKILL.md`, read that project-local skill file first.

Use global user-level skills only when:

- the project-local skill is missing
- the user explicitly asks for a global skill
- the runtime environment exposes an external system skill that is not part of the project-local Agent OS

Do not silently prefer global Codex home skill files such as `$CODEX_HOME/skills/...` or `~/.codex/skills/...` over project-local `.codex/skills/...` files.
