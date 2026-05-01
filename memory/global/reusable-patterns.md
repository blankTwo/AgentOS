# Reusable Patterns

## Pattern Template
- Name:
- Trigger:
- Pattern:
- Why:
- Validation: 该模式在当前系统中的落地证据或验证方式
- Caution:

---

## Pattern: Mandatory Gates Before Skills
- Name: Mandatory Gates Before Skills
- Trigger: 每次任务开始，尤其是跨项目、跨技术栈或复杂改动
- Pattern: 先经过 Context / Evidence / Risk / Validation / Memory 五个 gate，再选择 task-layer skill
- Why: gate 保证判断完整，skill 只负责执行，避免一开始被某个技术栈或局部 skill 带偏
- Validation: AGENTS.md 已将 Execution Flow 调整为 gate 链
- Caution: gate 是判断点，不应变成冗长汇报；简单任务可以简短完成判断

## Pattern: Task-Layer Skill Routing
- Name: Task-Layer Skill Routing
- Trigger: 新增功能、修复问题、重构、测试、UI/API/Data/Runtime 等任务
- Pattern: 先识别任务层，再选择对应 skill；技术栈只决定实现约束和可加载 rules
- Why: 避免为 React / Vue / Java / Go / Rust 等技术栈无限新增 stack-specific skill
- Validation: AGENTS.md 已增加 Task Layer Detection；feature-react 已收敛为 React 项目实现辅助
- Caution: 现有项目的技术栈模式仍然必须尊重，不等于忽略框架差异

## Pattern: Evidence Before Diagnosis
- Name: Evidence Before Diagnosis
- Trigger: bugfix、排查、架构判断、性能判断、数据或权限相关决策
- Pattern: 先收集代码位置、日志、复现路径、测试结果、接口返回或截图，再给结论
- Why: 防止基于猜测修改代码，降低误修和扩大影响面的风险
- Validation: bugfix skill 已强化 Evidence Standard 和系统化调试步骤
- Caution: 证据不足时要标明推断，不要把候选原因写成结论

## Pattern: Risk-Based TDD
- Name: Risk-Based TDD
- Trigger: 会改变可观察行为、数据结果、接口契约或业务规则的改动
- Pattern: 核心逻辑、复杂边界、数据处理、已有测试覆盖模块优先测试先行；低风险 UI/文档/配置可用验证替代
- Why: 保留 TDD 的可靠性收益，同时避免对不适合测试先行的任务造成流程负担
- Validation: rules/testing.md 已定义 Must / Recommended / Replacement 场景
- Caution: 不使用 TDD 时必须说明替代验证方式

## Pattern: Worktree Isolation By Risk
- Name: Worktree Isolation By Risk
- Trigger: 大规模重构、架构调整、依赖升级、数据库迁移、并行 agent 工作、当前工作区有冲突风险
- Pattern: 在 Risk Gate 中建议 git worktree 隔离，但不默认强制使用
- Why: worktree 适合隔离高风险或并行工作，不适合小改动和需要当前 IDE 即时预览的任务
- Validation: AGENTS.md 已加入 When Worktree Is Recommended
- Caution: 用户明确要求在当前工作区修改时，不应擅自切换 worktree

## Pattern: Memory Promotion Threshold
- Name: Memory Promotion Threshold
- Trigger: 任务结束后的 Memory Gate
- Pattern: 只有重复出现、已验证、有明确边界的经验才升级；普通成功路径、一次性操作和未验证偏好不写或不升级
- Why: 防止母体系统越沉淀越臃肿，保持 rule / skill 可执行
- Validation: rules/evolution.md 已增加 Do Not Record / Do Not Promote 约束
- Caution: 不要因为“看起来有价值”就升级，必须记录 Trigger / Count / Validation / Scope
