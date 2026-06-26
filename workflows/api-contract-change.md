# API Contract Change Workflow

Use for API, backend behavior, schema, auth, quota, billing, error code, adapter, or compatibility changes.

## User-Visible Output Before Action

Output a structured plan before implementation:

- goal
- existing contract
- target contract
- affected callers
- non-affected callers
- compatibility strategy
- risks
- rollback/recovery
- validation method

## Execution

1. Identify existing request/response/auth/quota/error behavior.
2. Identify all callers and adapters.
3. Define compatibility strategy.
4. Apply Language Context for decision docs, comments, and business documentation.
5. If the contract decision needs a durable project document, write it under `docs/agent-os/decisions/` in the user project.
6. Modify server/client/data code in the narrowest scope.
7. Preserve quota, billing, auth, and frontend behavior unless explicitly changed.
8. Validate contract and main business path.
9. Run Documentation Gate: update API docs, README, decision records, verification records, or migration notes when the contract, callers, compatibility, auth, quota, errors, or operational behavior changed.
10. Record memory for contract decisions.

## Rules

- Do not change API shape silently.
- Do not change quota, billing, or auth side effects unless requested and planned.
- Do not infer backend behavior from frontend names alone.
- Original unchanged flows must be verified when compatibility is promised.
- Do not write project contract decisions under `.agent-os/`.
- Do not finish a contract change without documenting the new contract or explicitly stating why existing docs remain accurate.
