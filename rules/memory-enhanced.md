# Enhanced Memory Rules

## Goal
Add structured memory retrieval and recording while keeping Codex Agent OS lightweight, reviewable, and controlled.

This rule strengthens Memory Gate. It does not replace Markdown memory, Evolution Policy, or Review Gate.

---

## Memory Sources

Use both layers when available:

1. Markdown memory
   - `memory/projects/{project}.md`
   - `memory/global/*.md`
   - Human-readable and Git-reviewable
   - Source of truth for stable project context and decisions

2. SQLite memory backend
   - `memory/index.db`
   - Generated locally on first `scripts/memory-tools.py` call
   - Ignored by Git
   - Fast retrieval and structured indexing
   - Managed through `scripts/memory-tools.py`

If `scripts/memory-tools.py` or `memory/schema.sql` is unavailable, continue using Markdown memory and report the missing SQLite recording in the final response.

---

## No Autonomous Memory Brain

Codex Agent OS does not have a background autonomous memory brain.

The agent must not:
- silently read or summarize full chat history into long-term memory
- automatically treat ordinary conversation as durable memory
- record one-off instructions as stable preferences
- use SQLite records as more authoritative than current project files or Markdown memory

Memory is explicit and reviewable:
- Markdown memory is the human-readable source of truth
- SQLite is a local structured retrieval and recording index
- user preferences require Memory Gate judgment before recording
- sensitive data, credentials, private data, and unverified guesses must not be recorded

---

## Context Gate Enhancement

When a task resembles prior work, prior bugs, repeated UI patterns, architecture decisions, or unclear historical context:

1. Search project memory Markdown.
2. If `scripts/memory-tools.py` and `memory/schema.sql` exist, search SQLite memory:

```bash
python scripts/memory-tools.py search "<query>" --project <project>
```

The first search may create `memory/index.db` automatically. This is expected. The database remains local and must not be committed.

If SQLite search returns no results but Markdown memory has existing records, the project may be an older project that has not been indexed yet. Run Markdown import before concluding there is no history:

```bash
python scripts/memory-tools.py import-markdown --project <project>
```

Useful queries include:
- feature name
- bug symptom
- page type
- API name
- data model
- error message
- design pattern
- validation failure

Use search results as context, not as unquestioned truth. Confirm against current files before modifying code.

---

## Memory Gate Plus

At task completion, after Validation Gate, decide:

1. Did this task produce a reusable memory item?
2. Is it project-specific or cross-project?
3. Should it be written to Markdown project memory?
4. Should it be recorded in SQLite memory?
5. Is it only a candidate skill?
6. Does it meet existing Evolution Policy thresholds?
7. Is Review Gate required before updating a skill or rule?
8. Did required SQLite recording actually run, or is there a stated reason it could not run?

---

## Mandatory SQLite Recording

When `memory/schema.sql` and `scripts/memory-tools.py` exist, SQLite recording is mandatory for high-signal tasks.

At task completion, run at least `record-session` when any of these are true:
- API contract changed: route, request params, response shape, auth, errors, backend behavior
- Data model changed: table, collection, schema, migration, query, cache, consistency rule
- Cross-module or cross-layer flow changed: frontend/backend integration, SDK, webhook, service boundary
- Bugfix has a clear root cause, repeated symptom, regression risk, or future diagnostic value
- A reusable implementation pattern, UI pattern, architecture decision, validation lesson, or project constraint was discovered
- Agent OS files changed: `AGENTS.md`, `rules/`, `skills/`, memory policy, or memory tooling
- User explicitly asks to remember, record,沉淀, or use later

Also run `record-item` when the task produced any of these:
- `lesson`: verified pitfall and fix
- `feature`: implemented feature or flow that future work may resemble
- `decision`: architecture/API/data/UI decision and rationale
- `pattern`: reusable implementation or UI pattern
- `validation`: validation result or failure that matters later
- `note`: stable user preference or useful context

If both Markdown and SQLite apply, write both:
- Markdown for stable, reviewable project/global context
- SQLite for fast retrieval and structured search

Do not finish silently when required SQLite recording cannot run. The final response must state:
- why SQLite recording did not run
- which Markdown memory was updated instead
- the exact command that can be run later to backfill the record

---

## Memory Recorder Sub-Agent

For complex tasks, memory writing can be delegated to a Memory Recorder sub-agent so the main agent can continue verification or user-facing completion work.

Use a sub-agent when:
- The task produced multiple memory records
- Markdown memory and SQLite records both need updates
- Candidate skill/rule evidence needs to be organized
- The main task is otherwise complete and memory writing would create noticeable latency

The main agent should give the sub-agent a bounded packet:
- Project slug
- Task summary
- Confirmed root cause or decision
- Files changed
- Validation result
- Which Markdown memory file to update, if any
- Required SQLite commands: `record-session`, `record-item`, `candidate-upsert`

Sub-agent write scope:
- `memory/projects/{project}.md`
- `memory/global/preferences.md` only for stable user preferences
- SQLite via `scripts/memory-tools.py`

Sub-agent must not:
- Touch business code
- Modify rules, skills, or `AGENTS.md`
- Record unverified guesses
- Promote candidates without Review Gate

The main agent remains accountable. Before final response, it must know whether memory recording completed. If it did not complete, final must include the reason and the backfill commands.

---

## Existing Markdown Import

Older projects may already have useful `memory/projects/*.md` files but no SQLite index.

When an older project has Markdown memory and SQLite search returns no relevant results, import the Markdown memory:

```bash
python scripts/memory-tools.py import-markdown --project <project>
```

For migration across all project memories:

```bash
python scripts/memory-tools.py import-markdown --all-projects
```

Use dry-run first when the memory file is large or unfamiliar:

```bash
python scripts/memory-tools.py import-markdown --project <project> --dry-run
```

Import behavior:
- Splits Markdown by headings
- Infers item type from section title/content
- Stores the source file path in SQLite metadata
- Marks imported items with `imported,markdown`
- Uses stable import keys so repeated imports update rather than duplicate

Imported Markdown is an index, not a new source of truth. Confirm important details against the original Markdown file before making changes.

---

## What To Record

Record high-signal memories:
- Repeated bug causes and verified fixes
- Previously implemented features and their files/patterns
- Architecture or API decisions
- UI layout patterns and viewport fixes
- Validation failures and final resolutions
- Reusable project-specific constraints
- Stable user preferences and collaboration habits
- Candidate skills with evidence

Use memory item types:
- `lesson`: a verified pitfall and fix
- `feature`: a previously implemented feature or flow
- `decision`: a technical decision and rationale
- `pattern`: a reusable implementation or UI pattern
- `validation`: validation result that matters later
- `candidate`: possible future skill/rule material
- `note`: useful context that does not fit other types

---

## What Not To Record

Do not record:
- Raw full trajectories
- Every command output
- Ordinary successful steps already covered by rules
- Unverified guesses
- Temporary experiments
- Large code snippets
- Secrets, tokens, credentials, private user data
- Business details from another project

Memory must be curated knowledge, not a log dump.

---

## Preference Recording

User preferences are memory, but they must be treated more carefully than task lessons.

Stable preferences should be written to Markdown first:

```text
memory/global/preferences.md
```

SQLite can also record them for retrieval, using `--type note` and `--project "*"`:

```bash
python scripts/memory-tools.py record-item \
  --project "*" \
  --type note \
  --title "User prefers production-grade implementation" \
  --summary "User repeatedly prefers complete, public-ready, maintainable solutions over MVP or temporary implementations." \
  --tags preference collaboration quality \
  --validation "Observed across multiple system design and implementation tasks."
```

Record a user preference only when:
- The user explicitly states it as a lasting preference, or it appears consistently across tasks
- It affects future collaboration or implementation choices
- It is not tied to one project's private business logic
- It does not include secrets, credentials, private data, or sensitive business context

Do not record:
- One-off instructions
- Temporary task constraints
- Guesses about user taste
- Project-specific business rules as global preference

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

Record a session summary:

```bash
python scripts/memory-tools.py record-session \
  --project <project> \
  --task-summary "<summary>" \
  --key-decisions "<decisions>" \
  --validation-summary "<validation>" \
  --memory-updated
```

Minimum required session record for high-signal tasks:

```bash
python scripts/memory-tools.py record-session \
  --project <project> \
  --task-summary "<what changed>" \
  --key-decisions "<important decisions or none>" \
  --validation-summary "<how it was verified or why it could not be verified>" \
  --memory-updated
```

If the task changed only workflow or rules and no project memory Markdown was updated, omit `--memory-updated` only when no Markdown memory changed. The SQLite session record is still required when the mandatory triggers apply.

---

## Candidate Skill Rules

Candidate skill tracking is allowed. Automatic skill creation is not.

Use candidate tracking when:
- A lesson repeats
- A workflow is likely reusable
- A pattern has clear trigger and boundary
- There is validation evidence

Record candidate:

```bash
python scripts/memory-tools.py candidate-upsert \
  --name <candidate-name> \
  --project "*" \
  --trigger "<when this applies>" \
  --evidence "<why this matters>" \
  --validation "<proof>" \
  --scope "<applies to>" \
  --boundary "<does not apply to>" \
  --tags tag1 tag2
```

Promotion requires:
- Existing Evolution Policy thresholds
- Review Gate
- User confirmation when changing `skills/`, `rules/`, or `AGENTS.md`

---

## Search Before Repeating Work

Before implementing a task that sounds familiar, search memory:

Examples:

```bash
python scripts/memory-tools.py search "login viewport overflow"
python scripts/memory-tools.py search "file upload size display"
python scripts/memory-tools.py search "api auth error handling"
```

This allows the system to remember:
- similar features built before
- related bugs and fixes
- design decisions
- project-specific constraints

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

Memory may evolve into candidates, skills, or rules only through controlled review. The agent may identify stable preferences and reusable lessons, but must not self-upgrade by modifying `AGENTS.md`, `rules/`, or `skills/` without evidence, boundaries, and Review Gate or explicit user approval.

The agent may:
- search memory
- record high-signal memory items
- create or update candidate records
- record session summaries

The agent must not automatically:
- create a new skill file
- modify a skill based only on one memory item
- promote a rule
- modify `AGENTS.md`
- treat database contents as more authoritative than current project files
