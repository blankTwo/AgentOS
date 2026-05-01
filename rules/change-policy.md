# Change Policy

## Allowed High Frequency Updates
- memory/global/*
- memory/projects/*

## Allowed With Reason
- rules/*
- skills/*

## Forbidden Automatic Updates
- AGENTS.md

## Promotion Standard
只有当某经验满足以下条件，才允许升级：
- 已验证
- 可复用
- 有明确边界
- 非一次性技巧
- 非强业务耦合

## Skill / Rule Maintenance
- 修改 skill 前必须说明复用价值和触发场景
- 修改 rule 前必须说明为什么它已经足够稳定
- 不把单个案例、临时 workaround 或未验证偏好写进 skill / rule
- 优先增强已有 task-layer skill，不因为出现新技术栈就新增 stack-specific skill
- 修改后应检查描述是否仍准确，避免 skill 触发范围过宽

## Anti-Drift
- 不得为了“更通用”而破坏已有清晰流程
- 不得为了“更智能”而让规则不可执行
- 规则必须简洁、明确、可操作
- 新规则必须能回答“何时触发、如何执行、如何验证”
