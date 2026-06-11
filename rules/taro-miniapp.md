# Taro / Mini Program Rules

## Structure
- Separate page logic from cloud-function calls.
- Prefer one-way data flow.
- Keep pull-to-refresh, infinite scroll, and pagination state clearly separated.

## Cloud
- Define cloud-function input and output shapes clearly.
- Validate fields before database writes.
- Pagination APIs must clearly define page / pageSize / cursor strategy.

## UI Logic
- Avoid putting excessive state directly into page files.
- Extract shared logic into hooks, utilities, or services first.
