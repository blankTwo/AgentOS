# Context Layer

The Context Layer determines what situation the agent is facing before it selects a workflow or edits files.

Context is not memory by itself. Context is the current, evidence-based interpretation of the task, project, capability state, business impact, platform surface, contract risk, and uncertainty.

## Required Context Dimensions

Every task should classify these dimensions, with depth scaled to the task:

| Dimension | Question |
| --- | --- |
| Project Context | Which project and project memory apply? |
| Stack Context | Which stack and subproject are affected? |
| Task Context | What kind of task is this: simple change, bug, feature, contract, runtime, refactor, test, or docs? |
| Business Context | Which business flow, user journey, quota, auth, payment, data, approval, content, order, or operational process is affected? |
| Capability Context | Is the requested capability complete, partial, broken-chain, absent, or unconfirmed? |
| Platform Context | Which surfaces are involved: PC, mobile web, app, mini program, admin, backend, job, webhook, third-party service? |
| Contract Context | Are API parameters, response shape, error codes, auth, quota, billing, schema, or compatibility affected? |
| Language Context | Which language should be used for project artifacts, docs, comments, UI copy, and memory? |
| Evidence Context | Is there enough evidence to act, or must the agent diagnose first? |
| Risk Context | What can break if the agent is wrong? |
| Workflow Context | Which workflow should control the next actions and user-visible output? |

## Context Depth

Simple local tasks need a compact context statement.

Example:

```text
Context: local UI style change, low business risk, direct execution with visual/build validation.
```

Unclear, cross-platform, contract, data, auth, quota, payment, or cross-service tasks need explicit context before implementation.

Example:

```text
Context: cross-platform API failure. PC succeeds, app returns 500. Root cause is unconfirmed. This requires diagnostic workflow before code changes.
```

## Output Contract

The agent does not need to print a long context report for every task, but it must make the execution posture visible:

- direct execution for simple, local, understood work
- diagnostic plan for unclear behavior or bugs
- structured plan for feature, contract, data, cross-layer, or high-risk work
- recovery and review decisions for high-risk work

Runtime records, memory hits, or internal notes never replace user-visible context and intent.
