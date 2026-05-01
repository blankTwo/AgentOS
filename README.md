# Codex Mother System v2

一个面向多项目、全栈开发的 Codex 母体系统。

它的目标不是为每个项目重复搭建一套 AGENTS / rules / skills，而是用一套可复用母体服务多个项目，同时通过项目记忆保持上下文隔离。

## 这是什么

这套系统主要解决 4 件事：

- 用统一入口管理不同项目的执行规则
- 把重复经验从项目记忆沉淀成 skill，再升级为 rule
- 让 UI、API、数据、测试、重构等流程可以跨项目复用
- 避免不同项目之间的业务细节互相污染

它更适合：

- 多项目、多技术栈、全栈开发场景
- 希望统一开发纪律，但不想为每个技术栈单独维护一套 skill 的团队
- 前端/UI 要求较高，同时也需要 API、数据、测试、运行时协作的项目
- 希望长期沉淀可复用规则与技能的场景

## 快速开始

### 第一次使用

1. 保持本目录中的 `AGENTS.md`、`rules/`、`skills/`、`memory/` 完整存在
2. 在任意项目中复用这套母体系统
3. 由 `AGENTS.md` 负责识别项目、技术栈、匹配 rules 和 skills
4. 将项目特定经验写入 `memory/projects/{project}.md`

### 典型工作流

**场景 1：修复一个项目 bug**

- 系统识别项目、技术栈与任务层
- 选择 `skills/bugfix/`
- 根据影响范围补充相关 rules
- 修复后把项目特定坑点写入对应 project memory

**场景 2：从 0 到 1 新建一个产品页面**

- 系统识别这是 UI 新建任务
- 读取 `rules/ui-consistency.md`
- 选择 `skills/feature-ui/`
- 根据项目现有技术栈与实现模式落地

**场景 3：新增或修改接口**

- 系统识别这是 API Layer 任务
- 选择 `skills/api-change/`
- 检查请求参数、响应结构、错误处理、兼容性与验证路径

**场景 4：优化已有页面**

- 系统识别这是 UI 优化任务
- 读取 `rules/ui-consistency.md`
- 选择 `skills/ui-refine/`
- 重点统一风格、减少原生拼装感、提升成熟度

## 核心概念

### AGENTS / rules / skills / memory 的关系

| 层级 | 作用 | 适合放什么 | 更新频率 |
| --- | --- | --- | --- |
| `AGENTS.md` | 总控入口 | 执行流程、路由、全局策略 | 极低 |
| `rules/` | 稳定规范 | 编码风格、测试规范、技术栈规则 | 低 |
| `skills/` | 可复用流程 | bugfix、refactor、api-change、feature-ui、write-tests | 中 |
| `memory/global/` | 跨项目沉淀 | 通用偏好、可复用模式、演化日志 | 中 |
| `memory/projects/` | 项目隔离上下文 | 决策、坑点、项目模式、约束 | 高 |

### 单母体、多项目复用

这套系统的基本思路是：

- 入口只有一套
- 规则只有一套主干
- 技能尽量复用
- 差异放到项目记忆里解决

这样能减少重复配置，也能让经验真正积累起来。

### Mandatory Gates

系统不采用“强制调用某个 skill”的方式，而是采用 Mandatory Gates 作为主流程骨架。

每次任务先经过 5 个判断门：

- `Context Gate`：识别项目、技术栈、任务层，并读取 memory summary
- `Evidence Gate`：排查、诊断、架构判断、数据/权限判断必须先有证据
- `Risk Gate`：判断是否需要 plan、worktree、回滚预案、TDD、review 或更高验证强度
- `Validation Gate`：完成前必须说明验证方式、验证结果和剩余风险
- `Memory Gate`：判断是否写 memory、是否只是演化候选、是否不应沉淀

这样做的目的不是增加流程负担，而是确保重要任务有上下文、有证据、有风险判断、有验证结果。

### 任务层优先，不按技术栈无限扩展

skill 的主分类按任务层组织，而不是按技术栈组织。

主要任务层包括：

- `UI Layer`：页面、组件、交互、视觉一致性
- `API Layer`：接口、请求/响应、鉴权、错误处理
- `Data Layer`：schema、migration、查询、事务、数据一致性
- `Integration Layer`：前后端联动、第三方服务、SDK、webhook
- `Runtime Layer`：环境变量、构建、部署、脚本、依赖
- `Test Layer`：测试编写、测试修复、测试基础设施
- `Bugfix Layer`：问题排查、根因定位、修复验证
- `Refactor Layer`：结构优化、行为不变、可维护性提升

技术栈仍然重要，但它是实现上下文：

- React 项目仍会读取 React 规则和现有组件模式
- Node 项目仍会读取后端规则和服务结构
- Java / Go / Python / Rust 等项目优先遵循通用 rules 与项目现有代码模式

系统不会因为出现一个新技术栈就新增一套平行 skill。

## 目录说明

### `AGENTS.md`

总控入口。定义：

- 项目识别
- 技术栈识别
- 任务层识别
- Mandatory Gates
- rule / skill 加载顺序
- UI 任务路由
- plan 触发条件
- memory 与演化策略

这份文件是系统核心，不建议频繁修改。

### `rules/`

存放稳定规范。当前包含：

- `coding-style.md`：通用编码风格
- `testing.md`：验证与测试要求
- `change-policy.md`：哪些文件适合高频更新，哪些不适合
- `evolution.md`：memory / skill / rule 升级条件
- `frontend-react.md`：React 项目规则
- `backend-node.md`：Node 后端规则
- `taro-miniapp.md`：Taro / 小程序规则
- `ui-consistency.md`：UI 一致性规则
- `tailwind-conventions.md`：Tailwind 写法约束

### `skills/`

存放可复用流程。当前包含：

- `bugfix/`：通用 bug 修复
- `refactor/`：通用重构
- `write-tests/`：测试编写
- `api-change/`：接口变更
- `feature-ui/`：从 0 到 1 生成功能级 / 页面级 UI
- `ui-refine/`：优化已有页面，统一风格与质量
- `feature-react/`：React 实现层 skill

说明：
- skill 优先按任务层组织，而不是按技术栈无限扩展
- 技术栈用于决定实现约束、项目模式和可加载 rules
- `feature-react/` 保留为当前 React 项目的实现辅助，不代表每个技术栈都必须新增对应 skill

### `memory/global/`

存放跨项目通用信息：

- `preferences.md`：稳定开发偏好
- `reusable-patterns.md`：可复用模式
- `evolution-log.md`：升级记录

其中 `reusable-patterns.md` 用来记录已经跨任务稳定成立的工作模式，例如 gate 先于 skill、任务层路由、证据优先、风险分级 TDD、worktree 风险隔离和 memory 升级门槛。

### `memory/projects/`

存放项目隔离记忆：

- `_template.md`：项目记忆模板
- `_index.md`：项目索引
- `{project}.md`：具体项目的上下文、决策、坑点、模式

## 演化机制

经验升级路径：

```text
project memory -> skill -> rule
```

### 什么时候写 project memory

- 项目特定的决策
- 这个项目里踩过的坑
- 局部但有复用价值的模式
- 尚未稳定、但值得记录的经验

### 什么时候升级为 skill

满足下面条件再考虑：

- 在同一项目重复出现至少 2 次，或多个项目都出现
- 有明确触发条件
- 有明确步骤
- 已验证有效

### 什么时候升级为 rule

满足下面条件再考虑：

- 多项目可复用
- 已经稳定
- 不依赖强业务语义
- 作为规范比作为流程更合适

## 隔离机制

为了避免不同项目之间互相污染，这套系统默认：

- 每个项目单独写 `memory/projects/{project}.md`
- 禁止把 A 项目的业务细节写进 B 项目 memory
- 技术栈和项目识别先于 skill 选择
- 记忆分为 `Summary` 和 `Detailed Records`

简单理解：

- 共性的东西进 rule / skill / global memory
- 项目特有的东西进 project memory

## 维护建议

- 高频更新 `memory/`
- 中频更新 `skills/`
- 低频更新 `rules/`
- 极低频更新 `AGENTS.md`

如果某个问题刚出现一次，优先写 memory。
如果某个流程已经稳定复用，再考虑升级成 skill。
如果某条规则已经跨项目稳定成立，再考虑升级成 rule。

维护时应遵守：

- 不把一次性案例写成 skill/rule
- 不因为新技术栈出现就新增 stack-specific skill
- 不用临时占位或半成品方案替代系统性调整
- 修改 skill 前说明复用价值，修改 rule 前说明稳定性证据
- 完成后给出验证结果，而不只是说明“已完成”

## 常见问题

### 我需要给每个项目单独建 AGENTS.md 吗？

不需要。默认就是用这一套母体复用到多个项目。

### 项目差异写在哪里？

写到 `memory/projects/{project}.md`。

### 我应该优先改 rule 还是 skill？

优先不要动 rule。一般先改 memory，再改 skill，最后才是 rule。

### README 和 AGENTS.md 的区别是什么？

- `README.md` 是给人看的系统说明
- `AGENTS.md` 是给 agent 执行的规则入口

不要把 `AGENTS.md` 的详细执行流程复制进 README。

### 这套系统是不是完全技术栈中立？

不是完全技术栈中立。它现在定位为全栈开发母体，但前端/UI 能力仍然是当前较成熟的强项。

系统不会为每个技术栈无限新增 skill，而是通过任务层 skill、技术栈识别和项目现有模式组合落地。
