# Bug Diagnosis Workflow

Use for errors, regressions, abnormal behavior, state mismatch, or unclear root cause.

## Diagnosis Modes

Bug Diagnosis has two modes:

- Read-only diagnosis mode: use when the user asks to investigate, analyze, inspect, locate the cause, review, or otherwise understand a bug without explicitly asking for a fix.
- Fix-authorized mode: use only when the user explicitly asks to fix, modify, implement, directly handle, or approves a proposed fix after diagnosis.

Read-only diagnosis is the default for unclear user intent.

## User-Visible Output Before Action

Before diagnostic commands or code inspection, output a diagnostic plan that states whether mutation is authorized.

Read-only example:

```text
This is a read-only diagnosis task. I will trace the failing path, compare expected and actual behavior, collect code/log evidence, and report the root cause plus a recommended fix. I will not modify files unless you approve the fix.
```

Fix-authorized example:

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
5. If in read-only diagnosis mode, stop before file mutation and report:
   - confirmed evidence
   - proven root cause or candidate causes
   - recommended fix
   - risk and validation plan
   - whether approval is needed before changing files
6. If fix is authorized and the diagnostic plan, review, or verification evidence needs a durable project document, write it under `docs/agent-os/plans/`, `docs/agent-os/reviews/`, or `docs/agent-os/verification/` in the user project.
7. If fix is authorized, make the smallest behavior-preserving fix.
8. Validate the failing path and relevant adjacent path.
9. Run Documentation Gate: update troubleshooting docs, verification records, review notes, or project docs when the bug changes known behavior, setup, operations, or future diagnosis steps.
10. Record reusable lessons when root cause is meaningful or repeatable and mutation/memory recording is authorized by the selected gates.

## Rules

- Do not modify behavior before collecting enough evidence.
- Do not modify files during read-only diagnosis.
- A user redirect such as "also check this upstream method" keeps the current authorization mode; it does not imply permission to patch.
- Do not call a guess a root cause.
- If evidence is insufficient, state what is missing and continue diagnosis.
- If validation fails twice, stop expanding and reassess the diagnosis.
- Do not write diagnostic project documents under `.agent-os/`.
- Do not finish a bugfix without deciding whether the root cause, workaround, or verification path needs documentation.
