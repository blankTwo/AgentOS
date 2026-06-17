# Risk Context

Risk Context determines how much visible planning, recovery, review, and validation are required.

## Risk Chain

Assess what can break if the agent is wrong:

- user-visible flow
- API callers
- app or platform compatibility
- auth, permissions, quota, payment
- data integrity
- production config
- build or release process
- performance, concurrency, or cache behavior
- Agent OS rules, skills, runtime, or memory policy

## Output Depth

| Risk | User-visible output before action |
| --- | --- |
| Low | one-sentence execution intent |
| Medium | short plan and validation method |
| High | structured plan with risks, validation, and recovery |
| Critical | structured plan, recovery, review decision, and explicit approval boundary when needed |

Internal risk scoring is allowed, but user-visible intent is always required.

