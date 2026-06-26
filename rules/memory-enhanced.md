# Enhanced Memory Rules

## Goal
Add structured memory retrieval and recording while keeping Agent OS lightweight, reviewable, and controlled.

This rule strengthens Memory Gate. It does not replace Markdown memory, Evolution Policy, or Review Gate.

---

## Memory Sources

Use both layers when available:

1. Markdown memory
   - `memory/projects/{project}.md`
   - `memory/global/*.md`
   - human-readable and Git-reviewable
   - source of truth for stable project context and decisions

2. SQLite memory backend
   - `memory/index.db`
   - generated locally on first `scripts/memory-tools.py` call
   - ignored by Git
   - fast retrieval and structured indexing
   - managed through `scripts/memory-tools.py`

If `scripts/memory-tools.py` or `memory/schema.sql` is unavailable, continue using Markdown memory and report the missing SQLite recording in the final response.

---

## No Autonomous Memory Brain

Agent OS does not have a background autonomous memory brain.

The agent must not:
- silently read or summarize full chat history into long-term memory
- automatically treat ordinary conversation as durable memory
- record one-off instructions as stable preferences
- treat SQLite records as more authoritative than current project files or Markdown memory

Memory is explicit and reviewable:
- Markdown memory is the human-readable source of truth.
- SQLite is a local structured retrieval and recording index.
- User preferences require Memory Gate judgment before recording.
- Sensitive data, credentials, private data, and unverified guesses must not be recorded.

---

## Context Gate Enhancement

When a task resembles prior work, prior bugs, repeated UI patterns, architecture decisions, or unclear historical context:

1. Search project Markdown memory.
2. If SQLite memory is available, search it:

```bash
python scripts/memory-tools.py search "<query>" --project <project>
```

If SQLite search returns no results but Markdown memory exists, import Markdown before concluding there is no history:

```bash
python scripts/memory-tools.py import-markdown --project <project>
```

Useful queries:
- feature name
- bug symptom
- page type
- API name
- data model
- error message
- design pattern
- validation failure

Use search results as context, not unquestioned truth. Confirm important details against current files.

---

## Memory Gate Plus

After Validation Gate, decide:
1. Did this task produce a reusable memory item?
2. Is it project-specific or cross-project?
3. Should Markdown project memory be updated?
4. Should SQLite memory be recorded?
5. Is it only a candidate skill?
6. Does it meet Evolution Policy thresholds?
7. Is Review Gate required before updating a skill or rule?
8. Did required SQLite recording actually run?

---

## Mandatory SQLite Recording

When `memory/schema.sql` and `scripts/memory-tools.py` exist, run at least `record-session` for high-signal tasks:
- API contract, backend behavior, auth, error code, or response shape changes
- data model, schema, migration, query, cache, or consistency changes
- cross-module or cross-layer flow changes
- bugfix with root cause, repeat risk, or future diagnostic value
- reusable implementation pattern, UI pattern, decision, validation lesson, or project constraint
- Agent OS changes to AGENTS, rules, skills, memory policy, or tooling
- user explicitly asks to remember, record, or use later

Also run `record-item` for:
- verified lessons
- implemented features
- decisions
- reusable patterns
- meaningful validation results
- stable user preferences

If both Markdown and SQLite apply, write both.

If required SQLite recording cannot run, final response must include:
- why it did not run
- which Markdown memory was updated instead
- exact backfill command

---

## Memory Recorder Sub-Agent

For complex tasks, memory writing can be delegated to a Memory Recorder sub-agent.

Provide:
- project slug
- task summary
- confirmed root cause or decision
- changed files
- validation result
- Markdown memory target, if any
- exact SQLite commands

The sub-agent may update memory and run `memory-tools.py`; it must not modify business code, rules, skills, or AGENTS.

---

## Existing Markdown Import

Older projects may have Markdown memory but no SQLite index.

Preview:

```bash
python scripts/memory-tools.py import-markdown --project <project> --dry-run
```

Import one project:

```bash
python scripts/memory-tools.py import-markdown --project <project>
```

Import all projects:

```bash
python scripts/memory-tools.py import-markdown --all-projects
```

Imported records are an index, not a new source of truth. Confirm important details against Markdown.

---

## What To Record

Record high-signal memory:
- repeated bug causes and verified fixes
- previously implemented features and files
- architecture or API decisions
- UI layout patterns and viewport fixes
- validation failures and final resolutions
- reusable project-specific constraints
- stable user preferences
- candidate skills with evidence

Types:
- `lesson`
- `feature`
- `decision`
- `pattern`
- `validation`
- `candidate`
- `note`

---

## What Not To Record

Do not record:
- raw full trajectories
- every command output
- ordinary successful steps already covered by rules
- unverified guesses
- temporary experiments
- large code snippets
- secrets, tokens, credentials, or private data
- business details from another project

---

## Preference Recording

Stable preferences should be written to Markdown first:

```text
memory/global/preferences.md
```

SQLite can also record them with `--project "*"` and `--type note`.

Record a user preference only when it is:
- explicitly long-term or repeated
- useful for future collaboration
- not tied to one project's private business logic
- non-sensitive

Do not record one-off instructions, temporary constraints, guesses about taste, or project-specific business rules as global preferences.

---

## SQLite Recording

Use the real script. Do not invent tool calls.

Record a lesson:

```bash
python scripts/memory-tools.py record-item \
  --project <project> \
  --type lesson \
  --title "<short title>" \
  --summary "<what happened and why it matters>" \
  --problem "<problem>" \
  --solution "<verified solution>" \
  --tags tag1 tag2 \
  --validation "<how it was verified>"
```

Record a feature:

```bash
python scripts/memory-tools.py record-item \
  --project <project> \
  --type feature \
  --title "<feature name>" \
  --summary "<what was implemented>" \
  --patterns pattern1 pattern2 \
  --files path1 path2 \
  --tags feature area \
  --validation "<verification summary>"
```

Record a session:

```bash
python scripts/memory-tools.py record-session \
  --project <project> \
  --task-summary "<what changed>" \
  --key-decisions "<important decisions or none>" \
  --validation-summary "<validation>" \
  --memory-updated
```

---

## Candidate Skill Rules

Candidate tracking is allowed. Automatic skill creation is not.

Use candidates when:
- a lesson repeats
- a workflow is reusable
- the trigger and boundary are clear
- validation evidence exists

Promotion requires Evolution Policy, Review Gate, and explicit user approval for rules/skills/AGENTS changes.

---

## Search Before Repeating Work

Before familiar work, search memory:

```bash
python scripts/memory-tools.py search "login viewport overflow"
python scripts/memory-tools.py search "file upload size display"
python scripts/memory-tools.py search "api auth error handling"
```

---

## Git Boundary

Commit:
- `memory/schema.sql`
- `scripts/memory-tools.py`
- `tools/memory-tools.md`
- Markdown memory files when appropriate

Do not commit:
- `memory/index.db`
- `memory/index.db-wal`
- `memory/index.db-shm`
- raw logs
- temporary session artifacts

---

## Review Boundary

SQLite may suggest.

Review Gate decides.

Memory may evolve into candidates, skills, or rules only through controlled review.
