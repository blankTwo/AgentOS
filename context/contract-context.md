# Contract Context

Contract Context identifies whether a task changes an interface that another layer or system depends on.

## Contract Signals

- API path, method, parameters, response shape, error codes
- auth or permission requirements
- quota, billing, credit, or deduction behavior
- database schema, migration, data consistency
- webhook payloads, SDK calls, third-party protocols
- frontend/backend adapter shapes
- backward compatibility requirements

## Required Behavior

For contract work:

1. State the existing contract.
2. State the target contract.
3. State compatibility strategy.
4. State affected callers and non-callers.
5. State validation path.
6. State rollback or recovery when risk is high.

Contract records or runtime policy decisions do not replace a visible compatibility plan.

