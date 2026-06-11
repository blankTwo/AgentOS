# Evolution Rules

## memory -> skill
Promote memory to a skill only when all conditions are met:
- Trigger: the scenario is clear and answers "when to use this".
- Count: repeated at least twice in one project or across projects.
- Validation: reproducible evidence exists; subjective judgment is not enough.
- Scope: applicable and non-applicable boundaries are clear.
- Boundary: it does not swallow other skill or rule responsibilities.
- Reusable: it can be executed repeatedly without business-specific context.

## skill -> rule
Promote a skill to a rule only when all conditions are met:
- The skill has run stably.
- It is reusable across projects, usually with evidence from at least three projects or equivalent proof.
- It does not depend on strong business semantics.
- It works better as a standard than as a workflow.
- It is not obviously controversial.

## Candidate Marker
When evidence is insufficient but the lesson may be valuable, keep it as:
- `[candidate-skill]`
- `[candidate-rule]`

Candidate records must include:
- Trigger
- Count
- Validation
- Scope
- Boundary

A candidate is not a promotion promise. Re-evaluate it when it appears again.

## Do Not Promote
Do not promote:
- one-off workarounds
- strongly business-coupled techniques
- controversial practices
- unvalidated experience
- ordinary success paths without a reusable pattern
- implementation details limited to one stack without cross-project evidence
- abstract rules added only to look complete

## Do Not Record
Usually do not record:
- temporary operations without reuse value
- routine flows already covered by rules or skills
- information without new decisions, pitfalls, or constraints
- explicitly one-off experiments
- unverified guesses or temporary preferences
- details useful only for the current filename or directory

## Promotion Output
When promoting, state:
- source
- why promotion is justified
- scope
- risk
- trigger
- count
- validation method

## Evidence Preference
Use structured evidence:
- Trigger
- Count
- Validation
- Scope
- Boundary
- Candidate decision

## Alignment With Change Policy
- memory -> skill must satisfy this file's thresholds.
- skill -> rule must satisfy this file's thresholds.
- Changes to existing rules must explain why the result remains stable, executable, and safe for existing projects.
- Do not promote candidate experience into rules or skills just to look complete.
