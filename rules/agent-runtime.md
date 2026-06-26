# Agent Runtime Rules

## Goal
Agent Runtime gives Agent OS a structured operating layer for long-running engineering work. It records goals, tasks, observations, capability state, policy decisions, verification, recovery points, and controlled improvement reviews, and it provides lightweight controllers for capability scanning, policy evaluation, next-action selection, verification planning, and recovery planning.

It does not create an always-on background agent. Runtime actions are explicit, reviewable commands run by the agent during gates and task execution.

Runtime records never replace user-visible workflow output. If the selected workflow requires execution intent, a diagnostic plan, a structured plan, recovery strategy, or review decision, the agent must show it to the user before implementation.

Runtime records also do not replace durable project execution documents. When a task needs a lasting implementation plan, task breakdown, decision record, review, or verification report, write it under the user project's `docs/agent-os/` directory:
- `docs/agent-os/plans/`
- `docs/agent-os/tasks/`
- `docs/agent-os/decisions/`
- `docs/agent-os/reviews/`
- `docs/agent-os/verification/`

Do not write project execution documents under `.agent-os/`.

Runtime records also do not replace Documentation Gate. If runtime activity changes user-facing setup, usage, commands, contracts, validation, troubleshooting, or Agent OS behavior, update README/docs/tool docs/templates/tests or state why no documentation update is needed before final response.

---

## Runtime Capabilities

Agent OS tracks ten agent capabilities through runtime records and controller commands:

| Capability | Runtime Record | Purpose |
| --- | --- | --- |
| Goal Runtime | `agent_goals` | Preserve objective, phase, success criteria, status, and completion evidence. |
| Autonomous Observe Loop | `agent_observations`, `runtime-scan-capability` | Record observed file/test/build/user/project signals with evidence. |
| Planner / Executor Separation | `agent_tasks.assigned_role`, `runtime-next` | Split planning, execution, review, verification, and memory recording responsibilities. |
| Capability Graph | `capability_nodes`, `capability_links`, `runtime-scan-capability` | Track whether a product capability is complete, partial, broken-chain, absent, or unconfirmed. |
| Durable Task Queue | `agent_tasks`, `runtime-next` | Track pending, in-progress, completed, blocked, and cancelled work items. |
| Policy Engine | `policy_decisions`, `runtime-evaluate-policy` | Evaluate and record plan/TDD/review/rollback/worktree/performance decisions with rationale. |
| Memory Intelligence | `memory_items`, `skill_candidates`, `improvement_reviews` | Capture stable preferences, reusable lessons, and promotion candidates without auto-upgrading. |
| Verification Orchestrator | `verification_runs`, `runtime-plan-verification` | Plan and record verification scope, commands, results, and evidence. |
| Recovery / Rollback System | `recovery_points`, `runtime-plan-recovery` | Plan and record recovery strategies and affected files. |
| Self-Improvement Governance | `improvement_reviews` | Track candidate improvements through review, approval, rejection, or promotion. |

---

## Runtime Use

Use runtime records when a task is L2 or above, spans multiple turns, involves capability discovery, or requires durable state beyond the current response.

Minimum runtime expectations:
- L1: Runtime records optional; validation still required.
- L2: Record a task and key policy decisions when planning is needed.
- L3: Record goal/task, capability state, policy decisions, verification, and recovery points.
- L4: Record all applicable runtime state, including review and controlled improvement records.

Runtime records should summarize state. Do not store raw transcripts, secrets, credentials, or noisy command logs.

---

## Runtime Controllers

Runtime controllers convert gate decisions into explicit command outputs:

- `runtime-detect-context`: detects project, stack, task layers, task scale, intent, confidence, and evidence.
- `runtime-run`: runs the full planning loop: context, capability, policy, tasks, skill recommendations, verification plan, and recovery plan.
- `runtime-scan-capability`: scans memory-adjacent project files and classifies capability state as `complete`, `partial`, `broken-chain`, `absent`, or `unconfirmed`.
- `runtime-evaluate-policy`: evaluates task scale, capability state, task layers, and risk signals into plan/TDD/review/rollback/worktree/performance decisions.
- `runtime-plan-tasks`: creates a durable runtime task queue from context and capability state.
- `runtime-select-skills`: recommends task-layer skills with rationale.
- `runtime-complete-task`: marks durable task records completed with evidence and can complete the goal when no open tasks remain.
- `runtime-next`: reads active goals, pending tasks, capability state, and failed verification to choose the next action.
- `runtime-plan-verification`: builds a verification checklist from task layer, scale, and affected files.
- `runtime-detect-validation-profile`: detects stack-specific validation commands for the task.
- `runtime-run-verification`: executes allowed verification commands and records exit code, result, summary, and failure type.
- `runtime-plan-recovery`: builds a recovery strategy from checkpoint, affected files, migration, and feature-flag inputs.
- `runtime-create-checkpoint`: records an available recovery checkpoint.
- `runtime-mark-recovery`: marks a recovery point as used, available, planned, or obsolete.
- `runtime-final-check`: checks final gate completeness before handoff and should be scoped with `--goal-id` or `--run-id` for multi-task projects.
- `runtime-review-improvements`: reviews candidate skill/rule evidence and returns promotion readiness; scope with `--goal-id` or `--run-id` during final task review.
- `runtime-report`: generates a scoped audit report for a run or goal.

Controllers may run in dry output mode or with `--record` to write runtime records. Recorded controller output is evidence, not a substitute for code inspection, real validation, or user-visible workflow output.

`runtime-run`, `runtime-plan-tasks`, and policy records can prepare the operating loop, but the agent still must summarize the applicable workflow intent or plan in the conversation before editing files.

---

## Capability Graph Rules

Capability state must be evidence-based:
- `complete`: frontend/API/backend/data-state path and verification evidence exist.
- `partial`: at least one layer exists, but the capability is not end-to-end.
- `broken-chain`: related layers exist, but the integration path is disconnected or contract-mismatched.
- `absent`: no meaningful implementation or memory evidence exists.
- `unconfirmed`: evidence is insufficient.

Capability state feeds Planning Gate:
- `complete` + low-risk local change may be L1.
- `partial`, `broken-chain`, `absent`, or `unconfirmed` must not be treated as L1.

Scanner evidence boundary:
- Documentation, README, AGENTS, rules, and tool docs can explain a capability, but they do not prove the product capability exists.
- `runtime-scan-capability` must treat implementation files, API clients, backend routes, data models, and tests as stronger evidence than documentation.
- API/client/backend route token overlap is stronger evidence than isolated file hits.
- A capability must not be marked `complete` from documentation-only hits.
- If scanner output conflicts with manual code inspection, manual evidence wins and the capability record must be corrected.

---

## Policy Decisions

Policy decisions should be recorded when they affect execution mode or risk controls:
- `plan`
- `tdd`
- `review`
- `rollback`
- `worktree`
- `performance`
- `execution-mode`

Every policy decision needs rationale and evidence. A policy record does not replace the actual plan or validation summary.

When a policy decision affects execution mode, TDD, review, rollback, worktree, or performance checks, the user-visible workflow output must include the relevant decision before implementation.

---

## Verification And Recovery

Verification records must say what was checked, how it was checked, and the result.

Recovery records must be created before high-risk changes when rollback or isolation matters. They can point to:
- clean branch or commit checkpoint
- files that can be reverted
- database migration rollback strategy
- feature flag or configuration fallback
- manual recovery steps

---

## Self-Improvement Boundary

Runtime can identify improvement candidates, but it cannot self-upgrade the Agent OS.

The agent may:
- record stable user preferences after Memory Gate
- record repeated lessons and patterns
- open improvement review records
- link candidates to evidence

The agent must not:
- auto-edit `AGENTS.md`, `rules/`, or `skills/`
- promote a candidate without Review Gate or explicit user approval
- treat one conversation as enough evidence for a rule
- record private or unverified material as durable knowledge

---

## Commands

Runtime state is managed through `scripts/agent-runtime.py`:

```bash
python scripts/agent-runtime.py runtime-record --kind goal ...
python scripts/agent-runtime.py runtime-record --kind task ...
python scripts/agent-runtime.py runtime-record --kind capability ...
python scripts/agent-runtime.py runtime-record --kind policy ...
python scripts/agent-runtime.py runtime-record --kind verification ...
python scripts/agent-runtime.py runtime-record --kind recovery ...
python scripts/agent-runtime.py runtime-record --kind improvement ...
python scripts/agent-runtime.py runtime-list --kind task --project my-project
python scripts/agent-runtime.py runtime-summary --project my-project
python scripts/agent-runtime.py runtime-detect-context --request "Implement phone login" --files src/Login.tsx server/auth.ts --record
python scripts/agent-runtime.py runtime-run --project my-project --request "Implement phone login" --capability phone-login --term phone login auth --record
python scripts/agent-runtime.py runtime-scan-capability --project my-project --name phone-login --term phone login --record
python scripts/agent-runtime.py runtime-evaluate-policy --project my-project --scale L3 --capability-status broken-chain --task-layer Integration API --signal auth --record
python scripts/agent-runtime.py runtime-plan-tasks --project my-project --goal-id goal-phone-login --request "Implement phone login" --scale L3 --capability-status broken-chain --record
python scripts/agent-runtime.py runtime-select-skills --project my-project --request "Implement phone login" --stack "React Node" --record
python scripts/agent-runtime.py runtime-complete-task --project my-project --id run-1-task-1 --evidence "Implemented and verified" --complete-goal
python scripts/agent-runtime.py runtime-next --project my-project --advance
python scripts/agent-runtime.py runtime-plan-verification --project my-project --task-layer Runtime Integration --scale L3 --record
python scripts/agent-runtime.py runtime-detect-validation-profile --project my-project --stack Python --task-layer Runtime --files scripts/agent-runtime.py
python scripts/agent-runtime.py runtime-run-verification --project my-project --command "python -m py_compile scripts\\agent-runtime.py scripts\\agent_store.py" --record
python scripts/agent-runtime.py runtime-plan-recovery --project my-project --files src/Login.tsx server/auth.ts --checkpoint HEAD --record
python scripts/agent-runtime.py runtime-create-checkpoint --project my-project --files src/Login.tsx server/auth.ts
python scripts/agent-runtime.py runtime-mark-recovery --id 1 --status obsolete --reason "validation passed"
python scripts/agent-runtime.py runtime-final-check --project my-project --run-id run-1 --require-recovery --require-skills
python scripts/agent-runtime.py runtime-report --project my-project --run-id run-1
python scripts/agent-runtime.py runtime-review-improvements --project my-project --goal-id goal-1 --run-id run-1 --record
```

Use `tools/agent-runtime.md` for command examples.
