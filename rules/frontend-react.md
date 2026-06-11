# Frontend React Rules

## Component Design
- Keep components single-purpose where practical.
- Pages organize sections; business logic should move into hooks, services, or stores.
- Extract complex logic into hooks, services, stores, or pure helpers.

## State
- Separate local state from global state.
- Keep global state centralized.
- Avoid implicit coupling between components.
- Do not mix query/server state with local UI state.

## Data Fetching
- Use the project request layer.
- Keep query keys stable.
- Reflect parameter changes in cache identity.
- Handle error, empty, and loading states explicitly.

## UI
- Ensure logic is correct before polishing visuals.
- Avoid piling complex conditional logic directly in JSX.
- Split complex rendering into child components or pure functions.
