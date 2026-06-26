# Project Agent Entry

This project uses Agent OS from `.agent-os/`.

This root `AGENTS.md` is the project bootstrap entry. Load it first, then delegate to `.agent-os/AGENTS.md`.

## Agent Display

Agent display name: Agent OS

Use this display name at the start of the first user-visible status paragraph and for major status/conclusion paragraphs so the user can see Agent OS is active.

Before starting any task:
1. Read `.agent-os/AGENTS.md`.
2. Follow `.agent-os/context/`, `.agent-os/workflows/`, `.agent-os/rules/`, `.agent-os/skills/`, `.agent-os/tools/`, and `.agent-os/memory/`.
3. Prefer project-local `.agent-os/skills/<skill>/SKILL.md` over global user-level skills when both exist.
4. Treat this repository root as the user project.
5. Keep project-specific decisions in `.agent-os/memory/projects/{project}.md`.
6. Do not modify `.agent-os/AGENTS.md` unless the user explicitly asks to upgrade Agent OS itself.

Project-specific rules can be added below this line.
