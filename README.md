# Agent OS

Agent OS 是一套可放进任意项目的 AI Coding Agent 执行层。

它不绑定 Codex、Claude、Cursor、VSCode 或某个模型。你把它安装到项目的 `.agent-os/` 后，项目里的 AI Agent 就能按统一规则完成上下文识别、能力发现、计划、执行、验证、文档同步和记忆沉淀。

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
└── docs/
    └── agent-os/
```

## 快速开始

在 Agent OS 源码仓库中运行：

```bash
python scripts/agent-os.py install --target <your-project>
```

安装后检查：

```bash
python <your-project>/.agent-os/scripts/agent-os.py doctor --root <your-project>/.agent-os
python <your-project>/.agent-os/scripts/agent-os.py version --root <your-project>/.agent-os
```

打开用户项目后，AI Agent 会先读取项目根目录 `AGENTS.md`，再进入 `.agent-os/AGENTS.md` 加载规则、workflow、skills、memory 和 runtime 工具。

## 它做什么

| 能力 | 作用 |
| --- | --- |
| Context Gate | 识别项目、技术栈、任务层、业务影响、证据和风险 |
| Workflow Gate | 为简单修改、Bug、功能、API、Agent OS 演化选择执行流程 |
| Mutation Authorization Gate | 区分只读排查和授权修改，排查/分析/定位原因默认不改文件 |
| Mission IR Compiler | 将自然语言编译为 Mission IR；可使用本地规则或插件配置的 LLM |
| Mission Optimizer | 清洗、校验、归一化 Mission IR，并收紧权限生成 Locked Mission IR |
| Intent Runtime | 记录结构化意图、授权状态、置信度、风险、允许动作和阻断动作 |
| Execution Gate | 写入、补丁、提交、部署、memory/docs 更新前做硬门校验 |
| Feedback Loop | 记录反馈、检测 drift、重新锚定用户意图，并保存计划版本 |
| Event Bus | 事件消息可发布、拉取、确认，支持 Agent Kernel 与 runtime 服务之间闭环 |
| Scheduler | 维护可执行队列，按优先级、依赖、资源占用选择下一步 |
| Resource Manager | 用资源租约控制 workspace、shell、git、model、browser 等关键资源占用 |
| Quality Score | 根据验证、意图漂移、调度、文档、恢复、记忆和风险计算质量分 |
| Benchmark | 记录性能/质量基准、阈值、方向和回归状态，并接入 final-check |
| Runtime Self-Audit | 自动发现未关闭的 action、drift、事件、调度、资源、验证缺口 |
| Compatibility Matrix | 汇总模型 provider、IDE/host adapter、入口文件和缺失能力 |
| Governance Proposal | 规则、skill 升级只能进入人工 review，不自动提升 |
| Planning Gate | 决定直接执行、短计划还是完整计划 |
| Capability Discovery | 判断功能链路是完整、半套、断链、缺失还是未确认 |
| Agent Runtime | 记录 goal、task、policy、intent、action、feedback、verification、recovery、trace |
| Documentation Gate | 判断 README or docs、`docs/agent-os/`、memory 是否需要同步 |
| Memory Gate | 把可复用经验写入 Markdown memory / SQLite memory |
| Evolution Policy | 只记录候选升级，不自动修改 rules / skills / AGENTS |

核心目标不是“多写几个 skill”，而是让 AI Agent 在项目内按可验证、可回滚、可审查、尊重用户意图边界的方式工作。

例如用户只说“排查一下”“分析一下”“看看为什么”，Agent OS 会把任务当成只读诊断。即使后续发现候选修复，写文件、打补丁、提交、部署、更新 memory/docs 也必须先通过 Execution Gate；没有明确授权时会被记录为 blocked，而不是直接执行。

## Mission IR

Agent OS 不直接把自然语言交给 Runtime 执行，而是先编译成 Mission IR。

```text
User Request
  -> Semantic Compiler
  -> Draft Mission IR
  -> Validator / Normalizer / Optimizer
  -> Locked Mission IR
  -> Execution Gate
  -> Runtime
```

默认使用内置规则算法。VSCode 插件可配置 OpenAI-compatible LLM Provider 的 `apiKey`、`baseUrl` 和 `model`，用于增强语义编译。LLM 只负责生成 Draft Mission IR；最终权限仍由 Agent OS 的 Validator、Optimizer 和 Execution Gate 决定。

```bash
python scripts/agent-runtime.py runtime-compile-mission \
  --project my-project \
  --request "用户反馈第一次检测原创度0，第二次检测就好了，你好好排查一下"
```

只读诊断会被锁定为 `diagnose + readonly + allowWrite=false`。如果 LLM 超时、返回 Markdown 包裹、坏 JSON、字段不合规或上游 502，Runtime 会清洗和归一化；无法恢复时自动回退本地规则算法。

## 常用命令

产品 CLI：

```bash
python .agent-os/scripts/agent-os.py doctor
python .agent-os/scripts/agent-os.py version
python .agent-os/scripts/agent-os.py migrate --dry-run
python .agent-os/scripts/agent-os.py migrate
python .agent-os/scripts/agent-os.py dashboard --project my-project --data-output docs/agent-os/dashboard.json
python .agent-os/scripts/agent-os.py quality-trends --project my-project --output docs/agent-os/quality-trends.json
python .agent-os/scripts/agent-os.py policy-packs
python .agent-os/scripts/agent-os.py security-check --output docs/agent-os/security-report.json
python .agent-os/scripts/agent-os.py release-check
```

底层 Runtime 命令与产品 CLI alias 对应：

```text
runtime-doctor -> agent-os doctor
runtime-version -> agent-os version
runtime-migrate -> agent-os migrate
runtime-migrate --dry-run -> agent-os migrate --dry-run
runtime-dashboard -> agent-os dashboard
runtime-quality-trends -> agent-os quality-trends
runtime-policy-packs -> agent-os policy-packs
runtime-security-check -> agent-os security-check
runtime-vscode-protocol -> agent-os vscode-protocol
runtime-distribution -> agent-os distribution
runtime-team-workspace -> agent-os team-workspace
runtime-release-check -> agent-os release-check
```

## 安装与分发

| 方式 | 适用场景 | 升级方式 |
| --- | --- | --- |
| `agent-os install` | 默认推荐，一条命令接入项目 | 重新运行 `install --force` 后运行 doctor / migrate |
| 复制到 `.agent-os/` | 简单项目或手动接入 | 覆盖 `.agent-os/` 后运行 doctor / migrate |
| clone 为 `.agent-os` | 希望保留 Agent OS Git 历史 | 在 `.agent-os/` 内 `git pull` 后运行 doctor / migrate |
| Git submodule / subtree | 团队多项目统一版本 | 更新指针或 subtree 后运行 doctor / migrate |
| VSCode 插件注入 | 编辑器按钮安装或更新 | 插件写入 `.agent-os/` 和根 `AGENTS.md`，面板展示状态与总览 |
| 包管理器分发 | 未来产品化安装方式 | 包安装后仍以 `.agent-os/` 布局落地 |

## VSCode 插件

源码仓库内的 `vscode-plugin/` 是一个独立 VSCode 插件子项目。

它负责：

- `Agent OS: Inject Workspace`：把当前仓库安装成 Agent OS 工作区
- `Agent OS: Refresh Status`：运行 doctor / runtime-summary / protocol 并刷新状态
- `Agent OS: Open Overview`：生成并打开 `docs/agent-os/dashboard.html`

插件面板只观察和触发 Agent OS 状态命令，不承载聊天运行时；核心规则、workflow、skills、memory 和 runtime 仍由 `.agent-os/` 提供。

## 项目文档边界

`.agent-os/` 是 Agent OS 系统目录，不保存用户项目的执行计划、业务决策或验证报告。

用户项目里的执行文档固定放到：

```text
docs/agent-os/
├── plans/
├── tasks/
├── decisions/
├── reviews/
└── verification/
```

边界规则：

- 实施计划：`docs/agent-os/plans/`
- 任务拆解：`docs/agent-os/tasks/`
- 技术或业务决策：`docs/agent-os/decisions/`
- Review / 审计 / 复盘：`docs/agent-os/reviews/`
- 验证记录：`docs/agent-os/verification/`
- 项目长期记忆：`.agent-os/memory/projects/{project}.md`
- 本地 SQLite 运行态：`.agent-os/memory/index.db`

Documentation Gate 要求：当安装、命令、行为、配置、API、部署、排错、规则或 workflow 变化时，必须更新 README or docs；如果不需要更新，最终回复要说明 why no documentation update was needed。

Memory is not documentation. Runtime records are not documentation. Memory 和 Runtime 可以提供证据，但不能替代 README、项目 docs 或 `docs/agent-os/`。

## Memory

Agent OS Memory 有两层：

- Markdown memory：人类可读、可审查，保存项目约束、决策、坑点和可复用经验。
- SQLite memory：本地结构化索引，用于检索、session 记录、candidate skill 和 runtime 状态。

`memory/index.db` 是本地运行态，已被 `.gitignore` 忽略，不应该提交。

常用命令：

```bash
python scripts/memory-tools.py init
python scripts/memory-tools.py search "login viewport overflow"
python scripts/memory-tools.py record-session --project my-project --task-summary "..."
python scripts/memory-tools.py record-item --project my-project --type lesson --title "..." --summary "..."
```

Agent OS 没有后台自主记忆大脑，不会自动读取完整聊天记录，也不会自动把对话写入长期记忆。记忆写入必须经过 Memory Gate。

## Skill 路由

| 任务 | 默认 skill |
| --- | --- |
| 修复 bug、异常行为、状态不一致 | `skills/bugfix/` |
| 新增或修改接口 | `skills/api-change/` |
| 新建页面、列表、表单、详情、dashboard | `skills/feature-ui/` |
| React 页面或交互落地 | `skills/feature-react/` |
| 优化已有 UI、统一风格 | `skills/ui-refine/` |
| 结构优化、职责拆分、重复消除 | `skills/refactor/` |
| 新增测试或补回归测试 | `skills/write-tests/` |

技术栈是实现上下文，不是 skill 的主要分类方式。

## 源码结构

```text
AgentOS/
├── AGENTS.md
├── README.md
├── VERSION
├── context/
├── workflows/
├── rules/
├── skills/
├── tools/
├── scripts/
├── memory/
├── policy-packs/
└── tests/
```

## 开发验证

```bash
python -m py_compile scripts/agent-os.py scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py
python -m unittest tests.test_agent_runtime
python scripts/agent-os.py doctor
python scripts/agent-os.py release-check
git diff --check
```

## FAQ

### 为什么叫 Agent OS？

因为它提供的是 Agent 的项目级操作层：入口、规则、workflow、skill、memory、runtime、验证和演化治理，而不是某个具体模型的插件。

### 它只支持 Codex 吗？

不是。Agent OS 是 model-agnostic 的。Codex、Claude、Cursor、VSCode 插件或其他宿主都可以通过项目根 `AGENTS.md` 和 `.agent-os/` 使用它。

### 用户必须手写根目录 AGENTS.md 吗？

不需要。`agent-os install` 会生成根目录 `AGENTS.md`。用户只需要按需修改 `Agent display name` 或追加项目专属规则。

### 项目经验写在哪里？

项目经验写入 `.agent-os/memory/projects/{project}.md`。Agent OS 源码仓库本身不提交具体项目的业务记忆。
