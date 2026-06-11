---
name: api-change
description: Use for API Layer changes, including endpoints, request parameters, response structures, authentication, error handling, service logic, data writes, and frontend/backend contracts.
---

# When to Use
- Add a new endpoint.
- Modify request parameters or response shape.
- Change auth, permission, or error semantics.
- Change service logic behind an API.
- Adjust frontend/backend contract behavior.
- Touch API-related data writes or consistency logic.

# Steps
1. Identify the affected API contract: route, method, request, response, auth, errors, and side effects.
2. Inspect existing API patterns before adding new structure.
3. Check callers and consumers before changing the contract.
4. Prefer backward-compatible changes when reasonable.
5. Update validation or tests that prove the contract.
6. Record API decisions when the contract affects future work.

# Output
- Contract summary.
- Impacted callers and files.
- Data or auth implications.
- Validation performed.
- Remaining compatibility risks.

## Contract Discipline
- Do not silently change a public response shape.
- Do not weaken auth or permission checks.
- Do not create a frontend-only API assumption without backend evidence.
- For cross-layer changes, verify both the client call and backend handler.

## Validation
- Prefer API tests, integration tests, or endpoint smoke checks.
- For auth or permission changes, include negative cases.
- For data writes, verify persistence and rollback or recovery assumptions.
