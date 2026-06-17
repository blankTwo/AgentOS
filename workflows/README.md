# Workflow Layer

The Workflow Layer defines how the agent acts after context is understood.

Rules define standards. Skills provide task-specific methods. Runtime records state. Workflows define the operating sequence and user-visible output.

## Workflow Contract

Every workflow must define:

- when to use it
- required user-visible output before action
- evidence requirements
- language-context requirements when writing project artifacts
- execution sequence
- validation requirements
- memory/evolution requirements

## Universal Rule

Before implementation, always provide user-visible execution intent.

- Simple work: one concise sentence is enough.
- Medium-risk work: short plan with validation.
- High-risk work: structured plan with goal, scope, steps, risks, validation, and recovery.
- Diagnostic work: diagnostic plan before code changes.

Runtime records or internal task queues never replace user-visible intent or plan.

## Workflow Selection

Use `context/workflow-context.md` to select the workflow.

Default workflows:

- `simple-change.md`
- `bug-diagnosis.md`
- `cross-platform-issue.md`
- `feature-implementation.md`
- `api-contract-change.md`
- `agent-os-evolution.md`

When workflows overlap, choose the workflow with the highest risk and strongest evidence requirement.
