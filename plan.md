# Agent OS 2.0 能力升级计划

## 目标

Agent OS 2.0 的目标不是增加更多 skill，而是把 Agent 从“规则驱动的执行系统”升级为“可调度、可审计、可恢复、可演化的 Agent 操作系统”。

核心定义：

```text
Agent OS = Goal Management + Event-driven Kernel + Runtime + Knowledge System + Governance + Execution Pipeline
```

升级后的系统需要具备：

- 能明确管理目标、子目标、成功标准和阻塞状态。
- 能用事件驱动 Kernel 调度任务，而不是只靠单次 prompt 或命令式脚本。
- 能统一调度 Model、Skill、Tool、Sub-agent 等运行时。
- 能把 Context、Memory、Docs、Decision、Workspace 状态组织成 Knowledge System。
- 能通过 Governance 管理计划、风险、权限、Review、Rollback、Promotion。
- 能把 Plan、Act、Observe、Verify、Recover、Document、Learn 串成稳定 Execution Pipeline。

---

## 当前状态总结

| 能力域 | 当前状态 | 结论 |
| --- | --- | --- |
| Goal Management | 已有 `agent_goals`、task queue、runtime records | 有雏形，但缺完整生命周期 |
| Event-driven Kernel | 主要依赖规则和命令式 runtime | 基本缺失 |
| Runtime | 有 `agent-runtime.py`，可记录任务、策略、验证、恢复 | 有基础，但还不是统一 Runtime |
| Knowledge System | 有 Markdown memory、SQLite memory、Context Gate、Documentation Gate | 有基础，但缺索引、排序、过期和冲突检测 |
| Governance | 有 Risk Gate、Planning Gate、Review Gate、Memory Gate、Documentation Gate | 基础较好，但缺自动化治理执行 |
| Execution Pipeline | 有 gates 和 workflows | 有流程，但还不是状态机驱动 pipeline |
| Verification | 有验证规划和安全命令执行 | 有雏形，缺多类型验证编排 |
| Reflection / Learning | 有 candidate 和 improvement review | 偏记录，缺真正反思和学习闭环 |
| Workspace OS | 有 workspace root、git dirty、文件扫描等局部能力 | 缺统一工作区模型 |
| Observability | 有 SQLite runtime report | 缺事件日志、指标和可视化 |

---

## 完整能力清单

### 1. Goal Management

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Goal Lifecycle | 管理目标创建、计划中、执行中、验证中、完成、阻塞、取消、恢复 | 有雏形 | 目标状态可追踪、可恢复、可审计 |
| Success Criteria | 明确成功标准和验收条件 | 有雏形 | 每个 L2+ goal 必须有可验证成功标准 |
| Sub-goal Decomposition | 把复杂目标拆成子目标和任务队列 | 有雏形 | 支持父子目标、依赖关系、完成条件 |
| Cross-turn Continuation | 跨轮次继续未完成任务 | 弱 | 能从 runtime state 恢复上下文和下一步 |
| Blocker Handling | 记录阻塞原因、等待条件、恢复策略 | 弱 | 阻塞状态有原因、有 owner、有恢复条件 |
| Goal Audit | 汇总目标过程、关键决策、验证和结果 | 弱 | 每个复杂 goal 可生成完整审计报告 |

### 2. Event-driven Kernel

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Event Bus | 把用户输入、任务完成、验证失败、文件变化、记忆更新等事件化 | 缺 | 所有关键动作都产生标准事件 |
| Event Types | 定义 `UserRequest`、`ContextReady`、`PlanApproved`、`TaskCompleted`、`VerificationFailed` 等事件 | 缺 | 事件类型稳定、可路由、可记录 |
| State Machine | 用状态驱动 plan、execute、verify、recover、deliver | 缺 | Goal 和 Task 都由状态机推进 |
| Scheduler | 决定下一步做什么、谁来做、何时做 | 弱 | 根据状态、风险、验证结果选择下一步 |
| Priority / Retry | 管理任务优先级、重试次数、失败升级 | 缺 | 验证失败、工具失败、阻塞都有明确重试策略 |
| Resource Manager | 管理模型、工具、命令、并发、预算、超时 | 缺 | 高风险或高成本操作可控、可限流 |
| Kernel API | 对外提供统一入口，让 CLI、插件、其他 AI runtime 调用 | 缺 | Kernel 能作为 Agent OS 的主入口 |

### 3. Runtime

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Model Runtime | 抽象 GPT、Claude、Gemini、Qwen、DeepSeek 等模型 | 缺 | 不同模型可通过统一 adapter 调用 |
| Skill Runtime | 统一加载、校验、执行、记录 skill | 弱 | skill 有 manifest、输入输出、验证和失败类型 |
| Tool Runtime | 统一 Shell、Git、Browser、API、文件操作执行策略 | 弱 | 工具调用可审计、可限权、可分类失败 |
| Sub-agent Runtime | 支持 planner、executor、reviewer、verifier、memory-recorder 协作 | 弱 | 子 agent 可调度、有边界、有结果合并 |
| Runtime Trace | 记录每次运行步骤、输入摘要、输出摘要、耗时和结果 | 弱 | 复杂任务可完整回放和审计 |
| Failure Classification | 分类环境失败、权限失败、实现失败、测试失败、模型失败 | 有雏形 | 每类失败有标准处理策略 |
| Runtime Isolation | 控制并发、隔离临时文件、避免任务互相污染 | 缺 | 多任务或多 agent 执行不互相踩踏 |

### 4. Context System

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Context Builder | 构建项目、栈、任务、业务、能力、契约、风险上下文 | 有 | 输出结构化 context object |
| Context Ranking | 判断哪些上下文最重要 | 缺 | 优先加载高相关、高可信、未过期上下文 |
| Context Compression | 压缩长文档、历史记录、项目结构 | 缺 | 大项目上下文可控，不污染窗口 |
| Context Cache | 缓存稳定上下文，减少重复扫描 | 缺 | 项目结构、依赖、规则摘要可缓存 |
| Context Freshness | 判断上下文是否过期 | 缺 | 文件变更后自动失效相关缓存 |
| Context Conflict Detection | 发现 memory、docs、code、runtime 之间冲突 | 缺 | 冲突时要求重新取证，而不是直接相信旧信息 |

### 5. Workspace OS

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Project Index | 建立文件、目录、模块、入口、配置索引 | 弱 | 可快速定位项目结构和主要模块 |
| Git State Model | 建模分支、diff、未提交、冲突、ahead/behind | 弱 | Risk Gate 可直接使用工作区风险 |
| Dependency Graph | 建立模块、包、接口、页面、服务依赖关系 | 缺 | 改动前能判断影响范围 |
| Impact Analysis | 判断改动会影响哪些模块、接口、页面、测试和文档 | 弱 | Planning Gate 能基于影响范围升级 |
| Workspace Snapshot | 执行前后快照、恢复依据 | 弱 | Recovery Gate 能基于快照回滚 |
| Docs Index | 索引 README、docs、docs/agent-os、决策和验证记录 | 缺 | Documentation Gate 能判断文档是否可能过期 |
| Runtime State View | 把 goal、task、policy、verification、memory 合成工作区状态 | 缺 | Kernel 能读取统一 workspace state |

### 6. Knowledge System

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Memory Retrieval | 检索历史功能、坑点、决策、偏好 | 有 | 与 Context Gate 和 Capability Gate 深度结合 |
| Memory Index | Markdown 和 SQLite 结构化索引 | 有 | 搜索、导入、记录、去重更稳定 |
| Memory TTL | 记忆有效期和过期策略 | 缺 | 易过期信息需要重新验证 |
| Decision Index | 决策记录可检索 | 弱 | API、架构、业务决策可被快速召回 |
| Documentation Index | README/docs/agent-os 文档索引 | 缺 | 文档能参与上下文和过期判断 |
| Knowledge Conflict Detection | 检测 memory/docs/code/runtime 冲突 | 缺 | 冲突信息不能直接作为事实 |
| Knowledge Compression | 把多次任务经验压缩成可复用摘要 | 缺 | 减少长期记忆噪音 |
| Knowledge Provenance | 记录知识来源、时间、验证证据 | 弱 | 知识可信度可判断 |

### 7. Governance

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Policy Engine | 决定 plan、TDD、review、rollback、worktree、performance | 有 | 由 Kernel 统一调用并记录 |
| Risk Scoring | 风险评分，不只依赖 L1-L4 | 弱 | 综合业务、数据、权限、契约、范围、工作区状态评分 |
| Permission Policy | 危险操作、敏感文件、外部网络、删除、迁移等权限边界 | 弱 | 高危动作必须明确确认或满足策略 |
| Review Governance | 决定何时必须 review，review 失败如何处理 | 有雏形 | Review 结果影响状态机下一步 |
| Promotion Governance | memory -> candidate -> skill/rule/policy 的升级治理 | 有雏形 | 证据、次数、边界、审批、回滚齐全 |
| Rollback Governance | 判断何时必须 rollback plan 或 checkpoint | 有雏形 | 高风险变更无 recovery 不执行 |
| Audit Trail | 记录关键决策、证据、策略、验证、文档、记忆 | 弱 | 每个 L3/L4 任务可审计 |

### 8. Execution Pipeline

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Plan Stage | 生成用户可见计划 | 有 | 计划由 context、risk、policy、capability 共同决定 |
| Act Stage | 执行代码、文档、配置变更 | 有 | 执行动作可追踪、可回滚 |
| Observe Stage | 收集 diff、日志、测试输出、工具结果、用户反馈 | 弱 | 每个关键步骤都有 observation |
| Verify Stage | 编译、lint、test、review、benchmark、smoke | 有雏形 | 验证 pipeline 自动按任务选择 |
| Recover Stage | 失败恢复、回滚、重试、暂停 | 弱 | 失败可分类处理，不盲目继续扩大改动 |
| Document Stage | 更新 README/docs/docs-agent-os/决策/验证记录 | 有规则 | 文档更新成为 pipeline 固定阶段 |
| Learn Stage | 反思、记忆、候选升级 | 弱 | 学习有证据、有边界、有审批 |
| Deliver Stage | 最终说明验证、风险、文档、记忆和剩余事项 | 有 | 最终回复可审计、结论明确 |

### 9. Verification

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Validation Profile | 根据技术栈和任务层选择验证命令 | 有 | 覆盖更多栈和项目结构 |
| Test Runner | 执行测试并记录结果 | 有雏形 | 支持多命令、多阶段、失败分类 |
| Review Runner | 代码审查、规则审查、文档审查执行器 | 弱 | Review Gate 可半自动执行 |
| Benchmark Runner | 性能基准和非回归检查 | 缺 | 性能风险任务必须有基准策略 |
| Smoke Test Runner | API、UI、端到端冒烟验证 | 缺 | 功能链路能跑最小真实路径 |
| Diff Validator | 检查 diff 是否超范围、是否改错文件 | 弱 | 交付前自动发现范围漂移 |
| Evidence Store | 统一保存验证证据和引用 | 弱 | 最终回复和 docs 可引用证据 |

### 10. Documentation System

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Documentation Gate | 判断文档是否需要更新 | 有 | 每次任务最终回复前强制执行 |
| Docs Placement Policy | 区分 `.agent-os/`、`docs/agent-os/`、memory | 有 | 所有 workflow 遵循同一边界 |
| Docs Freshness Check | 判断文档是否过期 | 缺 | 代码/配置/API 变更后能提示文档同步 |
| Behavior-Docs Consistency | 检查行为与文档是否一致 | 缺 | 交付前发现 README/docs 陈旧 |
| Decision Doc Template | 生成技术或业务决策记录 | 弱 | L3/L4 决策有统一模板 |
| Verification Doc Template | 生成验证记录 | 弱 | 高风险任务有可读验证报告 |
| Docs Impact Analysis | 判断本次改动影响哪些文档 | 缺 | Documentation Gate 不再只靠模型记忆 |

### 11. Reflection

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Outcome Reflection | 复盘任务成功、失败、部分完成原因 | 缺 | 复杂任务结束后产出结构化 reflection |
| Root Cause Classification | 失败根因归类 | 弱 | 区分需求、实现、环境、测试、上下文、工具失败 |
| Pattern Extraction | 从任务中提取可复用模式 | 弱 | 自动生成 candidate 证据 |
| Anti-pattern Detection | 发现反复出错模式 | 缺 | 多次失败后提示规则或 workflow 调整 |
| Second Failure Protocol | 连续失败后的强制重审 | 有规则，弱执行 | 状态机强制暂停扩张并重新诊断 |
| Reflection Report | 生成短复盘，供 memory 和 evolution 使用 | 缺 | Learning Engine 可消费 reflection |

### 12. Learning

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Memory Update | 写入项目或全局记忆 | 有 | 与 Documentation Gate、Reflection 联动 |
| Candidate Generation | 生成 candidate skill/rule/policy | 有雏形 | 从 reflection 中自动提取候选 |
| Evidence Threshold | 基于次数、验证和范围判断能否升级 | 有规则，弱执行 | 升级建议有客观证据 |
| Human Approval Flow | 人类确认后升级规则、skill、policy | 弱 | 所有自我升级必须经过审批 |
| Promotion Rollback | 升级后可回滚 | 缺 | 错误规则或 skill 能撤销 |
| Learning Boundary | 区分项目经验、全局偏好、业务私有信息 | 有规则 | 执行层面防止跨项目污染 |

### 13. Observability

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Run Report | 输出一次 run 的完整报告 | 有雏形 | 包含 context、policy、tasks、verification、docs、memory |
| Event Log | 事件级日志 | 缺 | Kernel 的所有事件可追踪 |
| Metrics | 成本、耗时、失败率、验证通过率、重试次数 | 缺 | 可评估 Agent OS 质量趋势 |
| Trace Viewer | 可视化执行链路 | 缺 | 复杂任务能看见流转过程 |
| Quality Dashboard | 查看 agent 表现趋势 | 缺 | 支持长期改进 |
| Audit Export | 导出审计记录 | 缺 | 高风险任务可交给人审查 |

### 14. Recovery

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Checkpoint | 执行前保存恢复点 | 有雏形 | 高风险任务强制 checkpoint |
| Rollback Plan | 变更失败后的恢复步骤 | 有雏形 | rollback plan 可执行、可验证 |
| Partial Completion Handling | 部分完成如何继续或回退 | 弱 | 中断后能识别已完成和未完成 |
| Resume Plan | 中断后如何继续 | 弱 | runtime-next 能恢复具体下一步 |
| Failure Escalation | 多次失败后升级到用户确认 | 有规则，弱执行 | 状态机强制执行失败升级 |
| Recovery Verification | 回滚或恢复后验证是否稳定 | 缺 | 恢复也必须有验证记录 |

### 15. Multi-Agent

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Role Separation | planner、executor、reviewer、verifier、memory-recorder | 有字段 | 角色有明确输入输出 |
| Role Scheduling | 分配角色并推进状态 | 缺 | Kernel 可调度不同角色 |
| Result Merge | 合并多个 agent 的结果 | 缺 | 多 agent 输出可比对和合并 |
| Conflict Arbitration | 多 agent 冲突裁决 | 缺 | 冲突进入 Review 或用户确认 |
| Specialist Pool | 不同专家 agent 可插拔 | 缺 | UI、API、DB、Review 等专家可选择 |
| Multi-agent Isolation | 多 agent 防止互相覆盖文件或 memory | 缺 | 有工作区隔离和合并策略 |

### 16. Security

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Command Safety | 命令 allowlist、unsafe 拦截 | 有雏形 | 不同风险级别有不同执行策略 |
| Secret Detection | 防止 token、密钥进入 memory、docs、logs | 弱 | 记录前自动扫描敏感信息 |
| Data Boundary | 不跨项目泄露业务记忆 | 有规则 | Memory 和 docs 都有项目隔离检查 |
| Permission Escalation | 高危操作需要显式确认 | 弱 | 删除、迁移、发布、外部写入必须审批 |
| Sandbox Strategy | 工具和命令隔离 | 缺 | 可按任务风险选择隔离级别 |
| External API Policy | 网络调用和外部 API 使用策略 | 缺 | 外部服务调用可审计、可限制 |

### 17. Packaging / Compatibility

| 能力项 | 作用 | 当前状态 | 目标状态 |
| --- | --- | --- | --- |
| Install Check | 检查 `.agent-os` 是否正确安装 | 弱 | 一键诊断安装完整性 |
| Versioning | Agent OS 版本、迁移、兼容判断 | 缺 | 每个项目知道当前 Agent OS 版本 |
| Migration Tool | 版本升级或路径迁移 | 缺 | 安全迁移配置、memory、docs |
| Adapter Layer | 适配 Codex、Claude、Cursor、Gemini CLI、VSCode 插件 | 缺 | 同一 Agent OS 能服务多个 AI 宿主 |
| Health Check | 检查 rules、skills、runtime、memory、docs 状态 | 缺 | 一条命令输出系统健康报告 |
| Distribution Strategy | clone、submodule、插件、包管理等分发方式 | 弱 | 支持团队稳定安装和升级 |

---

## 优先级路线图

### P0：把 Agent OS 从规则系统升级为可调度内核

P0 是 Agent OS 2.0 的地基。目标是让系统从“规则 + runtime 命令”升级为“Kernel + State Machine + Workspace State”。

| 优先级 | 能力 | 为什么先做 | 交付物 | 验收标准 |
| --- | --- | --- | --- | --- |
| x P0-1 | Agent Kernel 骨架 | 没有 Kernel，其他能力仍然是散的 | `scripts/agent-kernel.py` 或 runtime 内 kernel 模块 | 能创建 run，读取 context，产生下一步 action |
| x P0-2 | Event Schema / Event Bus | 事件化是 OS 化的前提 | SQLite event 表、事件类型定义、事件记录命令 | 用户请求、context ready、task completed、verification failed 能被记录 |
| x P0-3 | Goal / Task State Machine | 让任务不再只靠人工顺序推进 | goal/task 状态流转规则 | 状态能从 planning -> executing -> verifying -> documenting -> completed |
| x P0-4 | Workspace OS 基础模型 | Kernel 需要统一读取文件、git、docs、memory、runtime 状态 | workspace scan 命令和 workspace state object | 能输出项目结构、git 状态、docs 状态、runtime 摘要 |
| x P0-5 | Context Ranking 初版 | 避免上下文加载散乱 | context score 规则和排序输出 | 能按任务相关性排序 files、docs、memory、rules |
| x P0-6 | Execution Pipeline 状态化 | 把 gates 变成可执行 pipeline | pipeline stages 和 stage result 记录 | 每个 L2+ run 有 plan/act/observe/verify/document/learn 状态 |
| x P0-7 | Final Gate Completeness 2.0 | 防止漏验证、漏文档、漏记忆 | 扩展 `runtime-final-check` | 能检查 verification、documentation、memory、open tasks、recovery |

P0 完成后，Agent OS 应该具备：

- 每个复杂任务都有明确 run、goal、task、event、state。
- Kernel 能根据当前状态给出下一步。
- Workspace 状态成为 Context、Risk、Documentation、Recovery 的共同输入。
- Documentation Gate 和 Memory Gate 不再只是文字规则，而能被 final check 检查。

### P1：把验证、恢复、反思和学习闭环做实

P1 目标是提高可靠性，让 Agent 不只是能跑，还能知道成功、失败、为什么失败、下次怎么避免。

| 优先级 | 能力 | 为什么重要 | 交付物 | 验收标准 |
| --- | --- | --- | --- | --- |
| x P1-1 | Verification Pipeline | 验证是信任基础 | compile/lint/test/review/benchmark/smoke 统一 pipeline | 根据任务自动生成多阶段验证计划 |
| x P1-2 | Failure Classification 2.0 | 不同失败要走不同恢复策略 | failure type 标准和分类器 | 测试失败、环境失败、权限失败、实现失败可区分 |
| x P1-3 | Recovery Engine | 失败后能安全恢复 | recovery plan、checkpoint、rollback verify | 高风险任务无 recovery 不进入执行 |
| x P1-4 | Reflection Engine | 把结果转成经验 | reflection record 和 root cause classification | 失败或高信号任务生成结构化复盘 |
| x P1-5 | Learning Engine 初版 | 从经验进入候选升级 | reflection -> memory item -> candidate | 可自动提出 candidate，但不自动修改规则 |
| x P1-6 | Docs Freshness Check | 文档不能靠模型记忆 | docs impact / stale docs 检测 | API、命令、路径变化能提示更新文档 |
| x P1-7 | Knowledge Conflict Detection | 防止旧 memory 误导 | memory/docs/code 冲突检测 | 冲突时要求重新取证 |

P1 完成后，Agent OS 应该具备：

- 验证失败能分类、恢复、重试或停止扩张。
- 高信号任务能产生 reflection。
- Learning 不再只是手写 memory，而是有候选生成链路。
- 文档过期能被主动发现。

### P2：统一 Runtime 和多模型、多工具、多 Agent 能力

P2 目标是让 Agent OS 不绑定单一宿主或单一执行方式。

| 优先级 | 能力 | 为什么重要 | 交付物 | 验收标准 |
| --- | --- | --- | --- | --- |
| x P2-1 | Tool Runtime | 统一 Shell/Git/API/Browser 执行策略 | tool adapter 接口和执行记录 | 工具调用有类型、耗时、结果、失败原因 |
| x P2-2 | Skill Runtime | skill 不只是文件，而是可验证能力包 | skill manifest、loader、validator | 能检查 skill frontmatter、依赖和触发说明 |
| x P2-3 | Model Runtime | 支持多模型宿主 | model adapter 接口 | GPT/Claude/Gemini 等可抽象为统一 runtime |
| x P2-4 | Sub-agent Runtime | 支持多角色协作 | planner/executor/reviewer/verifier 调度 | 角色有输入输出和边界 |
| x P2-5 | Adapter Layer | 支持 Codex、Claude、Cursor、VSCode 插件等 | host adapter 规范 | 同一 Agent OS 可在不同宿主下运行 |
| x P2-6 | Observability Metrics | 衡量系统质量 | metrics 表和 report 输出 | 能看到耗时、失败率、验证通过率、重试次数 |
| x P2-7 | Trace Report | 可审计执行链路 | run trace 导出 | 一次任务能导出完整 trace |

P2 完成后，Agent OS 应该具备：

- 工具、模型、skill、sub-agent 都是可调度 runtime。
- 不同 AI 宿主可以接入同一套 Agent OS。
- 复杂任务能生成 trace 和 metrics。

### P3：产品化、可视化和团队级使用

P3 目标是让 Agent OS 从源码框架走向可安装、可升级、可观测的产品能力。

| 优先级 | 能力 | 为什么重要 | 交付物 | 验收标准 |
| --- | --- | --- | --- | --- |
| x P3-1 | Install Health Check | 用户接入要稳定 | `agent-os doctor` | 检查目录、AGENTS、rules、skills、memory、runtime |
| x P3-2 | Versioning / Migration | 多项目需要升级路径 | version 文件和 migration 工具 | 能检测版本并安全迁移 |
| x P3-3 | Dashboard | 让状态可见 | 本地 dashboard 或 report UI | 可看 run、goals、tasks、events、verification |
| x P3-4 | Quality Trends | 长期观察 Agent 表现 | metrics 趋势报告 | 可看失败率、验证通过率、文档漏更新率 |
| x P3-5 | Team Policy Packs | 团队级规则包 | policy pack 机制 | 团队能复用治理策略 |
| x P3-6 | Distribution Strategy | 支持 clone、submodule、插件、包管理 | 安装和升级文档 | 接入方式稳定明确 |
| x P3-7 | Security Hardening | 团队/生产环境安全 | secret scan、permission policy、sandbox strategy | 敏感信息和高危命令有保护 |

P3 完成后，Agent OS 应该具备：

- 用户可以稳定安装、升级、检查健康状态。
- 团队可以复用策略和治理规则。
- Agent OS 的运行质量可被持续观察和优化。

---

## 推荐实施顺序

### 第一阶段：Kernel 和 Workspace 基建

1. 定义 `events` 表和事件类型。
2. 定义 goal/task 状态机。
3. 扩展 runtime records，把 event_id / run_id / goal_id 串起来。
4. 实现 workspace scan，输出 project files、git state、docs state、runtime state。
5. 扩展 `runtime-next`，让它基于 state machine 和 workspace state 决定下一步。

### 第二阶段：Pipeline 和 Final Check

1. 把 Plan / Act / Observe / Verify / Document / Learn 建成 pipeline stage。
2. 扩展 `runtime-final-check`，加入 Documentation Gate 和 Memory Gate 检查。
3. 为 L2+ 任务生成 pipeline report。
4. 增加测试覆盖：缺 verification、缺 docs decision、open task 时 final check 必须失败。

### 第三阶段：Verification 和 Recovery

1. 统一 verification profile。
2. 引入多阶段 verification pipeline。
3. 强化 failure classification。
4. 强化 checkpoint / rollback / recovery verify。
5. 对高风险任务强制 recovery plan。

### 第四阶段：Reflection 和 Learning

1. 新增 reflection record。
2. 从失败、高风险、重复任务中生成 reflection。
3. 将 reflection 转为 memory item 或 candidate。
4. 完善 candidate promotion review。
5. 明确 human approval 后才能升级 rule / skill / policy。

### 第五阶段：Runtime Adapter 和多宿主

1. 抽象 tool runtime。
2. 抽象 skill runtime。
3. 抽象 model runtime。
4. 抽象 host adapter。
5. 对接 CLI、VSCode 插件、Claude/Cursor 等使用方式。

---

## 不应该优先做的事情

| 不优先事项 | 原因 |
| --- | --- |
| 继续堆更多业务 skill | 当前瓶颈是调度、验证、恢复、学习，不是 skill 数量 |
| 一开始就做 UI dashboard | 没有稳定 event/state/metrics 前，dashboard 只是展示壳 |
| 自动修改 rules/skills | Learning 必须受治理，不应直接自我升级 |
| 过早抽象所有模型 | 先把 Kernel 和 Runtime 边界做稳，再接多模型 |
| 过度复杂的多 agent | 没有状态机和冲突裁决前，多 agent 容易互相覆盖 |

---

## Agent OS 2.0 验收标准

当以下标准满足时，可以认为进入 Agent OS 2.0：

1. 任意 L2+ 任务都有 goal、task、event、state、policy、verification、documentation、memory 记录。
2. Kernel 能根据当前状态决定下一步，而不是完全依赖人工顺序。
3. Workspace OS 能提供项目文件、git、docs、memory、runtime 的统一状态。
4. Verification Pipeline 能根据任务类型自动规划并执行验证。
5. Documentation Gate 能检测并记录文档更新决策。
6. Recovery Engine 能为高风险任务提供 checkpoint、rollback plan 和恢复验证。
7. Reflection Engine 能对失败或高信号任务生成结构化复盘。
8. Learning Engine 能把复盘转成 memory 或 candidate，但不会自动升级规则。
9. Review / Promotion Governance 能控制 skill、rule、policy 的升级。
10. Run Report 能完整说明一次任务从输入到交付的过程和证据。

---

## 一句话总结

Agent OS 2.0 的核心不是让模型“更聪明地写代码”，而是让一次任务从目标、上下文、计划、执行、验证、恢复、文档、记忆到演化，都变成可调度、可审计、可恢复的系统能力。

---

## P2/P3 完整化清单

### P2-F：Runtime Execution 完整化

| 优先级 | 能力 | 完整实现目标 | 验收标准 |
| --- | --- | --- | --- |
| x P2-F1 | Tool Runtime 完整化 | Shell/Git/API/Browser 走统一 Tool Adapter 执行协议 | 四类 tool 都能真实执行或明确 blocked/unsupported，并记录耗时、结果、失败原因 |
| x P2-F2 | API Tool Adapter | 支持 method、headers、body、timeout、状态码、响应摘要、安全脱敏 | runtime 能调用本地 HTTP API，并记录状态码/响应摘要 |
| x P2-F3 | Browser Tool Adapter | 支持 open/check-text/click/type/screenshot | runtime 能打开本地页面、点击、输入、截图并记录结果 |
| x P2-F4 | Git Tool Adapter | 支持 status/diff/log/branch/check-clean 结构化动作 | runtime 能结构化返回 git state、branch、diff/check-clean 结果 |
| x P2-F5 | Skill Runtime 完整化 | skill dependency graph、trigger matcher、conflict detection、version 字段 | 输入任务后能解释 skill 选择原因，依赖缺失或冲突时能阻止 |
| x P2-F6 | Model Runtime 完整化 | Model Adapter 接口、mock/local adapter、provider 配置诊断 | mock/local 能真实返回；真实 provider 缺 key 时明确 blocked |
| x P2-F7 | Model Config / Secret Boundary | env/config provider 设置，禁止记录 API key | secret 不进 DB/log；配置缺失可诊断 |
| x P2-F8 | Sub-agent Runtime 完整化 | planner/executor/reviewer/verifier 子任务调度 | 能创建多角色任务链，并按顺序推进 |
| x P2-F9 | Reviewer / Verifier 子代理 | reviewer 读取 diff 给 findings，verifier 执行验证计划 | review/verification 能独立产出结果 |
| x P2-F10 | Host Adapter 完整化 | Codex/Claude/Cursor/VSCode adapter 能力协议和检测 | 能报告当前宿主支持/不支持的能力 |
| x P2-F11 | Runtime Orchestrator | 串起 context -> policy -> skill -> tool/model/subagent -> verification -> memory | 一个 runtime loop 能推进完整任务链，而不只是计划 |
| x P2-F12 | Trace 完整化 | step timeline、duration、input/output hash、关联事件 | 一次任务能导出完整可审计链路 |

### P3-F：Productization 完整化

| 优先级 | 能力 | 完整实现目标 | 验收标准 |
| --- | --- | --- | --- |
| x P3-F1 | CLI 入口产品化 | `agent-os` CLI 包装入口 | 用户能直接运行 `agent-os doctor` |
| x P3-F2 | Installer | install 命令复制 `.agent-os`、生成根 `AGENTS.md`、初始化 memory | 空项目一条命令完成接入 |
| x P3-F3 | Upgrade / Migration 完整化 | 版本比较、升级前备份、dry-run、迁移报告、失败回滚提示 | 能从旧版本安全升级到新版本 |
| x P3-F4 | Doctor 完整化 | root AGENTS、模板、policy packs、security、版本兼容、DB 可写性检查 | doctor 能发现安装缺失/版本不匹配/策略包错误 |
| x P3-F5 | Dashboard 产品化 | 交互式本地 dashboard 或 VSCode 数据源 | 用户能浏览任务链路和质量趋势 |
| x P3-F6 | Quality Trends 完整化 | 趋势图数据、失败聚类、验证通过率趋势、docs 漏更新趋势 | 能看最近 N 次任务质量变化 |
| x P3-F7 | Policy Packs 完整化 | install/enable/disable/override/inherit/conflict check | 团队能启用治理策略并检测冲突 |
| x P3-F8 | Security Hardening 完整化 | ignore 规则、熵检测、危险命令策略、审计报告 | secret scan 可配置，高危命令可拦截 |
| x P3-F9 | VSCode 插件集成边界 | 插件注入、状态面板、dashboard、report、doctor 交互协议 | 插件能调用 Agent OS CLI 并展示状态 |
| x P3-F10 | Distribution Channels | clone/submodule/plugin/package 的实际命令或脚本 | 每种分发方式都有可执行路径 |
| x P3-F11 | Team Workspace | 团队 policy、共享 templates、项目本地 override | 多项目复用同一套 Agent OS 策略 |
| x P3-F12 | Release Checklist | release doctor、security check、tests、schema version check | 发布前一条命令确认可发布 |
