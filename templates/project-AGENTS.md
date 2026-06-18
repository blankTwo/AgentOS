# Project Agent Entry

This project uses Codex Agent OS from `.codex/`.

This root `AGENTS.md` is the project bootstrap entry. Load it first, then delegate to `.codex/AGENTS.md`.

## Agent Display

Agent display name: Agent OS

Use this display name at the start of the first user-visible status paragraph and for major status/conclusion paragraphs so the user can see Codex Agent OS is active.

Before starting any task:
1. Read `.codex/AGENTS.md`.
2. Follow `.codex/context/`, `.codex/workflows/`, `.codex/rules/`, `.codex/skills/`, `.codex/tools/`, and `.codex/memory/`.
3. Prefer project-local `.codex/skills/<skill>/SKILL.md` over global user-level skills when both exist.
4. Treat this repository root as the user project.
5. Keep project-specific decisions in `.codex/memory/projects/{project}.md`.
6. Do not modify `.codex/AGENTS.md` unless the user explicitly asks to upgrade Codex Agent OS itself.

Project-specific rules can be added below this line.
