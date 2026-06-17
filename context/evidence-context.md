# Evidence Context

Evidence Context determines whether the agent can act or must diagnose first.

## Evidence Is Sufficient When

- the target file or code path is known
- expected behavior is clear
- current behavior is observed or directly inferable from code
- risk is local and bounded
- validation path is executable

## Evidence Is Insufficient When

- root cause is unclear
- behavior differs across platforms, roles, environments, or clients
- error logs are missing for a reported bug
- a feature may already exist in partial or broken form
- API/data/auth/quota/payment behavior may be involved
- multiple services or repositories may be involved

## Required Behavior

When evidence is insufficient:

1. State what is known.
2. State what is unconfirmed.
3. Output a diagnostic plan.
4. Collect evidence before modifying behavior.

Do not turn guesses into code changes.

