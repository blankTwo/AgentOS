# Backend Node Rules

## API
- Validate input before service logic.
- Use consistent error response format.
- Do not expose internal exceptions to callers.
- Keep controller / service / repository boundaries clear.

## Data
- Make database operation boundaries explicit.
- Prefer transactions for mutating multi-step operations.
- Evaluate compatibility for schema or model changes.

## Reliability
- Logs must support diagnosis.
- Avoid silent failure.
- External dependencies need failure branches.
