# Language Context

Language Context decides which language should be used for artifacts the agent writes.

## Core Boundary

Agent OS model-facing files should use English by default:

- `.codex/AGENTS.md`
- `.codex/context/`
- `.codex/workflows/`
- `.codex/rules/`
- `.codex/skills/`
- `.codex/tools/`

User project artifacts must follow the existing project language and the user's language unless the user explicitly asks otherwise.

## User Project Artifacts

Follow project/user language for:

- business docs
- docs headings
- decision records
- project README sections
- inline comments
- UI copy
- error messages
- commit messages
- memory written for a specific business project

## Detection Order

Use this order:

1. explicit user instruction
2. surrounding file language
3. existing project docs language
4. current conversation language
5. repository conventions

## Mixed-Language Rule

Do not impose English headings on a Chinese business document only because Agent OS model-facing files use English.

Bad:

```md
# Detection Service Ownership

## Current Decision

[Chinese business prose continues here.]
```

Good:

```md
# [Chinese heading matching the project language]

## [Chinese section heading matching the project language]

[Chinese business prose continues here.]
```

English technical identifiers, repository names, API names, and code symbols should remain unchanged.

## When To Ask

Ask the user only when language choice is materially ambiguous and the artifact will be user-facing or long-lived.
