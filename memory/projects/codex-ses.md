# codex-ses


## 2026-06-29
- Recovery Engine 进入可消费闭环：`runtime-plan-recovery`、`runtime-create-checkpoint`、`runtime-mark-recovery` 会写事件；`runtime-run` 会在高风险任务时切到 `prepare-recovery`；`runtime-final-check` 和 `runtime-pipeline` 会消费 recovery points 判断恢复阶段是否可用。
- 新增恢复事件类型 `RecoveryPlanned`、`RecoveryCheckpointCreated`、`RecoveryMarked`，并同步到 `agent_events` schema。
- 验证：`python -m unittest tests.test_agent_runtime` 通过。

## 2026-06-29 Reflection Engine
- Added `reflections` table plus `runtime-reflect` command for manual and failure-driven reflections.
- `runtime-run-verification` now records a reflection automatically on failed/blocked verification and emits a `MemoryUpdated` event.
- Reflection records capture source type, root cause, summary, evidence, pattern, next step, and confidence.
- Verification of the reflection flow passed with `python -m unittest tests.test_agent_runtime`.

## 2026-06-29 Learning Engine
- Reflections now auto-flow into `memory_items` and `skill_candidates` in `runtime-reflect` and failed verification paths.
- Candidate promotion is intentionally bounded: it records evidence and boundary text, but does not modify rules or promote skills automatically.
- `runtime-run-verification` returns `learning` metadata so the caller can see the memory/candidate bridge.

## 2026-06-29 Docs Freshness Check
- Added `runtime-check-docs` plus `docs_freshness_for_request` / `docs_impact_for_files` helpers.
- Final gate now distinguishes `docs missing` vs `docs stale` when `--require-docs` is used, instead of only a generic workspace flag.
- Docs freshness is intentionally scoped to docs-related requests and docs paths to avoid false positives on ordinary feature work.

## 2026-06-29 Knowledge Conflict Detection
- Added `runtime-check-knowledge` and state-based `knowledge_conflict_from_state` / `knowledge_conflict_for_capability` helpers.
- Final gate now records knowledge conflict alongside docs freshness, so conflicts can block handoff when memory, docs, code, or runtime evidence disagree.
- Verification: `python -m unittest tests.test_agent_runtime` passed after the new checks were added.

## 2026-06-29 Tool Runtime
- Added `tool_runs` as the Tool Runtime execution record table with tool type, adapter, command/target, status, exit code, duration, failure type/detail, and evidence.
- Added `runtime-run-tool` for unified shell/git/api/browser tool execution or recording. Local command execution uses the existing safety allowlist unless `--allow-unsafe` is provided.
- `runtime-list --kind tool` and `runtime-summary` can now expose recent tool calls.
- Verification: `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Skill Runtime
- Added `skill_manifests` as the Skill Runtime validation record table with manifest status, dependencies, triggers, issues, warnings, and validation timestamps.
- Added `runtime-validate-skills` plus manifest loader/validator support for `SKILL.md` frontmatter, trigger instructions, dependency declarations, and missing skill files.
- `runtime-select-skills` now returns manifest status/path evidence, and `runtime-list --kind skill` / `runtime-summary` expose skill validation records.
- Standardized `feature-react` and `feature-ui` skill headings so all current skills pass the validator.
- Verification: `python scripts/agent-runtime.py runtime-validate-skills --project codex-ses`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Model Runtime
- Added `model_runs` as the Model Runtime execution record table with provider, model name, adapter, operation, status, tokens, cost estimate, prompt/response summaries, and failure metadata.
- Added `runtime-run-model` for provider-neutral model call recording across `openai`, `anthropic`, `google`, `qwen`, `deepseek`, `local`, and `custom` providers.
- `runtime-list --kind model` and `runtime-summary` can now expose recent model calls.
- Added event type `ModelRunRecorded` and a migration that rebuilds old `agent_events` tables when their CHECK constraint lacks newer event types.
- Verification: `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, `python -m unittest tests.test_agent_runtime`, and `python scripts/agent-runtime.py runtime-run-model --project codex-ses --provider openai --model gpt-5 --operation planning --status passed --record-only --prompt-summary "Plan" --response-summary "Done" --db memory\index.db` passed.

## 2026-06-29 Sub-agent Runtime
- Added `subagent_runs` as the Sub-agent Runtime record table with role, status, input summary, output summary, boundary, handoff target, failure type, evidence, and timestamps.
- Added `runtime-run-subagent` for planner/executor/reviewer/verifier/memory-recorder role handoff recording.
- `runtime-list --kind subagent` and `runtime-summary` can now expose recent sub-agent role runs.
- Added event type `SubAgentRunRecorded` and included it in the old `agent_events` CHECK-constraint migration.
- Verification: `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, `python -m unittest tests.test_agent_runtime`, and `python scripts/agent-runtime.py runtime-run-subagent --project codex-ses --role planner --status completed --input-summary "Plan P2-4" --output-summary "Sub-agent runtime scoped" --boundary "Record role handoff only" --handoff-to executor --db memory\index.db` passed.

## 2026-06-29 Adapter Layer
- Added `host_adapters` as the Adapter Layer registry with host type, adapter name, entrypoint, capabilities, config path, status, issues, and evidence.
- Added `runtime-register-adapter` for registering or validating Codex, Claude, Cursor, VSCode, CLI, MCP, or custom host adapters.
- `runtime-list --kind adapter` and `runtime-summary` can now expose registered host adapters.
- Added event type `AdapterRegistered` and included it in the old `agent_events` CHECK-constraint migration.
- Verification: `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, `python -m unittest tests.test_agent_runtime`, and `python scripts/agent-runtime.py runtime-register-adapter --project codex-ses --host-type codex --adapter-name codex-cli --capability shell git runtime-cli skills --config-path AGENTS.md --db memory\index.db` passed.

## 2026-06-29 Observability Metrics
- Added `runtime_metrics` as the Observability Metrics record table with tool/model/verification counts, failure count, retry count, average duration, verification pass rate, and failure rate.
- Added `runtime-metrics` to calculate project/goal/run-scoped metrics from existing runtime records and optionally persist them.
- `runtime-list --kind metrics` and `runtime-summary` can now expose recent metrics snapshots.
- Added event type `MetricsRecorded` and included it in the old `agent_events` CHECK-constraint migration.
- Verification: `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, `python -m unittest tests.test_agent_runtime`, and `python scripts/agent-runtime.py runtime-metrics --project codex-ses --record --db memory\index.db` passed.

## 2026-06-29 Trace Report
- Added `runtime_traces` as the Trace Report archive table with project, goal, run, exported trace JSON, and export timestamp.
- Added `runtime-trace` to export a complete runtime chain across goal/run/context, tasks, policies, skill recommendations, skill manifests, tools, models, sub-agents, adapters, verification, recovery, metrics, and events.
- `runtime-list --kind trace` and `runtime-summary` can now expose recent trace exports.
- Added event type `TraceExported` and included it in the old `agent_events` CHECK-constraint migration.
- Verification: `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, `python -m unittest tests.test_agent_runtime`, and `git diff --check` passed with only CRLF normalization warnings.

## 2026-06-29 Install Health Check
- Added `runtime-doctor` as the install health check command for Agent OS.
- Doctor checks required directories, AGENTS.md core sections, required rules, skill manifest validity, memory schema initialization, schema version, and runtime tables.
- Broken installs now return structured failed checks instead of crashing when `memory/schema.sql` is missing.
- Synchronized `memory/schema.sql` top-level schema version with the current migration version.
- Verification: `python scripts/agent-runtime.py runtime-doctor --db memory\doctor-test.db`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Versioning / Migration
- Added root `VERSION` with Agent OS version `2.0.0`.
- Added `runtime-version` to report Agent OS version, expected schema version, database existence, current DB schema version, and whether migration is required.
- Added `runtime-migrate` with `--dry-run` support for safe SQLite runtime initialization and schema migration through the existing migration layer.
- Verification: `python scripts/agent-runtime.py runtime-version --db memory\doctor-test.db`, `python scripts/agent-runtime.py runtime-migrate --db memory\migration-test.db --dry-run`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Dashboard
- Added `runtime-dashboard` to generate a local static HTML Agent OS Runtime Dashboard.
- Dashboard shows goals, runs, tasks, events, and verification records with a compact summary.
- Default output is `docs/agent-os/dashboard.html` for user projects; tests and source validation use temporary output paths to avoid polluting the Agent OS source repository.
- Verification: `python scripts/agent-runtime.py runtime-dashboard --project codex-ses --db memory\doctor-test.db --output <temp-html>`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Quality Trends
- Added docs quality fields to runtime metrics snapshots: docs missing, stale, and update-required signals.
- Added `runtime-quality-trends` to report quality trends from metrics snapshots, including failure rate, verification pass rate, retry totals, and docs missing/stale rate.
- Verification: `python scripts/agent-runtime.py runtime-quality-trends --project codex-ses --db memory\doctor-test.db`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Team Policy Packs
- Added `policy-packs/core-governance/policy-pack.json` as the default reusable team governance pack.
- Added `runtime-policy-packs` to list and validate policy packs, including referenced rules, workflows, and gates.
- Verification: `python scripts/agent-runtime.py runtime-policy-packs --name core-governance`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Distribution Strategy
- Documented supported distribution channels in README: copy to `.agent-os/`, clone as `.agent-os`, Git submodule/subtree, VSCode plugin injection, and future package-manager distribution.
- Documented post-install and post-upgrade commands: `runtime-doctor`, `runtime-version`, `runtime-migrate --dry-run`, `runtime-migrate`, `runtime-dashboard`, `runtime-quality-trends`, and `runtime-policy-packs`.
- Clarified upgrade boundaries for `.agent-os/`, root `AGENTS.md`, `docs/agent-os/`, `memory/index.db`, and project memory files.
- Verification: `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, `python -m unittest tests.test_agent_runtime`, and `git diff --check` passed with only CRLF normalization warnings.

## 2026-06-29 Security Hardening
- Added `rules/security-hardening.md` with secret handling, permission policy, and sandbox strategy.
- Added `runtime-security-check` to scan for secret-like values and report Tool Runtime allowlist policy plus sandbox/worktree recommendations.
- Added `security-hardening.md` to doctor-required rules and the default `core-governance` policy pack.
- Verification: `python scripts/agent-runtime.py runtime-security-check --max-files 2000`, `python scripts/agent-runtime.py runtime-doctor --db memory\doctor-test.db`, `python scripts/agent-runtime.py runtime-policy-packs --name core-governance`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, `python -m unittest tests.test_agent_runtime`, and `git diff --check` passed with only CRLF normalization warnings.

## 2026-06-29 Skill Runtime Full Implementation
- Completed P2-F5 by extending Skill Runtime beyond manifest presence checks.
- Skill manifests now support `version`, `dependencies`, `triggers`, and `conflicts`; all source skills declare `version: 1.0.0`.
- `runtime-validate-skills` now returns dependency graph, trigger match evidence, conflicts, and blockers; missing dependencies or declared conflicts make the runtime result `ok: false`.
- `runtime-select-skills` now explains trigger/layer selection evidence and reports dependency/conflict blockers before execution.
- SQLite schema version advanced to `14`; `skill_manifests` records `version` and `conflicts_json`.
- Verification: `python scripts/agent-runtime.py runtime-validate-skills --project codex-ses --request "implement phone login" --task-layer API --stack Node`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Model Runtime Full Implementation
- Completed P2-F6 and P2-F7 by upgrading Model Runtime from record-only contract logging to adapter-backed execution and provider diagnostics.
- Added `mock` as a first-class model provider and kept `local` executable without external credentials; both produce deterministic adapter responses with prompt hashes, token counts, and zero cost by default.
- External providers now run configuration diagnostics before execution; missing required env keys return `blocked` with explicit `missing-provider-config:<ENV>` failure details.
- Model Runtime summaries, responses, evidence, and event payloads pass through secret redaction before persistence, so secret-like prompt or response values are not stored raw.
- SQLite schema version advanced to `15`; `model_runs` provider CHECK migration now allows `mock` for existing databases.
- Verification: `python scripts/agent-runtime.py runtime-run-model --project codex-ses --provider mock --model mock-planner --operation planning --prompt "Plan P2 F6 verification" --db memory\p2f6-model-check.db`, `python scripts/agent-runtime.py runtime-version --db memory\p2f6-model-check.db`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Sub-agent Runtime Full Implementation
- Completed P2-F8 and P2-F9 by upgrading sub-agents from isolated records to executable role chains.
- Added `runtime-plan-subagents` to create ordered planner -> executor -> reviewer -> verifier chains, including runtime goal/run initialization, `agent_tasks` queue entries, role boundaries, handoffs, and subagent records.
- Added `runtime-run-subagent-role` so reviewer can produce structured diff findings and verifier can execute a validation command, persist a subagent result, and write a `verification_runs` record.
- Reviewer currently flags secret-like assignments, TODO/FIXME incomplete work, and debug output as structured findings.
- Verification: `python scripts/agent-runtime.py runtime-plan-subagents --project codex-ses --goal-id goal-p2f8 --run-id run-p2f8 --request "Verify subagent chain" --task-prefix p2f8 --db memory\p2f8-subagent-check.db`, `python scripts/agent-runtime.py runtime-run-subagent-role --project codex-ses --goal-id goal-p2f8 --run-id run-p2f8 --task-id p2f8-4-verifier --role verifier --command "python -m py_compile scripts/agent-runtime.py" --scope "P2-F9 verifier" --db memory\p2f8-subagent-check.db`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed.

## 2026-06-29 Host Adapter Full Implementation
- Completed P2-F10 by adding a host capability protocol for Codex, Claude, Cursor, VSCode, CLI, MCP, and custom hosts.
- `runtime-register-adapter` now evaluates declared capabilities against the host protocol, reports unsupported declarations, and can require specific capabilities at registration.
- Added `runtime-detect-host-adapter` to report available adapters, supported capabilities, missing capabilities, unsupported declarations, and compatible adapters for a requested host.
- Verification: `python scripts/agent-runtime.py runtime-register-adapter --project codex-ses --host-type cli --adapter-name agent-os-cli --capability runtime-cli doctor dashboard report security-check policy-packs --require-capability runtime-cli doctor --db memory\p2f10-adapter-check.db`, `python scripts/agent-runtime.py runtime-detect-host-adapter --project codex-ses --host-type cli --require-capability runtime-cli doctor dashboard --db memory\p2f10-adapter-check.db`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed when `TEMP/TMP` pointed at `D:\codex-ses\.tmp` because the default C: temp drive was full.

## 2026-06-29 Runtime Orchestrator and Trace Full Implementation
- Completed P2-F11 and P2-F12 by adding `runtime-orchestrate` and enhancing `runtime-trace`.
- `runtime-orchestrate` now creates a runtime goal/run, records context, policy decisions, task queue, skill recommendations/manifests, subagent chain, mock model planning, verifier execution, metrics, events, and final trace in one loop.
- Orchestrator completion now marks runtime tasks and planned subagents completed so the chain is advanced, not only planned.
- `runtime-trace` now includes `timeline`, `duration_ms`, `input_hash`, `output_hash`, and `event_count` in addition to the existing goal/run/context/tasks/policies/skills/tools/models/subagents/adapters/verification/recovery/metrics/events data.
- Verification: `python scripts/agent-runtime.py runtime-orchestrate --project codex-ses --goal-id goal-p2f11-final --run-id run-p2f11-final --request "orchestrate runtime chain final check" --verification-command "python -m py_compile scripts/agent-runtime.py" --db memory\p2f11-orchestrate-final.db`, `python -m py_compile scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed with `TEMP/TMP=D:\codex-ses\.tmp`.

## 2026-06-29 Product CLI and Installer
- Completed P3-F1 and P3-F2 by adding `scripts/agent-os.py` as a product CLI wrapper.
- `agent-os doctor` and related aliases now forward to runtime commands without requiring users to know `runtime-*` names.
- Added `agent-os install --target <project>` to copy Agent OS into `<project>/.agent-os`, generate root `AGENTS.md` from `templates/project-AGENTS.md`, and initialize `.agent-os/memory/index.db`.
- Installer skips local runtime/cache folders and avoids recursively copying an install target inside the source checkout.
- Verification: `python scripts/agent-os.py doctor --db memory\p3f1-cli-check.db`, `python -m py_compile scripts/agent-os.py scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py`, and `python -m unittest tests.test_agent_runtime` passed with `TEMP/TMP=D:\codex-ses\.tmp`.

## 2026-06-29 Productization Full Implementation
- Completed P3-F3 through P3-F12 in `plan.md`.
- Upgrade/Migration and Doctor now cover safe migration backup/dry-run/report/rollback hints plus root AGENTS, templates, policy packs, security, version compatibility, and DB writability checks.
- Dashboard now generates both local HTML and VSCode/plugin-consumable JSON data; Quality Trends now reports trend series, failure clusters, verification pass rates, retry totals, and docs missing/stale rates.
- Policy Packs now support enable, disable, override, inherit, and conflict checks through `.enabled.json` state.
- Security Hardening now supports `.agent-os-security-ignore`, entropy-based secret detection, dangerous command policy, sandbox strategy reporting, and JSON audit output.
- Productization now includes `runtime-vscode-protocol`, `runtime-distribution`, `runtime-team-workspace`, and `runtime-release-check`, with `agent-os` aliases for product CLI use.
- Verification: targeted P3 productization tests and `runtime-security-check --max-files 2000` passed before full-suite validation.
