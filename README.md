# Agent OS

一套面向 AI Coding Agent 的项目级执行操作层。

Agent OS 不是某个具体业务项目，也不是某一种技术栈模板。它用统一的 `AGENTS.md`、`rules/`、`skills/` 和 `memory/`，为 AI Coding Agent 提供上下文识别、能力发现、规划决策、任务执行、验证沉淀与持续演化机制，让多个项目共享同一套开发纪律，同时避免项目上下文互相污染。

## 它解决什么问题

当你同时维护多个项目时，经常会遇到这些问题：

- 每个项目都要重复写一套 AI 规则、编码偏好和工作流
- Agent 容易一上来就选错技术栈、选错 skill，或者凭感觉修改代码
- Bug 修完没有证据，功能做完没有验证，经验也没有沉淀
- 前端、后端、数据、测试、重构等任务各自散落，缺少统一入口
- 不同项目的业务细节混在一起，长期使用后上下文污染越来越严重

Agent OS 的目标是把这些问题收束到一套稳定机制里：

- 用统一入口识别项目、技术栈和任务层
- 用 Mandatory Gates 保证上下文、证据、能力现状、风险、计划、验证和记忆判断
- 用 task-layer skills 承接 UI、API、Bugfix、Refactor、Test 等任务
- 用 project memory 隔离不同项目的专属上下文
- 用 evolution 机制把重复经验从 memory 沉淀为 skill，再升级为 rule

## 核心设计

### 1. Agent OS 复用，而不是每个项目重复配置

这套系统把通用能力放在 Agent OS 里：

| 模块 | 作用 |
| --- | --- |
| `AGENTS.md` | 总控入口，定义项目识别、任务路由、gate 流程和加载顺序 |
| `context/` | 模型侧上下文层，判断业务影响、能力状态、平台差异、契约风险和证据是否充分 |
| `workflows/` | 模型侧工作流层，定义不同任务类型的执行顺序和用户可见输出 |
| `rules/` | 稳定规则，例如编码风格、测试策略、变更策略、UI 一致性 |
| `skills/` | 可复用执行流程，例如 bugfix、api-change、feature-ui、refactor |
| `memory/global/` | 跨项目通用偏好、复用模式和演化记录 |
| `memory/projects/` | 每个项目独立的上下文、约束、坑点和决策 |

项目差异不写进全局规则，而是写进 `memory/projects/{project}.md`。

### 2. 按任务层选 skill，而不是按技术栈无限扩展

系统按任务层组织 skill：

- `UI Layer`：页面、组件、布局、样式、交互、视觉一致性
- `API Layer`：接口、请求参数、响应结构、鉴权、错误处理
- `Data Layer`：schema、migration、查询、事务、数据一致性
- `Integration Layer`：前后端联动、第三方服务、SDK、webhook
- `Runtime Layer`：环境变量、构建、部署、脚本、依赖
- `Test Layer`：测试编写、测试修复、测试基础设施
- `Bugfix Layer`：异常行为、报错、状态不一致、边界失败
- `Refactor Layer`：结构优化、职责拆分、行为不变

技术栈仍然重要，但它是实现上下文，不是 skill 的主要分类方式。

当前已有 React、Node、Taro / Mini Program 等专属 rules。对于暂无专属 rule 的技术栈，例如 Java、Go、Python、Rust，系统会优先遵循通用 rules、任务层 skill 和项目现有代码模式，而不是假装已经内置完整技术栈规范。

## 当前适用范围

适合：

- 多项目、多技术栈或全栈开发场景
- 想让 AI Coding Agent 在不同项目中保持一致工作纪律
- 希望前端 UI、API、测试、重构、Bugfix 都有统一流程
- 希望长期积累可复用规则，而不是每次从零开始
- 希望项目上下文隔离，避免 A 项目的业务污染 B 项目

不适合：

- 只想要一个单项目模板
- 希望系统自动覆盖所有语言和框架的完整最佳实践
- 希望每个技术栈都维护一套平行 skill
- 不需要长期记忆和演化机制的临时实验项目

## 目录结构

在本仓库中，Agent OS 文件位于仓库根目录：

```text
.
├── AGENTS.md
├── rules/
│   ├── coding-style.md
│   ├── testing.md
│   ├── change-policy.md
│   ├── evolution.md
│   ├── agent-runtime.md
│   ├── memory-enhanced.md
│   ├── review-gate.md
│   ├── ui-design-system.md
│   ├── frontend-react.md
│   ├── backend-node.md
│   ├── taro-miniapp.md
│   ├── ui-consistency.md
│   └── tailwind-conventions.md
├── skills/
│   ├── api-change/
│   ├── bugfix/
│   ├── feature-react/
│   ├── feature-ui/
│   ├── refactor/
│   ├── ui-refine/
│   └── write-tests/
└── memory/
    ├── schema.sql
    ├── global/
    └── projects/
├── scripts/
│   ├── agent-runtime.py
│   ├── agent_store.py
│   └── memory-tools.py
└── tools/
    ├── agent-runtime.md
    └── memory-tools.md
```

放到具体项目中使用时，推荐放在目标项目的 `.agent-os/` 目录：

```text
your-project/
├── .agent-os/
│   ├── AGENTS.md
│   ├── rules/
│   ├── skills/
│   ├── memory/
│   ├── scripts/
│   └── tools/
└── ...
```

## 快速开始

### 方式一：复制到目标项目 `.agent-os/`

适合大多数项目。把本仓库完整放到目标项目的 `.agent-os/` 目录下：

```text
.agent-os/
├── AGENTS.md
├── context/
│   ├── README.md
│   ├── business-context.md
│   ├── capability-context.md
│   ├── platform-context.md
│   ├── contract-context.md
│   ├── language-context.md
│   ├── evidence-context.md
│   ├── risk-context.md
│   └── workflow-context.md
├── workflows/
│   ├── README.md
│   ├── workflow-selection.md
│   ├── simple-change.md
│   ├── bug-diagnosis.md
│   ├── cross-platform-issue.md
│   ├── feature-implementation.md
│   ├── api-contract-change.md
│   └── agent-os-evolution.md
├── rules/
├── skills/
├── memory/
├── scripts/
└── tools/
```

步骤：

1. 在目标项目根目录创建 `.agent-os/`。
2. 将本仓库的全部内容放入目标项目 `.agent-os/`，至少包含 `AGENTS.md`、`rules/`、`skills/`、`memory/`、`scripts/` 和 `tools/`。
3. 使用 `.agent-os/templates/project-AGENTS.md` 在目标项目根目录创建轻量入口 `AGENTS.md`。
4. 在支持读取项目 `AGENTS.md` 的 AI Coding Agent 中打开目标项目。
5. Agent 会通过根目录 `AGENTS.md` 进入 `.agent-os/AGENTS.md`，再识别项目、技术栈、任务层，并按需加载 context / workflows / rules / skills / memory；SQLite memory 工具由 `.agent-os/scripts/memory-tools.py` 提供，Agent Runtime 控制器由 `.agent-os/scripts/agent-runtime.py` 提供。

根目录 `AGENTS.md` 推荐模板：

```md
# Project Agent Entry

This project uses Agent OS from `.agent-os/`.

This root `AGENTS.md` is the project bootstrap entry. Load it first, then delegate to `.agent-os/AGENTS.md`.

## Agent Display

Agent display name: Agent OS

Use this display name at the start of the first user-visible status paragraph and for major status/conclusion paragraphs so the user can see Agent OS is active.

Before starting any task:
1. Read `.agent-os/AGENTS.md`.
2. Follow `.agent-os/context/`, `.agent-os/workflows/`, `.agent-os/rules/`, `.agent-os/skills/`, `.agent-os/tools/`, and `.agent-os/memory/`.
3. Prefer project-local `.agent-os/skills/<skill>/SKILL.md` over global user-level skills when both exist.
4. Treat this repository root as the user project.
5. Keep project-specific decisions in `.agent-os/memory/projects/{project}.md`.
6. Do not modify `.agent-os/AGENTS.md` unless the user explicitly asks to upgrade Agent OS itself.

Project-specific rules can be added below this line.
```

如果希望用户可见回复前缀使用其他名字，可以修改：

```md
Agent display name: 小白
```

### 方式二：直接把仓库克隆为 `.agent-os`

如果你希望保留 Git 更新能力，也可以在目标项目根目录直接克隆为 `.agent-os`：

```bash
git clone <this-repo-url> .agent-os
```

之后目标项目结构类似：

```text
your-project/
├── AGENTS.md
├── .agent-os/
│   ├── AGENTS.md
│   ├── context/
│   ├── workflows/
│   ├── rules/
│   ├── skills/
│   ├── memory/
│   ├── scripts/
│   └── tools/
├── src/
├── package.json
└── ...
```

如果 `.agent-os/` 本身是一个独立 Git 仓库，请根据你的团队策略决定是否把它作为 submodule、subtree，或直接加入目标项目版本管理。

### 使用后会发生什么

- `AGENTS.md` 作为总控入口，先识别项目、技术栈、任务层，再选择对应 skill
- 项目特定信息会写入 `.agent-os/memory/projects/{project}.md`
- 重复出现、已验证、有边界的经验，可以从 memory 升级为 skill 或 rule

## 常见任务如何路由

| 任务 | 默认路由 |
| --- | --- |
| 修复 bug、异常行为、状态不一致 | `skills/bugfix/` |
| 新增或修改接口 | `skills/api-change/` |
| 新建页面、列表、表单、详情、dashboard | `skills/feature-ui/` |
| React 页面或交互落地 | `skills/feature-react/` 作为实现辅助 |
| 优化已有 UI、统一风格 | `skills/ui-refine/` |
| 结构优化、职责拆分、重复消除 | `skills/refactor/` |
| 新增测试或补回归测试 | `skills/write-tests/` |

说明：`feature-react/` 是当前已有 React 项目的实现辅助，不代表每个技术栈都需要创建一个对应 skill。

## 工作流程

系统不鼓励“看到任务就直接调用某个 skill”。每次任务先经过 Mandatory Gates：

- `Context Gate`：识别项目、技术栈、业务影响、能力状态、平台差异、契约风险、语言边界和证据状态
- `Workflow Gate`：选择 Simple Change、Bug Diagnosis、Cross-Platform Issue、Feature Implementation、API Contract Change 或 Agent OS Evolution
- `User-visible Intent / Plan`：执行前先让用户看到执行意图；简单任务一句话即可，复杂/高风险任务必须展示结构化计划
- `Evidence Gate`：涉及 bug、架构、数据、权限、性能等判断时必须先有证据
- `Capability Discovery Gate`：对实现、新增、接入、支持类需求，先判断能力链路是完整存在、部分存在、断链存在还是不存在
- `Risk Gate`：判断 TDD、worktree、rollback、review、performance check 等风险策略
- `Planning Gate`：按上下文、workflow、业务风险和不确定性决定 plan 深度，而不是只按 L1-L4
- `Agent Runtime Gate`：L2 及以上、长任务或能力链路任务记录目标、任务、策略、验证和恢复状态
- `Validation Gate`：完成前说明验证方式、验证结果、失败处理和剩余风险
- `Memory Gate`：判断是否写入 project memory，是否只是 candidate，是否不应沉淀

简单任务可以简短完成这些判断，但仍需要一句用户可见执行意图；复杂或不确定任务必须完整经过 gate 并展示计划。

性能不单独作为独立 gate，而是在 `Risk Gate` 和 `Validation Gate` 中作为专项检查处理。

## Agent OS Runtime

Agent OS Runtime 是显式运行态，用 SQLite 记录任务推进过程中的关键状态，并提供控制器来识别上下文、扫描能力链路、评估策略、拆分任务、推荐 skill、选择下一步、规划并执行验证、规划恢复和审查演化候选。它不是后台常驻大脑，不会自动改代码、自动升级规则或自动写长期记忆；它只在 gate 和执行过程中由 Agent 显式运行并写入可审查记录。

Runtime 命令统一从 `scripts/agent-runtime.py` 执行；`scripts/memory-tools.py` 只负责记忆检索、沉淀、导入和统计。

Runtime 记录不能替代用户可见计划。`runtime-run`、`runtime-plan-tasks` 或 policy records 可以准备执行状态，但 Agent 仍必须在对话中展示对应 workflow 的执行意图、诊断计划或结构化计划。

语言边界：Agent OS 模型侧文件默认使用英文；用户业务项目里的 docs、标题、注释、UI 文案、错误消息、commit 和项目 memory 必须跟随项目已有语言和用户语言，除非用户明确要求英文。

Runtime 补齐 10 个核心 Agent 能力：

| 能力 | 记录位置 | 作用 |
| --- | --- | --- |
| Goal Runtime | `agent_goals` | 记录目标、阶段、成功标准和完成证据 |
| Autonomous Observe Loop | `agent_observations` / `runtime-scan-capability` | 记录文件、测试、构建、日志、用户反馈等观察信号 |
| Planner / Executor Separation | `agent_tasks.assigned_role` / `runtime-next` | 区分 planner、executor、reviewer、verifier、memory-recorder |
| Capability Graph | `capability_nodes` / `capability_links` / `runtime-scan-capability` | 判断能力是完整、半套、断链、不存在还是未确认 |
| Durable Task Queue | `agent_tasks` / `runtime-next` | 持久化任务队列、状态、阻塞点和计划 |
| Policy Engine | `policy_decisions` / `runtime-evaluate-policy` | 评估是否 plan、TDD、review、rollback、worktree、performance check |
| Memory Intelligence | `memory_items` / `skill_candidates` / `improvement_reviews` | 检索和沉淀经验，但不自动自我升级 |
| Verification Orchestrator | `verification_runs` / `runtime-plan-verification` | 规划并记录验证范围、命令、结果和证据 |
| Recovery / Rollback System | `recovery_points` / `runtime-plan-recovery` | 规划并记录恢复策略、影响文件和回滚依据 |
| Self-Improvement Governance | `improvement_reviews` | 记录演化候选、审查状态和边界 |

完整 Agent Loop 覆盖：

```text
runtime-detect-context
-> runtime-scan-capability
-> runtime-evaluate-policy
-> runtime-plan-tasks
-> runtime-run
-> runtime-complete-task
-> runtime-detect-validation-profile
-> runtime-run-verification
-> runtime-create-checkpoint / runtime-mark-recovery
-> runtime-select-skills
-> runtime-final-check
-> runtime-review-improvements
-> runtime-report
```

Runtime 触发原则：

- L1 简单局部修改：通常不需要 runtime 记录，但必须说明验证。
- L2 模块内多文件修改：建议记录 task 和关键 policy。
- L3 跨模块或跨层链路：必须记录 goal/task、capability、policy、verification，必要时记录 recovery。
- L4 架构、数据、权限、发布或 Agent OS 核心变更：必须记录完整运行态，并执行 review 或等价一致性检查。

常用命令：

```bash
python scripts/agent-runtime.py runtime-record --kind goal --project my-project --id goal-1 --objective "Implement phone login" --success-criteria "Phone login works end to end" --current-phase planning

python scripts/agent-runtime.py runtime-record --kind capability --project my-project --name phone-login --capability-status broken-chain --frontend "Login form exists" --api "API call missing" --backend "Endpoint unconfirmed" --data-state "Phone field unconfirmed" --verification "No end-to-end evidence" --evidence "Capability Discovery Gate result"

python scripts/agent-runtime.py runtime-record --kind policy --project my-project --goal-id goal-1 --decision-type plan --decision "full-plan-required" --rationale "Capability is broken-chain and task is L3" --evidence "Capability discovery result"

python scripts/agent-runtime.py runtime-detect-context --request "Implement phone login" --files src/pages/Login.tsx server/auth.ts --record

python scripts/agent-runtime.py runtime-run --project my-project --request "Implement phone login" --capability phone-login --term phone login auth --files src/pages/Login.tsx server/auth.ts --signal auth --use-memory --record

python scripts/agent-runtime.py runtime-scan-capability --project my-project --name phone-login --term phone login --record

python scripts/agent-runtime.py runtime-evaluate-policy --project my-project --scale L3 --capability-status broken-chain --task-layer Integration API --signal auth --record

python scripts/agent-runtime.py runtime-plan-tasks --project my-project --goal-id goal-1 --request "Implement phone login" --scale L3 --capability-status broken-chain --record

python scripts/agent-runtime.py runtime-select-skills --project my-project --request "Implement phone login" --stack "React Node" --record

python scripts/agent-runtime.py runtime-complete-task --project my-project --id run-1-task-1 --evidence "Implemented and verified" --complete-goal

python scripts/agent-runtime.py runtime-plan-verification --project my-project --task-layer Integration API --scale L3 --files src/pages/Login.tsx server/auth.ts --record

python scripts/agent-runtime.py runtime-detect-validation-profile --project my-project --stack Python --task-layer Runtime --files scripts/agent-runtime.py

python scripts/agent-runtime.py runtime-run-verification --project my-project --command "python -m py_compile scripts\\agent-runtime.py scripts\\agent_store.py" --record

python scripts/agent-runtime.py runtime-plan-recovery --project my-project --files src/pages/Login.tsx server/auth.ts --checkpoint HEAD --record

python scripts/agent-runtime.py runtime-create-checkpoint --project my-project --files src/pages/Login.tsx server/auth.ts

python scripts/agent-runtime.py runtime-final-check --project my-project --run-id run-1 --require-recovery --require-skills

python scripts/agent-runtime.py runtime-review-improvements --project my-project --goal-id goal-1 --run-id run-1 --record

python scripts/agent-runtime.py runtime-report --project my-project --run-id run-1

python scripts/agent-runtime.py runtime-next --project my-project --advance

python scripts/agent-runtime.py runtime-summary --project my-project
```

## Agent OS Memory Backend

系统提供 Agent OS Memory Backend，用 Markdown memory 作为可审查主记忆层，并用 SQLite 作为本地结构化检索与记录索引。

这里的“记忆”不是自动读取完整聊天记录，也不是凭空知道过去发生了什么。它依赖任务结束后的显式结构化沉淀：把已完成的功能、踩过的坑、架构决策、验证结果记录为可检索 memory item。后续任务开始时，Agent 再通过 Context Gate 或 Capability Discovery Gate 搜索这些记录，从而用已沉淀的项目经验辅助判断。

它解决的问题：

- 记住以前做过的相关功能
- 检索以前踩过的坑和解决方案
- 记录架构决策、UI 模式、验证经验
- 跟踪 candidate skill，而不是自动创建 skill
- 记录 session 摘要和 skill 使用结果
- 记录 Agent Runtime 的目标、任务、能力链路、策略、验证、恢复和演化审查状态

数据库生成方式：

- 克隆或复制 `.agent-os/` 后，不会立刻生成 SQLite 数据库。
- 首次调用 `scripts/memory-tools.py` 的任意命令时，会自动创建 `memory/index.db` 并应用 `memory/schema.sql`。
- `init` 是显式初始化和健康检查命令，不是必须先执行的安装步骤。
- 如果只手动编辑 Markdown memory 文件，不调用 memory tools，则不会生成 SQLite 数据库。

执行要求：

- SQLite 不会自动监听 Markdown 文件变化，写入 Markdown memory 不会自动同步到 `index.db`。
- 当任务涉及接口、数据模型、跨模块链路、重复 bug、可复用决策、Agent OS 规则调整，或用户明确要求“记住/沉淀/记录”时，任务结束前必须执行 `record-session`。
- 当任务产生可复用经验、已实现功能记录、踩坑修复、重要决策或稳定用户偏好时，还必须执行 `record-item`。
- 复杂任务可以把 memory 写入委派给 Memory Recorder 子代理并行处理，但主 Agent 最终仍要确认记录完成。
- 如果工具不可用或执行失败，最终回复必须说明原因，并给出后续可补执行的命令。

显式检查：

```bash
python scripts/memory-tools.py init
```

搜索历史经验：

```bash
python scripts/memory-tools.py search "login viewport overflow"
```

搜索真实报错或带符号的文本也可以，脚本会自动把普通输入转换为安全的 FTS5 查询：

```bash
python scripts/memory-tools.py search "5MB -> 4.5MB upload display"
```

导入老项目已有 Markdown memory：

```bash
python scripts/memory-tools.py import-markdown --project my-project
```

批量导入所有项目 memory：

```bash
python scripts/memory-tools.py import-markdown --all-projects
```

导入是幂等的，重复执行会更新已有导入记录，不会制造重复项。导入后的 SQLite 记录只是检索索引，重要细节仍应回到 Markdown 原文确认。

记录结构化经验：

```bash
python scripts/memory-tools.py record-item \
  --project my-project \
  --type lesson \
  --title "Login page overflow at 1024x768" \
  --summary "Brand typography and spacing caused unnecessary scroll." \
  --solution "Use ui-design-system type scale and viewport checks." \
  --tags ui login viewport \
  --validation "Checked 1024x768, 1280x800, and 1440x900."
```

记录已实现功能：

```bash
python scripts/memory-tools.py record-item \
  --project my-project \
  --type feature \
  --title "Login flow with dashboard entry" \
  --summary "Implemented split login page, mock login action, and dashboard entry." \
  --patterns auth-layout dashboard-entry route-flow \
  --files src/pages/Login.tsx src/pages/Dashboard.tsx \
  --tags auth ui routing \
  --validation "Verified login click enters dashboard."
```

记录候选 skill：

```bash
python scripts/memory-tools.py candidate-upsert \
  --name viewport-fit-auth-layout \
  --project "*" \
  --trigger "Auth or single-task page uses split layout and must avoid unnecessary viewport scroll." \
  --evidence "Repeated login page overflow caused by oversized brand typography and padding." \
  --validation "Resolved by design-system type scale and common viewport checks." \
  --scope "Login, register, forgot password, simple settings pages." \
  --boundary "Not for long-form onboarding or content-heavy pages." \
  --tags ui auth viewport
```

边界：

- `memory/index.db` 是本地索引，已被 `.gitignore` 忽略
- `memory/schema.sql`、`scripts/memory-tools.py`、`scripts/agent-runtime.py`、`scripts/agent_store.py`、`tools/memory-tools.md`、`tools/agent-runtime.md` 可以提交和审查
- Markdown memory 仍是人类可读、Git 可审查的主要记忆层
- Agent OS 没有后台自主记忆大脑，不会自动读取完整聊天记录或自动把对话写入长期记忆；Runtime 记录也必须由 Agent 在任务过程中显式写入
- 用户偏好只有在明确表达为长期偏好，或跨任务稳定出现，并通过 Memory Gate 判断后，才写入 `memory/global/preferences.md`
- SQLite 不会自动修改 skill、rule 或 AGENTS
- skill/rule 升级仍然必须经过 Review Gate 或用户确认

## 隔离机制

为了避免不同项目之间互相污染，这套系统默认：

- 每个项目单独写 `memory/projects/{project}.md`
- 禁止把 A 项目的业务细节写进 B 项目 memory
- 技术栈和项目识别先于 skill 选择
- 记忆分为 `Summary` 和 `Detailed Records`

简单理解：

- 共性的东西进 rule / skill / global memory
- 项目特有的东西进 project memory

## 演化机制

经验升级路径：

```text
project memory -> skill -> rule
```

这是一条受控演化路径，不是自动自我升级。Agent 可以记录高价值经验、稳定用户偏好、candidate skill/rule 和 session 摘要，但不能基于一次对话自动修改 `AGENTS.md`、`rules/` 或 `skills/`。任何从 memory 升级到 skill/rule 的动作，都必须满足触发场景、出现次数、验证证据、适用范围和边界要求，并经过 Review Gate 或用户确认。

写入 project memory 的典型情况：

- 项目特定的技术栈、架构、约束或关键依赖
- 已验证的非常规问题解决方案
- 会影响后续任务的验证失败根因、修复路径或待验证项
- 可能复用但证据不足的 `[candidate-skill]` 或 `[candidate-rule]`

升级为 skill 前至少需要：

- 触发场景清晰
- 同项目或跨项目重复出现
- 有可复现验证证据
- 适用范围和不适用范围明确
- 不会吞并其他 skill 或 rule 的职责

升级为 rule 前还需要：

- 已作为 skill 稳定运行
- 跨项目可复用
- 不依赖强业务语义
- 作为规范比作为流程更合适

## 维护原则

- 高频更新 `memory/`
- 中频更新 `skills/`
- 低频更新 `rules/`
- 极低频更新 `AGENTS.md`

维护时应遵守：

- 不把一次性 workaround 写成 skill 或 rule
- 不因为出现新技术栈就新增 stack-specific skill
- 不用临时占位、半成品或 MVP 式方案替代系统性调整
- 修改 skill 前说明复用价值和触发场景
- 修改 rule 前说明稳定性证据和适用边界
- 修改 AGENTS / rules / skills 或高风险跨层变更时，执行 Review Gate 或等价一致性检查
- 完成任务后说明验证结果、失败处理和剩余风险，而不是只说“已完成”

## FAQ

### 为什么叫 Agent OS？

`Agent OS` 强调的是一套面向 AI Coding Agent 的执行操作层：规则、技能、记忆、gate、规划和演化机制在这里统一维护，再服务多个项目。项目自己的业务信息不会写回全局规则，而是隔离在 project memory 中。

### 它是全栈系统吗？

是全栈 Agent OS，但不是“所有技术栈都内置完整规则”。当前系统以通用 rules、任务层 skills 和项目现有模式为主，已有 React、Node、Taro / Mini Program 等规则，其他技术栈会按项目上下文落地。

### 我需要给每个项目单独建 AGENTS.md 吗？

需要一个很薄的项目根入口 `AGENTS.md`。它不复制 Agent OS 核心规则，只负责告诉 AI Coding Agent 当前项目使用 `.agent-os/` 下的 Agent OS，并允许项目补充少量专属规则。

### 项目差异写在哪里？

写到 `memory/projects/{project}.md`。全局只保留跨项目稳定成立的偏好、模式和规则。

### README 和 AGENTS.md 的区别是什么？

`README.md` 给人读，用来理解项目定位、结构和使用方式。`AGENTS.md` 给 agent 执行，包含更细的流程、路由和约束。
