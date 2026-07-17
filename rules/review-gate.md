# Review Gate

Review Gate is a structured review for core rules, cross-layer changes, and high-risk modifications.

It is not required for every small change. Run it when Risk Gate or Change Policy triggers it.

## When To Run
Run or strongly recommend Review Gate for:
- AGENTS.md / context / workflows / rules / skills changes
- cross-layer full-stack changes
- permission, data, security, payment, or release changes
- large refactors or architecture changes
- release-critical changes
- merging results from multiple agents

## Review Checklist

### 1. Goal Fit
- Does the change solve the user's explicit request?
- Did it introduce unrequested features, abstractions, or process?
- Is the scope complete without unnecessary expansion?

### 2. Boundary
- Does it preserve rule / skill / gate responsibility boundaries?
- Does it preserve context / workflow / rule / skill / runtime responsibility boundaries?
- Does any skill become too broad?
- Does any workflow become a skill, or any skill become a workflow?
- Does it mistake stack context for skill selection?
- Did it avoid unnecessary stack-specific skills?

### 3. Consistency
- Are terms consistent?
- Are stale positioning, stale flows, or stale rules removed?
- Do README / AGENTS / context / workflows / rules / skills conflict?
- Is the Rules Loading Order still sensible?
- Did Agent OS English-language policy stay inside model-facing Agent OS files instead of leaking into user project artifacts?
- Did durable project execution documents use `docs/agent-os/` instead of `.agent-os/`?

### 4. Documentation Gate
- Were user-facing README/docs updated when setup, usage, behavior, configuration, API contracts, deployment, troubleshooting, or validation changed?
- Were durable plans, task breakdowns, decisions, reviews, and verification records written under `docs/agent-os/` when needed?
- For L2+ or complex work, was documentation writing delegated to a Documentation Recorder sub-agent when available, with the main agent reviewing the resulting diff?
- If documentation writing was not delegated, was the reason explicit?
- Were Agent OS README, AGENTS, context, workflows, rules, tools, installer bootstrap, and tests updated when Agent OS behavior changed?
- Did the final response state either what documentation changed or why no documentation update was needed?
- Did the change avoid treating memory or Runtime records as substitutes for human-readable documentation?

### 5. Evidence And Validation
- Are conclusions based on files, code, logs, tests, or user context?
- Is validation method and result stated?
- Does validation cover the core path?
- Are unable-to-validate, partial pass, and remaining risks marked?
- For performance work, is there a baseline, target, or substitute validation?

### 6. Evolution And Memory
- Is project memory needed?
- Is this only a candidate skill or candidate rule?
- Does it satisfy Trigger / Count / Validation / Scope / Boundary?
- Did it avoid recording one-off operations, unverified preferences, or ordinary success paths?

### 7. Executability
- Can the new rule answer when it triggers, how to execute, and how to validate?
- Can the new workflow answer when it triggers, what user-visible output is required, how to execute, and how to validate?
- Is it concise enough?
- Does it require guessing to follow?
- Could it cause infinite loops, unlimited skill creation, or memory bloat?

### 8. Risk And Rollback
- Was impact scope identified?
- Is rollback needed?
- Is worktree isolation needed?
- If review fails, is the next action fix, rollback, or user confirmation?

## Review Result

### Pass
Use when:
- the core goal is met
- no clear boundary conflict exists
- validation evidence is enough
- remaining risk is stated

Output:
- Review result: pass
- Review scope
- Validation evidence
- Remaining risk

### Pass With Notes
Use when:
- the core goal is met
- non-blocking risks or follow-up observations remain

Output:
- Review result: pass with notes
- Notes
- Why they do not block delivery
- Follow-up recommendation

### Fail
Use when:
- core goal is not met
- core validation fails
- rule boundaries conflict
- changes introduce non-executable rules
- high-risk changes lack validation or rollback

Handling:
- Record the failure reason.
- Stop expanding changes.
- Fix the non-compliant item and review again.
- Recover to a stable state or ask the user when needed.

## What Not To Do
- Do not run Review Gate for every tiny change.
- Do not check formatting only; review semantics and boundaries.
- Do not claim completion after a failed review.
- Do not introduce new standards during review without evidence.
- Do not use Review Gate as a substitute for Evidence Gate or Validation Gate.
