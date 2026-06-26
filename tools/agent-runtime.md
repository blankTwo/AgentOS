# Agent Runtime Tools

Agent Runtime commands provide explicit operating-state controls for Agent OS. They use the same SQLite database as memory tools, but they are not memory commands.

Use `scripts/agent-runtime.py` for goals, tasks, observations, capability graph, policy decisions, verification planning, recovery planning, next-action selection, and controlled improvement reviews.

Runtime records do not replace user-visible workflow output. If a workflow requires intent, diagnostic plan, structured plan, recovery, or review decision, show it in the conversation before editing files.

---

## Commands

```bash
python scripts/agent-runtime.py --help
```

Available runtime commands:
- `runtime-detect-context`
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

This produces project, stack, task layers, task scale, intent, confidence, and evidence.

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
