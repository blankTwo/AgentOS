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
5. If the diagnostic plan, review, or verification evidence needs a durable project document, write it under `docs/agent-os/plans/`, `docs/agent-os/reviews/`, or `docs/agent-os/verification/` in the user project.
6. Make the smallest behavior-preserving fix.
7. Validate the failing path and relevant adjacent path.
8. Run Documentation Gate: update troubleshooting docs, verification records, review notes, or project docs when the bug changes known behavior, setup, operations, or future diagnosis steps.
9. Record reusable lessons when root cause is meaningful or repeatable.

## Rules

- Do not modify behavior before collecting enough evidence.
- Do not call a guess a root cause.
- If evidence is insufficient, state what is missing and continue diagnosis.
- If validation fails twice, stop expanding and reassess the diagnosis.
- Do not write diagnostic project documents under `.agent-os/`.
- Do not finish a bugfix without deciding whether the root cause, workaround, or verification path needs documentation.
