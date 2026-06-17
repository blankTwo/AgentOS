# Simple Change Workflow

Use for local, low-risk, well-understood changes.

## Examples

- change page text color
- update copy
- update local docs wording or headings
- adjust local spacing
- fix a small docs typo
- change a local config value with obvious impact

## Entry Criteria

All must be true:

- goal is explicit
- impact is local
- behavior is already understood
- no unclear root cause
- no API, data, auth, quota, payment, state-flow, cross-platform, cross-service, or production risk

## User-Visible Output Before Action

One concise sentence is enough:

```text
I will update the target text color using the existing design token and run a quick render/build check.
```

Do not output a heavy structured plan for simple work.

## Execution

1. Locate the smallest affected file set.
2. Check Language Context for docs, copy, comments, or user-facing text.
3. Make the minimal change.
4. Run the narrowest useful validation.
5. Report the change and validation result.

## Escalation

Escalate to another workflow if:

- the target is unclear
- behavior is not understood
- the change touches shared components or contracts
- validation reveals broader impact
