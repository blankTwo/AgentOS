# Testing Rules

## General
- Any non-trivial change should consider validation.
- Bugfixes must at least validate reproduction and fixed paths.
- Features must validate the main flow and key boundaries.
- Refactors must validate unchanged behavior.
- Validation conclusions must be based on actual results, not plans or impressions.

## Risk-Based TDD
TDD is not globally mandatory, but changes that affect observable behavior, data results, API contracts, or business rules should prefer test-first work.

### Test-First Required Unless Blocked
- New or changed core business logic.
- Permission, money, state machines, data conversion, or complex validation.
- Modules already covered by tests.
- Clear regression fixes when a usable test framework exists.
- Multi-branch utilities or data-processing logic with edge cases.

If test-first is blocked, state the blocker and substitute validation.

### Recommended TDD
- New API behavior or response contracts.
- Behavior-preserving refactors.
- Cross-layer state flows.
- Forms, error handling, and boundary-heavy branches.
- Bugfixes after root cause is confirmed.

### TDD Can Be Replaced By Validation
- Pure visual or layout UI work.
- Documentation, rules, skills, or memory updates.
- One-off scripts or exploratory prototypes.
- Projects without a test foundation when adding one exceeds task risk.
- Low-risk config changes.

If TDD is not used, state the validation method.

## Validation Priority
1. Compile / type check.
2. Unit tests.
3. Integration tests.
4. Manual key-path validation.

## Validation By Task Layer
- UI Layer: visual check, interaction path, responsive behavior, empty/error/loading states.
- API Layer: request parameters, response shape, success path, error path, permission boundary.
- Data Layer: schema, migration, query results, consistency, rollback path.
- Integration Layer: frontend/backend contract, third-party response, retry, timeout, exceptions.
- Runtime Layer: build, startup, environment variables, scripts, deployment, runtime config.
- Test Layer: new tests fail when expected and pass after the fix; tests are stable.
- Bugfix Layer: reproduction path, fix path, related regression path.
- Refactor Layer: unchanged behavior, core path passes, structural goal met.

## When Tests Are Missing
If the project has no tests:
- provide the minimum validation plan
- state risks
- recommend tests when risk justifies it

## Validation Failure Handling
Validation failure is not a final answer. Enter failure handling.

### Failure Evidence
Record:
- failed command, output, logs, or screenshot
- failed path, input, or reproduction steps
- possible relationship to the current change

### Failure Classification
- implementation problem
- test problem
- environment problem
- requirement understanding problem

### Retry Boundary
- First failure: locate root cause, fix narrowly, validate again.
- Second failure: check edge cases, dependencies, task layer, and validation method.
- Three consecutive failures: stop expanding changes, list attempts and causes, reanalyze, and recover or ask for confirmation when needed.

### Unable To Validate
Delivery with risk is allowed only when:
- production config or real credentials are missing
- third-party service, hardware, system version, or network condition cannot be simulated
- large data, long runtime, or external approval is required
- the project truly lacks a test foundation and adding it is outside task risk

These are not valid "unable to validate" reasons:
- a test framework exists but was not run
- local startup, build, or type check is possible but not attempted
- compile, type check, or core path failed but delivery is still claimed

### Partial Pass
- Core path failure blocks completion.
- Core path pass with edge failure requires impact statement and prioritized fix.
- Core path pass with unverifiable external dependency may be delivered with risk and manual validation steps.

### Performance Validation
Performance tasks must state:
- current baseline or observable state
- target or non-regression metric
- validation method: benchmark, profiling, load test, artifact comparison, or manual observation
- reason and substitute method when not quantifiable

## Output
Validation notes must include:
- what was validated
- how it was validated
- result
- remaining risk
