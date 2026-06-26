# Feature Implementation Workflow

Use for new capabilities, missing features, or feature completion.

## User-Visible Output Before Action

Output a plan before implementation unless the feature is clearly local and trivial.

Required plan:

- goal
- current capability state
- impact scope
- implementation steps
- risks
- validation method

## Execution

1. Detect current capability state: complete, partial, broken-chain, absent, or unconfirmed.
2. Inspect existing patterns and adjacent implementations.
3. Apply Language Context for docs, comments, UI copy, and project memory.
4. If a durable implementation plan or task breakdown is needed, write it under `docs/agent-os/plans/` or `docs/agent-os/tasks/` in the user project.
5. Preserve existing contracts and user workflows unless a change is explicit.
6. Implement the smallest complete capability chain.
7. Validate the main path and key boundary.
8. Run Documentation Gate: update README/docs, `docs/agent-os/`, or Agent OS docs when the feature changes usage, behavior, contracts, validation, or maintainability knowledge.
9. Record feature or decision memory when reusable or project-specific.

## Rules

- Do not implement a frontend-only assumption when backend/API evidence is required.
- Do not ship an MVP placeholder when the user asked for a complete feature.
- If capability state is partial, broken-chain, absent, or unconfirmed, use visible planning before editing.
- Do not write project implementation plans or task docs under `.agent-os/`.
- Do not finish a feature change without deciding and reporting whether documentation was updated or why it was unnecessary.
