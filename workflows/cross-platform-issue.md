# Cross-Platform Issue Workflow

Use when behavior differs across PC, mobile web, app, mini program, environment, role, tenant, or client version.

## Examples

- PC request succeeds, app request returns 500.
- Web login works, mini program login fails.
- Admin page works locally but fails in production.

## User-Visible Output Before Action

Output a comparison-based diagnostic plan before code changes. State whether mutation is authorized.

Read-only diagnosis is the default when the user asks to investigate, compare, inspect, or locate the cause without explicitly asking for a fix.

```text
This is a read-only cross-platform diagnosis. I will compare PC and app request path, headers, auth/session, payload, environment, and backend logs, then report the root cause and recommended fix. I will not modify files unless you approve the fix.
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
5. If the request is read-only diagnosis, stop before file mutation and report evidence, root cause or candidate causes, recommended fix, risk, and validation plan.
6. If fix is authorized, apply the smallest fix.
7. Verify both passing and previously failing platforms.

## Rules

- Do not patch one platform blindly.
- Do not modify files during read-only diagnosis.
- Do not assume same endpoint means same contract.
- Keep compatibility with the already passing platform unless the user asks for a contract change.

