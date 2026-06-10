# Agent Runtime Tools

Agent Runtime commands provide explicit operating-state controls for Codex Agent OS. They use the same SQLite database as memory tools, but they are not memory commands.

Use `scripts/agent-runtime.py` for goals, tasks, observations, capability graph, policy decisions, verification planning, recovery planning, next-action selection, and controlled improvement reviews.

---

## Commands

```bash
python scripts/agent-runtime.py --help
```

Available runtime commands:
- `runtime-record`
- `runtime-list`
- `runtime-summary`
- `runtime-scan-capability`
- `runtime-evaluate-policy`
- `runtime-next`
- `runtime-plan-verification`
- `runtime-plan-recovery`

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

## List And Summarize Runtime

```bash
python scripts/agent-runtime.py runtime-list --kind task --project my-project
python scripts/agent-runtime.py runtime-list --kind capability --project my-project --status broken-chain
python scripts/agent-runtime.py runtime-summary --project my-project
```

---

## Rules

- Do not use `scripts/memory-tools.py` for runtime commands.
- Do not treat runtime records as raw transcript storage.
- Do not store secrets, credentials, or noisy command logs.
- Do not auto-promote improvement records into skills or rules.
- Keep Markdown memory as the reviewable long-term memory layer.
