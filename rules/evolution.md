# Evolution Rules

## memory -> skill
满足全部条件时，允许从 memory 升级为 skill：
- 在同一项目重复出现 >= 2 次，或多个项目都出现
- 有明确触发条件
- 有明确步骤
- 可被重复执行
- 已被验证有效
- 已记录最小证据：Trigger / Count / Validation / Scope

## skill -> rule
满足全部条件时，允许从 skill 升级为 rule：
- 多个项目可复用
- 已稳定
- 不依赖强业务语义
- 作为规范比作为流程更合适

## Do Not Promote
以下内容不得升级：
- 一次性 workaround
- 强业务耦合技巧
- 仍存在明显争议的做法
- 缺少验证的经验
- 普通成功路径，没有形成可复用模式
- 只适用于单一技术栈但没有跨项目证据的实现细节
- 为了“显得完整”而补充的抽象规则

## Do Not Record
以下内容通常不需要写入 memory：
- 没有复用价值的临时操作
- 已由现有 rules / skills 覆盖的普通流程
- 没有新决策、新坑点、新约束的信息
- 用户明确表示只是一次性尝试或临时验证

## Promotion Output
升级时必须说明：
- 来源
- 为什么值得升级
- 适用范围
- 风险
- 触发条件
- 出现次数
- 验证方式

## Evidence Preference
演化记录优先使用结构化字段，而不是只写主观判断：
- Trigger: 在什么任务或场景下触发
- Count: 已出现次数，尽量写明确数字
- Validation: 通过什么验证证明有效
- Scope: 适用于哪些项目/模块/边界
- Candidate: 建议停留在 memory、升级为 skill，还是升级为 rule
