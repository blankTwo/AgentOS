# Agent Runtime Tools

Agent Runtime commands provide explicit operating-state controls for Agent OS. They use the same SQLite database as memory tools, but they are not memory commands.

Use `scripts/agent-runtime.py` for intent state, execution gates, feedback/drift loops, goals, tasks, observations, capability graph, policy decisions, verification planning, recovery planning, next-action selection, and controlled improvement reviews.

Runtime records do not replace user-visible workflow output. If a workflow requires intent, diagnostic plan, structured plan, recovery, or review decision, show it in the conversation before editing files.

Runtime records do not replace durable project execution documents. If a task needs a saved implementation plan, task breakdown, decision record, review, or verification report, write it to the user project's `docs/agent-os/` directory, not to `.agent-os/`.

Runtime records do not replace Documentation Gate. If runtime work changes commands, setup, usage, contracts, validation, troubleshooting, or Agent OS behavior, update the relevant README/docs/tools/installer bootstrap/tests or state why documentation did not need changes.

Documentation and memory writing should not block the main agent's critical path on complex work. The main agent decides what documentation or memory is required, packages confirmed facts, and verifies the result. Use `documentation-recorder` and `memory-recorder` sub-agent roles to perform the actual writing/recording when sub-agents are available.

---

## Commands

```bash
python scripts/agent-runtime.py --help
```

Available runtime commands:
- `runtime-detect-context`
- `runtime-compile-mission`
- `runtime-detect-intent`
- `runtime-tool-registry`
- `runtime-validate-action`
- `runtime-propose-action`
- `runtime-execution-gate`
- `runtime-approve-action`
- `runtime-record-feedback`
- `runtime-detect-drift`
- `runtime-reanchor`
- `runtime-revise-plan`
- `runtime-publish-event`
- `runtime-poll-events`
- `runtime-ack-event`
- `runtime-schedule`
- `runtime-scheduler-next`
- `runtime-schedule-complete`
- `runtime-request-resource`
- `runtime-release-resource`
- `runtime-quality-score`
- `runtime-benchmark`
- `runtime-self-audit`
- `runtime-compatibility-matrix`
- `runtime-governance-proposal`
- `runtime-run`
- `runtime-select-skills`
- `runtime-plan-tasks`
- `runtime-complete-task`
- `runtime-detect-validation-profile`
- `runtime-run-verification`
- `runtime-create-checkpoint`
- `runtime-mark-recovery`
- `runtime-final-check`
- `runtime-review-improvements`
- `runtime-report`
- `runtime-record`
- `runtime-list`
- `runtime-summary`
- `runtime-scan-capability`
- `runtime-evaluate-policy`
- `runtime-next`
- `runtime-plan-verification`
- `runtime-plan-recovery`

---

## Event Bus, Scheduler, And Resources

Use these when the runtime needs an explicit event loop instead of a flat command sequence.

```bash
python scripts/agent-runtime.py runtime-publish-event \
  --project my-project \
  --topic scheduler.tick \
  --subscriber scheduler \
  --event-type KernelStep \
  --summary "Scheduler should inspect queue."

python scripts/agent-runtime.py runtime-poll-events \
  --project my-project \
  --subscriber scheduler \
  --deliver

python scripts/agent-runtime.py runtime-ack-event \
  --project my-project \
  --id event-msg-1 \
  --ok
```

```bash
python scripts/agent-runtime.py runtime-request-resource \
  --project my-project \
  --resource-type workspace \
  --resource-key repo \
  --reason "Protect workspace mutation window."

python scripts/agent-runtime.py runtime-schedule \
  --project my-project \
  --action-type verify \
  --assigned-role verifier \
  --required-resources workspace:repo \
  --priority 10

python scripts/agent-runtime.py runtime-scheduler-next \
  --project my-project \
  --advance

python scripts/agent-runtime.py runtime-release-resource \
  --project my-project \
  --id lease-1
```

Open event messages, open schedule items, and unresolved resource leases are checked by `runtime-final-check`.

---

## Quality Score And Self-Audit

Use these before final handoff on L2+ work or Agent OS evolution.

```bash
python scripts/agent-runtime.py runtime-quality-score \
  --project my-project \
  --goal-id goal-1 \
  --record \
  --min-score 70

python scripts/agent-runtime.py runtime-benchmark \
  --project my-project \
  --goal-id goal-1 \
  --name dashboard-render \
  --metric duration-ms \
  --baseline-value 100 \
  --current-value 92 \
  --direction lower-is-better \
  --unit ms \
  --record

python scripts/agent-runtime.py runtime-self-audit \
  --project my-project \
  --goal-id goal-1 \
  --record
```

`runtime-final-check` treats low recorded quality scores, failed benchmarks, and open self-audit findings as completion risks.

---

## Compatibility And Governance

Use the compatibility matrix when supporting multiple models or IDE hosts.

```bash
python scripts/agent-runtime.py runtime-compatibility-matrix \
  --project my-project \
  --provider openai qwen mock \
  --host-type codex claude qwen vscode
```

Use governance proposals for controlled Agent OS evolution. This records review evidence only; it never edits rules or skills by itself.

```bash
python scripts/agent-runtime.py runtime-governance-proposal \
  --project my-project \
  --name intent-drift-policy \
  --source-type rule \
  --trigger "Repeated diagnosis-to-mutation drift" \
  --evidence "blocked action proposals and drift records" \
  --validation "runtime-final-check blocks open drift" \
  --scope "Mutation Authorization Gate" \
  --boundary "Do not auto-promote without human review" \
  --ready-for-review
```

---

## Run The Full Agent Loop

Use `runtime-run` for L2+ work when the agent needs one command to prepare the full operating loop.

```bash
python scripts/agent-runtime.py runtime-run \
  --project my-project \
  --request "Implement phone login" \
  --capability phone-login \
  --term phone login auth \
  --files src/pages/Login.tsx server/auth.ts \
  --signal auth \
  --use-memory \
  --record
```

It outputs and optionally records:
- context detection
- capability state
- policy decisions
- runtime task queue
- skill recommendations
- verification plan
- recovery plan

---

## Detect Context

```bash
python scripts/agent-runtime.py runtime-detect-context \
  --request "Implement phone login" \
  --files src/pages/Login.tsx server/auth.ts \
  --record
```

This produces project, stack, task layers, task scale, intent, mutation authorization, confidence, and evidence.

---

## Mission IR, Intent, And Execution Gate

Compile natural language into Locked Mission IR before runtime execution:

```bash
python scripts/agent-runtime.py runtime-compile-mission \
  --project my-project \
  --request "Investigate why original check returns 0 on first run" \
  --files server/original-check.ts
```

By default this uses builtin deterministic rules. To use an OpenAI-compatible LLM Semantic Compiler:

```bash
python scripts/agent-runtime.py runtime-compile-mission \
  --project my-project \
  --provider custom \
  --base-url https://example.com/v1 \
  --api-key "$AGENT_OS_LLM_API_KEY" \
  --model gemini-3-flash \
  --request "Investigate why original check returns 0 on first run"
```

The LLM produces Draft Mission IR only. Runtime then strips Markdown code fences, parses JSON, validates and normalizes fields, tightens permissions, and returns Locked Mission IR. If the LLM fails, times out, returns bad JSON, or expands a read-only request into mutation, runtime falls back to builtin rules unless `--no-fallback` is used.

Read-only diagnosis should lock to:

```json
{
  "mission": { "type": "diagnose", "mode": "readonly" },
  "constraints": {
    "readonly": true,
    "allowWrite": false,
    "allowCommit": false,
    "allowDeploy": false,
    "requireApprovalBeforeMutation": true
  }
}
```

Use this when a request may be diagnosis-only, ambiguous, or risky. Read-only diagnosis must not mutate files until the user approves a fix.

```bash
python scripts/agent-runtime.py runtime-detect-intent \
  --project my-project \
  --intent-id intent-original-check \
  --request "Investigate why original check returns 0 on first run" \
  --files server/original-check.ts \
  --record
```

Check a proposed mutation before execution:

```bash
python scripts/agent-runtime.py runtime-validate-action \
  --project my-project \
  --intent-id intent-original-check \
  --action-type patch \
  --tool patch.apply \
  --target-paths server/original-check.ts \
  --validation-plan "npm test"
```

Record a proposal and let the gate decide whether it is allowed, blocked, or needs approval:

```bash
python scripts/agent-runtime.py runtime-propose-action \
  --project my-project \
  --intent-id intent-original-check \
  --id action-original-check-fix \
  --action-type patch \
  --tool patch.apply \
  --target-paths server/original-check.ts \
  --reason "candidate root-cause fix" \
  --validation-plan "npm test"
```

If the user explicitly confirms the fix, record approval and re-run the gate:

```bash
python scripts/agent-runtime.py runtime-approve-action \
  --project my-project \
  --intent-id intent-original-check \
  --proposal-id action-original-check-fix \
  --approved-text "fix it" \
  --approved-scope server/original-check.ts

python scripts/agent-runtime.py runtime-execution-gate \
  --project my-project \
  --proposal-id action-original-check-fix \
  --user-approved \
  --validation-plan "npm test"
```

When a tool call supplies intent/action context, `runtime-run-tool` applies the same gate before running. Blocked or approval-required actions are recorded and do not execute.

---

## Feedback, Drift, And Re-anchor

Use feedback events when validation, user feedback, or new evidence changes the current plan.

```bash
python scripts/agent-runtime.py runtime-record-feedback \
  --project my-project \
  --intent-id intent-original-check \
  --proposal-id action-original-check-fix \
  --evidence-delta new-evidence \
  --summary "Upstream result timing contradicts the initial hypothesis."
```

Detect drift when execution no longer matches the original intent, approved scope, tool class, confidence, or plan:

```bash
python scripts/agent-runtime.py runtime-detect-drift \
  --project my-project \
  --intent-id intent-original-check \
  --proposal-id action-original-check-fix \
  --record
```

If drift exists, re-anchor with the user and record the revised plan:

```bash
python scripts/agent-runtime.py runtime-reanchor \
  --project my-project \
  --intent-id intent-original-check

python scripts/agent-runtime.py runtime-revise-plan \
  --project my-project \
  --intent-id intent-original-check \
  --steps "1. Re-anchor. 2. Collect missing evidence. 3. Execute only after approval." \
  --validation "No write action before gate approval." \
  --status active
```

---

## Record Runtime State

```bash
python scripts/agent-runtime.py runtime-record \
  --kind goal \
  --project my-project \
  --id goal-phone-login \
  --objective "Implement phone login" \
  --success-criteria "Phone login works end to end with validation evidence." \
  --current-phase planning
```

```bash
python scripts/agent-runtime.py runtime-record \
  --kind task \
  --project my-project \
  --id task-discover-phone-login \
  --goal-id goal-phone-login \
  --title "Discover current phone login capability chain" \
  --task-layer Integration \
  --scale L3 \
  --assigned-role planner
```

Runtime kinds:
- `goal`
- `task`
- `observation`
- `capability`
- `policy`
- `verification`
- `recovery`
- `improvement`
- `intent`
- `action-proposal`
- `feedback`
- `drift`
- `approval`
- `plan-version`

---

## Scan Capability State

Use this during Capability Discovery Gate. It scans implementation files and classifies frontend/API/backend/data/verification evidence.

```bash
python scripts/agent-runtime.py runtime-scan-capability \
  --project my-project \
  --goal-id goal-phone-login \
  --name phone-login \
  --term phone login auth \
  --roots src server \
  --require-verification \
  --record
```

Capability status values:
- `complete`
- `partial`
- `broken-chain`
- `absent`
- `unconfirmed`

Documentation-only hits must not prove a capability exists. If scanner output conflicts with manual code inspection, manual evidence wins.

Use `--use-memory` to include SQLite memory hits as context. Memory hits can raise `absent` to `unconfirmed`, but they must not prove a current implementation exists without code evidence.

---

## Evaluate Policy Decisions

Use this during Risk Gate and Planning Gate.

```bash
python scripts/agent-runtime.py runtime-evaluate-policy \
  --project my-project \
  --goal-id goal-phone-login \
  --task-id task-discover-phone-login \
  --scale L3 \
  --capability-status broken-chain \
  --task-layer Integration API \
  --signal auth \
  --record
```

Policy decision types:
- `plan`
- `tdd`
- `review`
- `rollback`
- `worktree`
- `performance`
- `execution-mode`

Policy records do not replace user-visible gate output. If policy changes execution mode, TDD, review, rollback, worktree, or performance handling, state that decision in the visible intent or plan before implementation.

---

## Plan Tasks

```bash
python scripts/agent-runtime.py runtime-plan-tasks \
  --project my-project \
  --goal-id goal-phone-login \
  --request "Implement phone login" \
  --scale L3 \
  --capability-status broken-chain \
  --record
```

This creates planner, executor, verifier, and reviewer task records with order indexes.

These task records are not the user-visible plan. After running this command, summarize the applicable workflow plan or intent to the user before implementation.

---

## Select Skills

```bash
python scripts/agent-runtime.py runtime-select-skills \
  --project my-project \
  --request "Implement phone login" \
  --stack "React Node" \
  --record
```

The output is a recommendation list with rationale. It does not auto-load or execute skills.
Recommendations are derived from task layers and real `skills/*/SKILL.md` metadata.

---

## Select Next Runtime Action

Use this for long-running or multi-turn tasks. It reads active goals, pending tasks, capability state, and failed verification.

```bash
python scripts/agent-runtime.py runtime-next \
  --project my-project \
  --goal-id goal-phone-login \
  --advance
```

Use `--advance` only when moving the selected pending task to `in_progress` is intended.

---

## Plan Verification

Use this before implementation or before final validation.

```bash
python scripts/agent-runtime.py runtime-plan-verification \
  --project my-project \
  --goal-id goal-phone-login \
  --task-id task-discover-phone-login \
  --task-layer Integration API \
  --scale L3 \
  --files src/pages/Login.tsx src/api/auth.ts server/auth.ts \
  --record
```

---

## Run Verification

Detect a stack-specific validation profile first:

```bash
python scripts/agent-runtime.py runtime-detect-validation-profile \
  --project my-project \
  --stack Python \
  --task-layer Runtime \
  --files scripts/agent-runtime.py
```

```bash
python scripts/agent-runtime.py runtime-run-verification \
  --project my-project \
  --command "python -m py_compile scripts\\agent-runtime.py scripts\\agent_store.py" \
  --record
```

By default, only safe verification prefixes are executable. Use `--allow-unsafe` only when the command has already been inspected.

---

## Plan Recovery

Use this for high-risk tasks.

```bash
python scripts/agent-runtime.py runtime-plan-recovery \
  --project my-project \
  --goal-id goal-phone-login \
  --task-id task-discover-phone-login \
  --files src/pages/Login.tsx src/api/auth.ts server/auth.ts \
  --checkpoint HEAD \
  --feature-flag PHONE_LOGIN_ENABLED \
  --record
```

---

## Manage Recovery State

```bash
python scripts/agent-runtime.py runtime-create-checkpoint \
  --project my-project \
  --files src/pages/Login.tsx src/api/auth.ts

python scripts/agent-runtime.py runtime-mark-recovery \
  --id 1 \
  --status obsolete \
  --reason "Validation passed"
```

---

## Final Gate Check

```bash
python scripts/agent-runtime.py runtime-final-check \
  --project my-project \
  --run-id run-phone-login \
  --require-recovery \
  --require-skills
```

The command checks runtime context, policy records, verification records, recovery points, skill recommendations, and open tasks.
Use `--goal-id` or `--run-id` to avoid older project records polluting the final check.

---

## Complete Runtime Tasks

```bash
python scripts/agent-runtime.py runtime-complete-task \
  --project my-project \
  --id run-phone-login-task-1 \
  --evidence "Implemented and verified" \
  --complete-goal
```

This closes durable queue records with evidence and can mark the goal completed when no open tasks remain.

---

## Review Improvements

```bash
python scripts/agent-runtime.py runtime-review-improvements \
  --project "*" \
  --record
```

Use `--goal-id` or `--run-id` to review only global candidates plus candidates associated with the current runtime goal/run:

```bash
python scripts/agent-runtime.py runtime-review-improvements \
  --project my-project \
  --goal-id goal-phone-login \
  --run-id run-phone-login \
  --record
```

This reviews candidate skill/rule evidence and writes improvement review records. It never promotes a candidate by itself.

---

## Runtime Report

```bash
python scripts/agent-runtime.py runtime-report \
  --project my-project \
  --run-id run-phone-login
```

The report returns goal, task, policy, verification, recovery, and skill recommendation evidence for the scoped run or goal.

---

## List And Summarize Runtime

```bash
python scripts/agent-runtime.py runtime-list --kind task --project my-project
python scripts/agent-runtime.py runtime-list --kind capability --project my-project --status broken-chain
python scripts/agent-runtime.py runtime-summary --project my-project
```

---

## Rules

- Do not use `scripts/memory-tools.py` for runtime commands.
- Prefer `runtime-run` for L2+ tasks when a complete loop is needed.
- Scope `runtime-final-check` and `runtime-report` with `--goal-id` or `--run-id` when possible.
- Do not treat runtime records as raw transcript storage.
- Do not store secrets, credentials, or noisy command logs.
- Do not auto-promote improvement records into skills or rules.
- Keep Markdown memory as the reviewable long-term memory layer.
