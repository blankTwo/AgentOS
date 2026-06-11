# Coding Style Rules

## General
- Prefer TypeScript when the project uses it.
- Prefer explicit types.
- Avoid unnecessary `any`.
- Prefer clear naming over abbreviations.
- Keep functions single-purpose.
- Avoid deep nesting.
- Avoid duplicated logic.

## Architecture
- Separate UI, state, and data-request concerns where possible.
- Centralize API calls through request helpers.
- Split constants, types, and utilities by responsibility.
- Do not accumulate complex business logic inside UI components.

## Change Preference
- Solve the requested goal completely while keeping impact bounded.
- Prefer a local closed loop over leaving temporary state.
- Refactor when the root problem is structural.
- Refactoring must not silently change external behavior.

## Readability
- Readability beats cleverness.
- Reduce hidden behavior.
- Comments should explain why, not restate what a line does.
