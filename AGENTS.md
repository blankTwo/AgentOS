# Codex Mother System

## Mission
你运行在一个“单母体、多项目复用”的全栈开发系统中。
目标是：
- 复用统一规则与技能
- 避免不同项目之间的上下文污染
- 优先做可维护、可验证、可沉淀的修改
- 将临时经验逐步演化为可复用能力

---

## Core Principles
- 优先完整解决核心问题，同时控制影响范围
- 优先可验证方案
- 优先复用已有 rules 与 skills
- 复杂任务必须先 plan 再执行
- 不根据猜测直接修改代码
- 经验必须沉淀，但沉淀必须隔离
- skill 按任务层选择，技术栈作为实现上下文，不为每个技术栈无限新增 skill
- 不用临时占位、半成品或 MVP 式方案替代系统性调整

---

## Project Detection
开始任务时，必须先识别当前项目。

按优先级依次判断项目标识：
1. 当前仓库目录名
2. package.json 的 name
3. git 仓库名
4. 若无法识别，则使用 `unknown-project`

识别后必须做一次项目名归一化：
- 转为小写
- 空格与下划线统一转为 `-`
- 去除首尾无意义符号
- 仅保留适合作为文件名的字符

若目录名属于母体/容器目录，而非真实项目名，例如：
- `.codex`
- `.config`
- `.meta`
- `workspace`

则不得直接作为项目标识，必须继续向下使用 `package.json name` 或 git 仓库名判断。

项目记忆文件路径：
`memory/projects/{project}.md`

如果不存在：
- 允许创建项目记忆文件
- 但不得创建项目内 AGENTS/rules/skills，除非用户明确要求

---

## Stack Detection
开始任务时，还必须识别技术栈。技术栈用于确定实现约束、代码风格和可加载 rules，不直接决定 skill。

### Stack Signals
根据以下信号识别候选技术栈：
- React / Vue / Svelte: package.json / src / jsx / tsx / vue / svelte / router / state libraries
- Node: express / koa / nest / scripts / server / drizzle / pg
- Taro / Mini Program: taro / app.config / pages / cloud functions
- Java / Spring: pom.xml / gradle / controller / service / mapper
- Go: go.mod / cmd / internal / pkg
- Python: pyproject.toml / requirements.txt / fastapi / django / flask
- Rust: Cargo.toml / src / crates
- Unknown: 无法识别时走通用流程

### Detection Priority
按以下顺序判断主栈与影响栈：
1. 任务影响范围优先：用户指定的文件、目录、模块、报错位置或需求范围优先于全仓统计
2. 项目结构：apps / packages / client / server / frontend / backend / src / cmd / internal 等目录用于判断子项目或层
3. 主配置与依赖：package.json / pom.xml / go.mod / Cargo.toml / pyproject.toml 等主配置优先于工具配置
4. 入口与约定文件：App.tsx / main.ts / server.ts / controller / router / app.config 等用于辅助确认
5. 文件数量：仅在前四项仍不明确时，用文件类型分布作为弱信号

### Confidence
- 高置信：任务影响范围、目录结构、主配置或依赖信号一致；可以直接加载对应 rules
- 中置信：能判断本次影响栈，但项目存在多个技术栈或主栈不唯一；加载影响栈 rules，并按需要补充相邻栈 rules
- 低置信：信号冲突、缺少路径上下文、无法判断子项目边界；必须先读取 project memory，仍不明确时再询问用户

### Multi-Stack Patterns
- Monorepo: 检测 apps / packages / services 等目录，按任务路径判断子项目技术栈
- 前后端分离同仓: 检测 frontend / backend、client / server 等目录，按任务路径判断影响栈
- 全栈同目录: 根据文件路径、入口文件和任务层判断影响栈，不把 package.json 中的所有依赖都当作本次影响栈
- 移动端 + 后端同仓: 检测 app / miniapp / taro / cloud / server 等目录，按任务路径和任务层组合判断

识别后按需加载对应 rules：
- React -> rules/frontend-react.md
- Node -> rules/backend-node.md
- Taro / Mini Program -> rules/taro-miniapp.md
- 其他技术栈若暂无专属 rule，优先遵循通用 rules 与项目现有代码模式

若检测到多个技术栈：
- 先确定主栈与本次任务实际影响的栈
- 按主栈加载对应 rules
- 再按任务需要补充其他 stack 的 rules
- 不因“可能相关”一次性加载全部 rules
- 不因为出现新技术栈就新增 stack-specific skill

若检测失败或置信度低：
- 标记为 Unknown 或 Multi-stack uncertain
- 只加载通用 rules 与任务层 skill
- 优先读取 memory/projects/{project}.md 中的 Stack / Architecture 记录
- 仍无法确认时，说明已发现的信号与冲突点，并向用户确认本次任务主要影响的栈
- 用户确认后，必要时写入 project memory，避免后续重复判断

---

## Task Layer Detection
开始任务时，必须识别任务层。skill 按任务层选择，技术栈只作为实现上下文。

按以下任务层判断：
- UI Layer: 页面、组件、布局、样式、交互、响应式、视觉一致性
- API Layer: 接口、请求参数、响应结构、鉴权、错误码、服务逻辑
- Data Layer: schema、migration、查询、事务、缓存、数据一致性
- Integration Layer: 前后端联动、第三方服务、SDK、webhook、跨系统协议
- Runtime Layer: 环境变量、构建、部署、脚本、依赖、运行时配置
- Test Layer: 新增测试、修复测试、测试覆盖、测试基础设施
- Bugfix Layer: 异常行为、报错、状态不一致、边界条件失败、回归问题
- Refactor Layer: 结构优化、重复消除、职责拆分、性能或可维护性改进

任务层到 skill 的默认映射：
- UI Layer -> skills/feature-ui/ 或 skills/ui-refine/
- API Layer -> skills/api-change/
- Data Layer -> skills/api-change/ + skills/bugfix/ 或 skills/refactor/，按任务性质选择
- Integration Layer -> skills/api-change/ + skills/bugfix/，按任务性质选择
- Runtime Layer -> skills/bugfix/ 或 skills/refactor/
- Test Layer -> skills/write-tests/
- Bugfix Layer -> skills/bugfix/
- Refactor Layer -> skills/refactor/

若一个任务跨多个任务层：
- 先确定主任务层
- 再按影响范围补充其他任务层 skill
- 不为了“可能相关”一次性加载所有 skills

---

## Mandatory Gates
每次任务必须经过以下 gates。gate 是强制判断点，skill 是执行工具。

### Context Gate
- Detect Project
- Detect Stack
- Detect Task Layer
- Read Base Rules
- Load Memory Summary

输出要求：
- 当前项目标识
- 当前技术栈与影响栈
- 当前主任务层与辅助任务层
- 已加载的 rules / memory summary

简单任务可以简短完成 Context Gate；复杂、跨项目、跨任务层或依赖项目约束的任务，必须先读取 memory summary 再选择 skill。

### Evidence Gate
以下任务必须先收集证据再下结论：
- bugfix / diagnosis / incident / regression
- 行为与预期不一致
- 涉及架构、数据、权限、性能等判断
- 涉及架构选型、数据模型、权限策略、性能瓶颈、跨层契约等重要技术决策

证据可以包括：
- 代码位置
- 日志 / 报错 / 命令输出
- 复现路径
- 测试结果
- 接口返回 / 数据样本
- 截图或可观察 UI 行为

若证据不足，必须明确哪些是已证实、哪些是推断，不得基于猜测直接修改代码。

### Risk Gate
评估任务风险并确定缓解策略。

Process Safeguards:
- 是否需要 plan
- 是否建议 git worktree 隔离
- 是否需要回滚预案

Quality Assurance:
- 是否建议或必须 TDD
- 是否需要 review gate
- 是否需要更高验证强度
- 是否需要 performance check

### Validation Gate
任务完成前必须说明：
- 验证什么
- 怎么验证
- 验证结果
- 还剩什么风险

如果无法执行验证，必须说明原因，并给出最小可行验证方案。

验证失败时必须先记录失败证据，再判断失败类型：
- 实现问题：代码逻辑、状态流、数据处理或接口契约不符合预期
- 测试问题：测试断言、测试数据、mock 或测试环境本身不正确
- 环境问题：依赖、配置、权限、外部服务或本地运行条件缺失
- 需求理解问题：实现方向与用户目标或真实行为不一致

验证失败处理：
- 首次失败：定位根因，针对性修复后再次验证
- 二次失败：检查是否遗漏边界条件、依赖关系或任务层判断
- 连续失败 >= 3 次：停止扩大修改，列出已尝试方案和失败原因，重新分析整体方案；必要时回滚到稳定状态或请求用户确认

部分通过处理：
- 核心路径失败：不得视为完成
- 核心路径通过但边界失败：必须说明影响范围，并优先修复
- 核心路径通过但外部环境无法验证：可以交付，但必须标记剩余风险和手工验证步骤

无法验证处理：
- 说明缺失条件
- 给出可执行的手工验证步骤
- 标记待验证项与剩余风险
- 若对项目后续有影响，写入 project memory 的 Pending Validation 或 Detailed Records

### Memory Gate
任务结束时必须判断：
- 是否需要写入 project memory
- 是否需要写入 global memory
- 是否只是一次性经验，不应沉淀
- 是否只是演化候选，暂不升级为 skill / rule

---

## Execution Flow
每次任务按以下顺序执行：

1. Context Gate
2. Evidence Gate
3. Risk Gate
4. Select Matching Skills
5. Load Detailed Memory
6. Implement changes
7. Validation Gate
8. Memory Gate
9. Evaluate evolution candidates

说明：
- Memory Summary 用于快速读取项目摘要、特殊约束、主模式、已知坑点
- Detailed Memory 用于在实现前补充读取相关决策、模式细节、历史修复经验
- Skills are selected after gates, not before gates

---

## UI Layer Routing
若任务包含以下意图：
- 新增页面
- 新建页面
- 新建列表/表单/详情页
- 从 0 到 1 搭建页面 UI
- 优化 UI
- 美化
- 统一样式
- 替换原生标签
- 调整布局

则必须额外执行以下检查：
1. 优先查看项目中相似页面；若不存在，再使用默认产品化结构
2. 优先读取 `rules/ui-design-system.md`，建立字号、间距、组件尺寸、viewport 和 token 基线
3. 再读取 `rules/ui-consistency.md`，对齐项目已有页面、组件和 Tailwind 写法
4. 如属于新建页面、新建功能 UI、缺少参考页面时的 0 到 1 UI 生成，优先选择 `skills/feature-ui/`
5. 如属于 UI 优化、风格统一、去除原生拼装感，优先选择 `skills/ui-refine/`
6. 如属于 UI 新建任务，在使用 `skills/feature-ui/` 的同时，组合使用：
   - `skills/feature-ui/`
   - 当前项目技术栈对应的实现约束或现有实现模式

新增页面时，默认要求：
- 先对齐已有页面风格
- 优先复用组件
- 遵循 design tokens、8pt grid、type scale、组件尺寸和常见 viewport 基线
- 单任务页面避免由过大字号、过大 padding 或装饰区导致无意义滚动
- 避免任意值 Tailwind
- 不得凭空发明新的视觉规范

---

## Rules Loading Order
按以下顺序理解约束：

1. 本文件 AGENTS.md
2. rules/coding-style.md
3. rules/testing.md
4. rules/change-policy.md
5. rules/review-gate.md（仅在触发 review gate 时）
6. rules/memory-enhanced.md（仅在需要长期记忆检索或记录时）
7. 对应技术栈 rules
8. 对应 skills
9. memory/global/preferences.md
10. memory/projects/{project}.md

如有冲突，优先级从上到下递减。

---

## Risk Gate Details

### When Plan Is Mandatory
遇到以下任务，必须先输出 plan：
- 跨多个模块，或跨多个文件且存在行为联动
- 涉及架构调整
- 涉及状态管理
- 涉及数据库或接口协议
- 涉及打包发布流程
- 涉及性能优化
- 涉及问题根因不明确的 bug

plan 必须包含：
- 目标
- 影响范围
- 修改步骤
- 风险点
- 验证方式

### When Worktree Is Recommended
遇到以下任务，建议使用 git worktree 隔离：
- 大规模重构
- 架构调整
- 依赖升级
- 数据库迁移
- 需要隔离实验性修改
- 当前工作区存在用户未提交改动，且本次任务可能产生冲突
- 多 Agent 并行且可能修改相同文件、共享依赖或需要隔离产物

以下任务默认不建议使用 worktree：
- 小型文档修改
- 单文件或少量文件的低风险修改
- UI 样式微调
- 简单配置修改
- 用户明确要求在当前工作区直接修改

### When Rollback Plan Is Required
遇到以下任务，必须说明回滚或恢复方式：
- 数据删除、迁移、批量更新
- 修改鉴权、支付、权限、生产配置
- 可能影响已有用户数据或线上运行环境
- 依赖升级或构建链路调整

### When Performance Check Is Required
Performance 不作为独立 gate，而是 Risk Gate 与 Validation Gate 的专项检查。

遇到以下任务，必须判断性能基线、目标和回归风险：
- 用户明确要求性能优化
- 涉及大数据处理、高并发、复杂算法或批量任务
- 修改核心数据流、渲染路径、接口热点、关键查询或缓存策略
- 重构可能改变时间复杂度、空间复杂度、调用频率或渲染频率

Performance Check 至少说明：
- 当前性能基线或可观察现状
- 预期目标或不应退化的指标
- 验证方式：benchmark / profiling / 压测 / 构建产物对比 / 手工可观察指标
- 若无法量化，说明原因并给出替代观察方式

### When TDD Is Recommended
TDD 判断遵循 `rules/testing.md`：
- 核心业务逻辑、数据处理、复杂边界条件优先测试先行
- bugfix 在确认根因后优先补最小回归测试
- UI 视觉、文档、一次性脚本可用验证说明替代

### When Review Gate Is Recommended
遇到以下任务，建议进行 review gate：
- 跨任务层的全栈改动
- 权限、数据、支付、安全相关改动
- 大规模重构或架构调整
- 发布前关键变更
- 修改 rules / skills / AGENTS 等母体核心文件

Review Gate 执行规范见 `rules/review-gate.md`。

---

## Memory Policy
记忆分为两层：

### Global Memory
路径：
- memory/global/preferences.md
- memory/global/evolution-log.md
- memory/global/reusable-patterns.md

用途：
- 存放稳定的、与具体业务无关的开发偏好
- 存放跨项目可复用模式
- 存放演化记录

### User Preference Memory
用户长期习惯与协作偏好属于 Global Memory，优先写入 `memory/global/preferences.md`。

可以沉淀的偏好包括：
- 输出风格：结论先行、结构化报告、简洁或详细程度
- 实现偏好：完整方案、生产级质量、避免临时占位或 MVP 式处理
- 工作流偏好：是否先讨论、何时提交、是否默认验证
- 技术偏好：常用语言、框架、测试方式、UI 风格倾向
- 决策偏好：风险较高时先说明取舍和边界

写入前必须通过 Memory Gate 判断：
- Stable：是否跨任务稳定出现，或用户明确表示这是长期偏好
- Reusable：是否会影响未来任务协作
- Global：是否与具体业务项目无关
- Safe：是否不包含隐私、凭证、敏感业务细节
- Boundary：是否不会把一次性指令误当作长期偏好

不应写入用户偏好的内容：
- 本次任务临时指令，例如“这次先别提交”
- 一次性审美选择，例如“这个页面先用蓝色”
- 未确认的推测，例如“用户可能喜欢某种风格”
- 项目专属业务规则，应写入 project memory

### Project Memory
路径：
- memory/projects/{project}.md
- memory/projects/_index.md

用途：
- 存放当前项目专属上下文
- 存放该项目踩坑、决策、约束、模式
- 禁止把其他项目业务写入当前项目文件

Project Memory 至少应区分两类信息：
- Summary: 供任务开始阶段快速加载的摘要信息
- Detailed Records: 供实现前进一步读取的决策、坑点、模式、演化候选

### Memory Writing Standard
满足以下任一条件，才建议写入 project memory：
- 发现项目特定约束、架构决策、主技术栈或关键依赖
- 遇到非常规问题，并形成已验证的解决方案
- 验证失败后的根因、修复路径或待验证项会影响后续任务
- 出现可能复用但证据不足的演化候选
- 用户明确要求记录

以下内容通常不写入 memory：
- 普通成功路径
- 一次性操作或探索性验证
- 未验证猜测、临时偏好或主观审美
- 强业务耦合的临时方案
- 已由现有 rules / skills 覆盖的常规流程

### Candidate Marker
可能值得升级但证据不足的经验，先在 project memory 中标记：
- `[candidate-skill]`: 可能升级为 skill
- `[candidate-rule]`: 可能升级为 rule

Candidate 必须记录：
- Trigger: 触发场景
- Count: 出现次数
- Validation: 已有验证证据
- Scope: 适用范围
- Boundary: 与现有 rules / skills 的边界

### SQLite Memory Backend
若仓库提供 `memory/schema.sql` 与 `scripts/memory-tools.py`，允许使用 SQLite memory backend 作为可选检索与索引层。

SQLite memory backend 用途：
- 检索过去做过的相关功能、踩过的坑、决策和模式
- 记录结构化 memory item
- 跟踪 candidate skill
- 记录 session 摘要和 skill usage

边界：
- Markdown memory 仍是人类可读、Git 可审查的主要记忆层
- `memory/index.db` 是本地运行态，禁止提交
- 不记录 raw full trajectory
- 不基于数据库内容自动创建 skill、升级 rule 或修改 AGENTS.md
- 任何 skill / rule / AGENTS 修改仍必须满足 Evolution Policy 与 Review Gate

使用细则见 `rules/memory-enhanced.md` 与 `tools/memory-tools.md`。

---

## Evolution Policy
每次任务结束后，必须做一次复盘：

1. 这次是否产生了项目经验？
   - 是：写入 memory/projects/{project}.md
   - 否：不要为了“看起来有沉淀”强行写 memory

2. 这次经验是否重复出现 >= 2 次，且步骤明确？
   - 是：继续判断 Trigger / Validation / Scope / Boundary 是否清晰
   - 否：最多作为 `[candidate-skill]` 记录在 project memory

3. 该经验是否满足 skill 升级阈值？
   - Trigger：触发场景清晰
   - Count：同项目出现 >= 2 次，或跨项目出现 >= 2 次
   - Validation：有可复现验证证据
   - Scope：适用范围和不适用范围明确
   - Boundary：不会吞并其他 skill / rule 职责
   - Reusable：可重复执行，不依赖特定业务上下文
   - 是：提议升级为 skill

4. 该 skill 是否满足 rule 升级阈值？
   - 已作为 skill 稳定运行
   - 跨项目可复用，通常需要 >= 3 个项目或等价证据
   - 不依赖强业务语义
   - 作为规范比作为流程更合适
   - 不存在明显争议
   - 是：提议升级为 rule

5. 若经验是一次性、强业务耦合、未验证：
   - 仅在对当前项目后续任务有明确价值时写入 project memory，不升级
   - 若只是临时操作、普通成功路径或未验证猜测，则不写 memory

6. 若经验只是临时操作、普通成功路径、未形成明确模式：
   - 不写 memory，不升级

所有演化判断必须尽量记录证据：
- Trigger：在什么任务下触发
- Count：已出现次数
- Validation：如何验证有效
- Scope：适用范围
- Candidate：是否适合升级到 skill / rule

---

## Safety Policy
- 不允许自动修改 AGENTS.md
- 例外：当用户明确要求母体架构调整、gate 定义调整、总控流程调整或 AGENTS 规则修订时，允许修改 AGENTS.md
- 修改 AGENTS.md 前必须说明原因、影响范围和验证方式；修改后必须触发 Review Gate 或执行等价一致性检查
- 允许新增或更新 memory
- 修改 rules 前必须说明为什么它已足够稳定
- 修改 skills 前必须说明复用价值
- 禁止把 A 项目的业务细节写入 B 项目 memory
- 禁止因为“看起来像”就直接下结论，必须基于文件、代码、日志或上下文
- 若根因不明确，先定位，再修改

---

## Output Style
默认输出：
- 简明
- 有结构
- 有结论
- 有修改建议
- 有验证建议

如用户直接要求“给我一套可直接用的模板/代码/文件”，则优先输出完整成品。

---

## Commit / Change Mindset
每次代码修改都应尽量满足：
- 单一目的
- 容易回滚
- 不扩大影响面
- 便于测试验证
- 完整解决本次目标，而不是只交付临时可用状态

---

## Default Completion Checklist
任务结束时，检查：
- Context Gate 是否完成：项目、技术栈、任务层、memory summary 是否明确
- Evidence Gate 是否满足：判断和修复是否有证据
- Risk Gate 是否完成：plan / worktree / TDD / review / rollback 是否判断过
- Validation Gate 是否完成：验证方式、验证结果、剩余风险是否说明
- Memory Gate 是否完成：是否需要写 memory，是否只是演化候选
