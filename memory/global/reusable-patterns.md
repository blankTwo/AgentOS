# Reusable Patterns

## Pattern Template

- Trigger:
- Scope:
- Steps:
- Validation:
- Boundary:

## Pattern: Mandatory Gates Before Skills

- Trigger: Any engineering task.
- Scope: Context, Evidence, Risk, Planning, Validation, Memory, and Runtime gates.
- Steps: Detect project, stack, task layer, and risk before selecting skills.
- Validation: Final response must state validation and memory decisions.
- Boundary: Simple L1 tasks may complete gates briefly.

## Pattern: Task-Layer Skill Routing

- Trigger: Selecting implementation workflow.
- Scope: UI, API, Data, Integration, Runtime, Test, Bugfix, Refactor.
- Steps: Choose by task layer first; use stack only as implementation context.
- Validation: Selected skill rationale matches task layer.
- Boundary: Do not create stack-specific skills without repeated evidence.

## Pattern: Evidence Before Diagnosis

- Trigger: Bugfix, incident, regression, architecture, data, permission, or performance decisions.
- Scope: All diagnosis and high-impact decisions.
- Steps: Gather code, logs, output, tests, or observable behavior before conclusions.
- Validation: State proven facts versus inference.
- Boundary: If evidence is unavailable, document the missing evidence and minimal validation path.

## Pattern: Risk-Based TDD

- Trigger: Core logic, data handling, integration, or root-cause bugfix.
- Scope: Tests and validation strategy.
- Steps: Prefer test-first or regression tests when risk is meaningful.
- Validation: Test fails before fix or proves final behavior.
- Boundary: UI visuals and documentation may use targeted validation instead.

## Pattern: Worktree Isolation By Risk

- Trigger: large refactor, architecture change, dependency upgrade, migration, dirty worktree, or parallel-agent work.
- Scope: Git safety.
- Steps: Recommend worktree isolation before risky edits.
- Validation: Worktree or recovery strategy is documented.
- Boundary: Small documentation or low-risk local edits usually do not need worktree.

## Pattern: Memory Promotion Threshold

- Trigger: A lesson appears reusable.
- Scope: memory -> skill -> rule evolution.
- Steps: Record candidate with trigger, count, validation, scope, and boundary.
- Validation: Promotion requires repeated evidence and Review Gate.
- Boundary: One-off workarounds and unverified guesses do not promote.
