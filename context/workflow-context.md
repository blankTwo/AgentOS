# Workflow Context

Workflow Context selects the operating path for the task.

## Selection Inputs

Use:

- task type
- business impact
- capability state
- platform scope
- contract risk
- language context
- evidence sufficiency
- risk chain
- user instruction

## Default Workflow Mapping

| Situation | Workflow |
| --- | --- |
| local low-risk style/copy/config change | Simple Change |
| unclear bug or behavior mismatch | Bug Diagnosis |
| PC/app/mobile/environment difference | Cross-Platform Issue |
| new or missing capability | Feature Implementation |
| API, schema, auth, quota, billing, or compatibility work | API Contract Change |
| AGENTS/rules/skills/runtime/memory changes | Agent OS Evolution |

When multiple workflows apply, choose the workflow with the highest risk and strongest evidence requirement.
