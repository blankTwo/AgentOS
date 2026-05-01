# Testing Rules

## General
- 任何非极小改动都应考虑验证
- bugfix 至少要验证复现路径与修复路径
- feature 至少验证主流程与关键边界
- refactor 至少验证行为不变
- 验证结论必须基于实际结果，不能只写计划或主观判断

## Risk-Based TDD
TDD 不是全局强制，但会改变可观察行为、数据结果、接口契约或业务规则的改动，应优先考虑测试先行。

### Test-First Required Unless Blocked
- 新增或修改核心业务逻辑
- 涉及权限、金额、状态机、数据转换、复杂校验
- 修改已有测试覆盖的模块
- 修复明确回归问题，且项目已有可用测试框架
- 数据处理、算法、工具函数存在多分支或边界条件

若无法测试先行，必须说明阻塞原因，并给出替代验证方式。

### Recommended TDD
- 新增 API 行为或响应协议
- 重构已有逻辑但要求行为不变
- 跨层联动中存在关键状态流
- 表单校验、错误处理、边界分支较多
- bugfix 在确认根因后可补最小回归测试

### TDD Can Be Replaced By Validation
- 纯 UI 视觉或布局调整
- 文档、rules、skills、memory 更新
- 一次性脚本或探索性原型
- 项目没有测试基础，且补测试成本明显超过本次改动风险
- 低风险配置调整

若不使用 TDD，必须说明替代验证方式。

## Validation Priority
1. 编译 / 类型检查
2. 单元测试
3. 集成测试
4. 手工关键路径验证

## Validation By Task Layer
- UI Layer: 视觉检查、交互路径、响应式、空/错/加载状态
- API Layer: 请求参数、响应结构、成功路径、错误路径、权限边界
- Data Layer: schema / migration / 查询结果 / 数据一致性 / 回滚路径
- Integration Layer: 前后端契约、第三方返回、失败重试、超时或异常
- Runtime Layer: 构建、启动、环境变量、脚本、部署或运行时配置
- Test Layer: 新增测试是否能失败后通过，测试是否稳定且覆盖目标行为
- Bugfix Layer: 复现路径、修复路径、相关回归路径
- Refactor Layer: 行为不变、关键路径仍通过、性能或结构目标是否达成

## When Tests Are Missing
如果项目没有测试：
- 先给出最小验证方案
- 说明风险点
- 必要时建议补测试

## Output
验证说明至少包含：
- 验证什么
- 怎么验证
- 验证结果
- 风险还剩什么
