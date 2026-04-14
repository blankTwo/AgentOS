# Testing Rules

## General
- 任何非极小改动都应考虑验证
- bugfix 至少要验证复现路径与修复路径
- feature 至少验证主流程与关键边界
- refactor 至少验证行为不变

## Validation Priority
1. 编译 / 类型检查
2. 单元测试
3. 集成测试
4. 手工关键路径验证

## When Tests Are Missing
如果项目没有测试：
- 先给出最小验证方案
- 说明风险点
- 必要时建议补测试

## Output
验证说明至少包含：
- 验证什么
- 怎么验证
- 风险还剩什么
