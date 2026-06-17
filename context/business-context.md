# Business Context

Business Context identifies whether a task affects real user or operational behavior.

## Business-Risk Signals

Treat the task as business-impacting when it touches:

- login, registration, session, auth, roles, permissions
- payment, quota, billing, credits, refunds, usage limits
- orders, approvals, publishing, review, compliance, moderation
- content generation, originality checks, risk scoring, labeling, title generation
- data sync, import/export, background jobs, webhooks, third-party APIs
- API contracts used by frontend, app, partner systems, or jobs
- user data, production config, migrations, or irreversible operations

## Required Behavior

For business-impacting tasks:

1. Identify the business flow.
2. Identify upstream and downstream callers.
3. Identify the contract that must remain stable.
4. State whether frontend, backend, data, quota, auth, or third-party behavior changes.
5. Use a workflow that requires visible plan or diagnostic plan before implementation.

## Direct Execution Boundary

Direct execution is allowed only when business impact is absent or clearly local.

Examples:

- changing local UI text color
- fixing copy in a static label
- updating a local docs typo

Direct execution is not allowed when the task changes behavior that users, data, API clients, billing, auth, or operations depend on.

