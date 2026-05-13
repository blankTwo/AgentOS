# Enhanced Memory Rules

## Goal
Add Hermes-like long-term memory and retrieval while keeping Codex Mother System lightweight, reviewable, and controlled.

This rule enhances Memory Gate. It does not replace Markdown memory, Evolution Policy, or Review Gate.

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

If `scripts/memory-tools.py` or `memory/schema.sql` is unavailable, continue using Markdown memory.

---

## Context Gate Enhancement

When a task resembles prior work, prior bugs, repeated UI patterns, architecture decisions, or unclear historical context:

1. Search project memory Markdown.
2. If `scripts/memory-tools.py` and `memory/schema.sql` exist, search SQLite memory:

```bash
python scripts/memory-tools.py search "<query>" --project <project>
```

The first search may create `memory/index.db` automatically. This is expected. The database remains local and must not be committed.

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
