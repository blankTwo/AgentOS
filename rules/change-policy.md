# Change Policy

## Allowed High-Frequency Updates
- Project memory
- SQLite memory records
- Validation notes
- Small documentation clarifications

## Allowed With Reason
- Skills, when reuse value and trigger boundaries are clear.
- Rules, when the behavior is stable and broadly applicable.
- AGENTS.md, only when the user explicitly asks for Agent OS architecture, gate definitions, control-flow, or routing changes.
- Context files, when the user explicitly asks to improve task situation classification or context modeling.
- Workflow files, when the user explicitly asks to improve operating sequence, user-visible output, workflow routing, or agent behavior.

### AGENTS.md Exception
When the user explicitly requests these changes, AGENTS.md may be modified:
- Agent OS architecture changes.
- Gate definition or execution-flow changes.
- Control-rule revisions.
- Project / Stack / Task Layer routing changes.
- Context Layer or Workflow Layer integration.

Before changing AGENTS.md, state:
- reason for change
- impact scope
- validation method

After changing AGENTS.md:
- run Review Gate or an equivalent consistency check
- check README / rules / skills for duplicated responsibility or stale rules
- check context / workflows / runtime docs for duplicated responsibility or stale flows
- state whether memory or evolution records are needed

## Promotion Standard
Experience may be promoted only when it is:
- verified
- reusable
- bounded
- not one-off
- not strongly business-coupled

## Skill / Rule Maintenance
- Before changing a skill, state its reuse value and trigger scenario.
- Before changing a rule, state why it is stable enough.
- Do not write one-off cases, temporary workarounds, or unverified preferences into skills or rules.
- Prefer improving existing task-layer skills instead of creating stack-specific skills.
- After modification, check that descriptions remain accurate and triggers are not too broad.
- New stack-specific skills require cross-project evidence, clear boundaries, and proof that task-layer skill plus project pattern is insufficient.

## Review Gate
Run `rules/review-gate.md` for:
- AGENTS.md / context / workflows / rules / skills changes
- large architecture or cross-layer changes
- permission, data, security, payment, or release risk

## Anti-Drift
- Do not break clear workflows for the sake of being "more generic".
- Do not make rules less executable for the sake of being "more intelligent".
- Rules must be concise, explicit, and actionable.
- A new rule must answer: when it triggers, how to execute it, and how to validate it.
- A workflow must answer: when to use it, what user-visible output is required, what evidence is required, how to execute, and how to validate.
