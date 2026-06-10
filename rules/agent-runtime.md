# Agent Runtime Rules

## Goal
Agent Runtime gives Codex Agent OS a structured operating layer for long-running engineering work. It records goals, tasks, observations, capability state, policy decisions, verification, recovery points, and controlled improvement reviews.

It does not create an always-on background agent. Runtime records are explicit, reviewable state written by the agent during gates and task execution.

---

## Runtime Capabilities

Codex Agent OS tracks ten agent capabilities through lightweight runtime records:

| Capability | Runtime Record | Purpose |
| --- | --- | --- |
| Goal Runtime | `agent_goals` | Preserve objective, phase, success criteria, status, and completion evidence. |
| Autonomous Observe Loop | `agent_observations` | Record observed file/test/build/user/project signals with evidence. |
| Planner / Executor Separation | `agent_tasks.assigned_role` | Split planning, execution, review, verification, and memory recording responsibilities. |
| Capability Graph | `capability_nodes`, `capability_links` | Track whether a product capability is complete, partial, broken-chain, absent, or unconfirmed. |
| Durable Task Queue | `agent_tasks` | Track pending, in-progress, completed, blocked, and cancelled work items. |
| Policy Engine | `policy_decisions` | Record plan/TDD/review/rollback/worktree/performance decisions with rationale. |
| Memory Intelligence | `memory_items`, `skill_candidates`, `improvement_reviews` | Capture stable preferences, reusable lessons, and promotion candidates without auto-upgrading. |
| Verification Orchestrator | `verification_runs` | Record verification scope, commands, results, and evidence. |
| Recovery / Rollback System | `recovery_points` | Record planned or available recovery strategies and affected files. |
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

Runtime state is managed through `scripts/memory-tools.py`:

```bash
python scripts/memory-tools.py runtime-record --kind goal ...
python scripts/memory-tools.py runtime-record --kind task ...
python scripts/memory-tools.py runtime-record --kind capability ...
python scripts/memory-tools.py runtime-record --kind policy ...
python scripts/memory-tools.py runtime-record --kind verification ...
python scripts/memory-tools.py runtime-record --kind recovery ...
python scripts/memory-tools.py runtime-record --kind improvement ...
python scripts/memory-tools.py runtime-list --kind task --project my-project
python scripts/memory-tools.py runtime-summary --project my-project
```

Use `tools/memory-tools.md` for command examples.
