# Cross-Platform Issue Workflow

Use when behavior differs across PC, mobile web, app, mini program, environment, role, tenant, or client version.

## Examples

- PC request succeeds, app request returns 500.
- Web login works, mini program login fails.
- Admin page works locally but fails in production.

## User-Visible Output Before Action

Output a comparison-based diagnostic plan before code changes:

```text
This is a cross-platform discrepancy. I will compare PC and app request path, headers, auth/session, payload, environment, and backend logs before changing code.
```

## Required Evidence Matrix

Compare:

- URL and route
- method
- query/body payload
- headers and content type
- auth/session/token
- client version and environment
- backend route and logs
- gateway/proxy behavior
- response status, error code, and trace

## Execution

1. Confirm both platform behaviors.
2. Compare request and runtime differences.
3. Trace backend handling for the failing platform.
4. Identify whether the issue is client, gateway, backend, data, auth, or environment.
5. Apply the smallest fix.
6. Verify both passing and previously failing platforms.

## Rules

- Do not patch one platform blindly.
- Do not assume same endpoint means same contract.
- Keep compatibility with the already passing platform unless the user asks for a contract change.

