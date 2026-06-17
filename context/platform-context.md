# Platform Context

Platform Context identifies which runtime surfaces are affected.

## Platform Signals

- PC web
- mobile web
- native app
- mini program
- admin dashboard
- backend API
- background job
- third-party callback or webhook

## Cross-Platform Rule

If behavior differs by platform, environment, client, role, or tenant, the agent must enter a diagnostic workflow before modifying code.

Example:

```text
PC request succeeds, app request returns 500.
```

Required comparison:

- URL and route
- method
- headers
- auth/session token
- request body
- content type
- client version or environment
- backend logs and error trace
- gateway/proxy behavior

Do not fix cross-platform behavior from assumptions.

