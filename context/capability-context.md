# Capability Context

Capability Context determines whether the requested capability already exists and whether its chain is usable.

## States

| State | Meaning |
| --- | --- |
| complete | Frontend/API/backend/data-state path and verification evidence exist. |
| partial | Some pieces exist, but the full chain is incomplete. |
| broken-chain | Pieces exist but are not connected correctly. |
| absent | No meaningful implementation exists. |
| unconfirmed | Evidence is insufficient to classify safely. |

## Evidence Sources

Use stronger evidence first:

1. current code paths
2. tests and verification records
3. API clients and backend routes
4. schema, data models, stores, migrations
5. project memory
6. documentation

Documentation and memory may guide investigation, but they do not prove the current implementation exists without code evidence.

## Workflow Impact

- `complete` plus low-risk local change may use Simple Change Workflow.
- `partial`, `broken-chain`, `absent`, or `unconfirmed` must use a planning or diagnostic workflow.
- Capability chain work must not start from keyword guessing.

