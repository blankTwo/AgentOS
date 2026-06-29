---
name: write-tests
version: 1.0.0
description: Use to add tests for existing logic or create regression coverage for new behavior.
---

# When to Use
- The user asks for tests.
- A bugfix needs regression protection.
- Core business logic lacks coverage.
- Refactoring needs behavior protection.
- New logic has meaningful edge cases.

# Steps
1. Identify the behavior under test.
2. List the main scenarios.
3. List critical boundaries and failures.
4. Write the smallest effective tests.
5. Avoid asserting implementation details when behavior is enough.
6. Make failures easy to diagnose.

# Output
- Test coverage scope.
- Key assertions.
- Command used to run tests.
- Remaining uncovered risk.

## TDD Use
- Prefer test-first for core business logic, data handling, and complex edge cases.
- For bugfixes, add the smallest regression test after root cause is confirmed.
- UI visual changes and documentation can use targeted validation instead.

## Test Quality
- Tests should prove behavior, not mirror implementation.
- Keep fixtures narrow and readable.
- Avoid brittle snapshots unless the project already relies on them.
