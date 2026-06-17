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
5. Modify server/client/data code in the narrowest scope.
6. Preserve quota, billing, auth, and frontend behavior unless explicitly changed.
7. Validate contract and main business path.
8. Record memory for contract decisions.

## Rules

- Do not change API shape silently.
- Do not change quota, billing, or auth side effects unless requested and planned.
- Do not infer backend behavior from frontend names alone.
- Original unchanged flows must be verified when compatibility is promised.
