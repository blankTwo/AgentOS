# Agent OS Evolution Workflow

Use for changes to AGENTS.md, rules, skills, runtime, memory policy, context, workflows, or Agent OS documentation.

## User-Visible Output Before Action

Output a structured plan before editing:

- objective
- affected Agent OS layer
- files to change
- compatibility or migration impact
- validation method
- Review Gate decision
- memory recording plan

## Execution

1. Identify the exact Agent OS layer: AGENTS, context, workflow, rule, skill, runtime, memory, docs, tests.
2. Confirm the change is stable enough for a rule/workflow/skill, or keep it as a candidate.
3. Make scoped edits.
4. Run relevant tests and syntax/frontmatter checks.
5. Run Documentation Gate: decide required README, AGENTS, context, workflows, rules, tools, installer bootstrap, and test documentation updates; delegate documentation writing when available and review the diff before final response.
6. Run Review Gate or equivalent consistency review.
7. Run Memory Gate: delegate structured memory recording to a Memory Recorder sub-agent when policy, runtime, workflow, or reusable behavior changes.

## Rules

- Do not modify AGENTS/rules/skills/workflows based on one weak anecdote unless the user explicitly asks.
- Do not let a workflow duplicate a skill; workflows define sequence, skills define task methods.
- Do not let Runtime records replace user-visible workflow output.
- Do not apply Agent OS English-language policy to user project business docs; project artifacts follow Language Context.
- Do not finish Agent OS behavior changes while README, installer bootstrap, tests, or tool docs still describe the old behavior.
