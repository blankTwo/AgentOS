# Bug Diagnosis Workflow

Use for errors, regressions, abnormal behavior, state mismatch, or unclear root cause.

## User-Visible Output Before Action

Before modifying code, output a diagnostic plan:

```text
This is a diagnosis task. I will first reproduce/locate the failing path, compare expected and actual behavior, collect logs or code evidence, identify the root cause, then make the smallest fix and verify the regression path.
```

For non-trivial bugs, include:

- known facts
- unconfirmed assumptions
- diagnostic steps
- validation path

## Execution

1. Clarify expected vs actual behavior.
2. Locate entry points and affected layers.
3. Collect evidence: logs, error text, code path, request/response, tests, screenshots, or observable behavior.
4. State root cause or candidate root cause.
5. Make the smallest behavior-preserving fix.
6. Validate the failing path and relevant adjacent path.
7. Record reusable lessons when root cause is meaningful or repeatable.

## Rules

- Do not modify behavior before collecting enough evidence.
- Do not call a guess a root cause.
- If evidence is insufficient, state what is missing and continue diagnosis.
- If validation fails twice, stop expanding and reassess the diagnosis.

