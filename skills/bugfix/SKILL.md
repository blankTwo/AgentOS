---
name: bugfix
version: 1.0.0
description: Use to diagnose errors, abnormal behavior, failed edge cases, inconsistent state, and regressions; fix only when mutation is explicitly authorized.
---

# When to Use
- Runtime errors or build errors.
- UI or API behavior differs from expectation.
- State inconsistency.
- Edge-case failures.
- Regressions after a change.
- User reports that something does not work.

# Steps
1. Classify mutation authorization using the Agent OS Mutation Authorization Gate.
2. Reproduce or locate the failure signal.
3. Collect evidence: error text, logs, affected files, tests, screenshots, or observed behavior.
4. Identify the root cause before changing code.
5. If the request is read-only diagnosis, stop before file edits and report the evidence, root cause or candidate causes, recommended fix, risk, and validation plan.
6. If fix is authorized, make the smallest complete fix that addresses the root cause.
7. Add or run regression validation when a fix is applied.
8. Record the lesson when the bug is likely to recur and memory recording is allowed.

# Output
- Confirmed symptom.
- Root cause.
- Fix summary, or recommended fix if no mutation was authorized.
- Validation result, or validation plan if no mutation was authorized.
- Remaining risk.

## Evidence Standard
- State what is proven and what is inferred.
- Do not patch from filename or keyword guesses.
- If the root cause is unclear, keep investigating before editing.
- Do not edit source, tests, docs, config, or memory for diagnosis-only requests such as "排查一下", "分析一下", "定位原因", or "看看为什么".

## Regression Protection
- Prefer a failing-before / passing-after test when practical.
- If tests are not available, provide a targeted manual validation path.

# Memory Usage
Record a memory item when the bug has a clear root cause, repeated symptom, project-specific pitfall, or future diagnostic value.

Do not update project memory during read-only diagnosis unless the user explicitly asks to record the finding.
