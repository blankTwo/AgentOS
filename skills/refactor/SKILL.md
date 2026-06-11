---
name: refactor
description: Use to improve structure, readability, reuse, responsibility boundaries, and maintainability without changing external behavior.
---

# When to Use
- Duplicated logic.
- Files or functions are too large.
- Responsibilities are unclear.
- Structure is hard to maintain.
- The user explicitly asks to optimize or refactor.
- Behavior should remain the same.

# Steps
1. Define the refactor goal.
2. Mark the impact scope.
3. Confirm the behavior boundary that must not change.
4. Make small verifiable changes.
5. Keep each step testable.
6. Update tests or validation notes when needed.
7. Record stable reusable patterns when they emerge.

# Output
- Refactor goal.
- Impact scope.
- Behavior compatibility statement.
- Maintenance benefit.
- Validation performed.

## Boundaries
- Do not mix unrelated feature work into a refactor.
- Do not change public contracts unless the user requested it.
- Do not rename or move broadly without validation.
