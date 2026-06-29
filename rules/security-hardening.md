# Security Hardening

## Secret Handling
- Do not store secrets, tokens, credentials, private keys, or raw sensitive payloads in memory, runtime records, docs, or logs.
- Run `runtime-security-check` before release, distribution, or team handoff.
- If a secret-like value is found, treat it as a blocker until it is removed or confirmed as a safe placeholder.

## Permission Policy
- Tool execution must prefer the Tool Runtime allowlist.
- Use `--allow-unsafe` only for explicit user-approved commands and record the reason.
- High-risk filesystem, network, dependency, release, migration, auth, permission, and production commands require Risk Gate and Validation Gate evidence.

## Sandbox Strategy
- Prefer project-local execution with bounded workspace paths.
- Keep runtime databases and generated local state out of commits.
- For large refactors, dependency upgrades, database migrations, or experimental work, recommend git worktree isolation.
- Never use destructive cleanup as a default validation step.
