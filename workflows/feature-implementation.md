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
4. Preserve existing contracts and user workflows unless a change is explicit.
5. Implement the smallest complete capability chain.
6. Validate the main path and key boundary.
7. Record feature or decision memory when reusable or project-specific.

## Rules

- Do not implement a frontend-only assumption when backend/API evidence is required.
- Do not ship an MVP placeholder when the user asked for a complete feature.
- If capability state is partial, broken-chain, absent, or unconfirmed, use visible planning before editing.
