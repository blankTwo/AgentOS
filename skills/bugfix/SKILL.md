---
name: bugfix
description: Use to diagnose and fix errors, abnormal behavior, failed edge cases, inconsistent state, and regressions.
---

# When to Use
- Runtime errors or build errors.
- UI or API behavior differs from expectation.
- State inconsistency.
- Edge-case failures.
- Regressions after a change.
- User reports that something does not work.

# Steps
1. Reproduce or locate the failure signal.
2. Collect evidence: error text, logs, affected files, tests, screenshots, or observed behavior.
3. Identify the root cause before changing code.
4. Make the smallest complete fix that addresses the root cause.
5. Add or run regression validation.
6. Record the lesson when the bug is likely to recur.

# Output
- Confirmed symptom.
- Root cause.
- Fix summary.
- Validation result.
- Remaining risk.

## Evidence Standard
- State what is proven and what is inferred.
- Do not patch from filename or keyword guesses.
- If the root cause is unclear, keep investigating before editing.

## Regression Protection
- Prefer a failing-before / passing-after test when practical.
- If tests are not available, provide a targeted manual validation path.

# Memory Usage
Record a memory item when the bug has a clear root cause, repeated symptom, project-specific pitfall, or future diagnostic value.
