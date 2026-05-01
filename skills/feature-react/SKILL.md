---
name: feature-react
description: 用于已确认是 React 项目的实现辅助，负责将 UI / API / 状态 / 交互需求落地为符合当前 React 项目模式的代码。适用于新增或修改 React 页面、组件、hooks、状态逻辑、请求流程，或承接 `feature-ui` 的页面结构。该 skill 是当前 React 项目的实现辅助，新技术栈不应复制此模式，除非已在多个项目中验证稳定复用价值且有清晰边界。
---

# Goal
在已确认项目使用 React 时，以符合当前项目习惯的方式实现页面和功能，包括：
- 组件拆分
- hooks 使用
- 状态组织
- 请求流程接入
- 事件与交互实现

该 skill 关注“如何在 React 中实现”，而不是“页面应该长什么样”。
它是当前 React 项目的实现辅助，不是为每个技术栈复制一份 skill 的范式。

# Scope
适合处理：
- 新增 React 页面并落地为具体组件代码
- 新增 React 组件、交互与页面逻辑
- 识别代码应放在 component / hook / store / api 的位置
- 实现查询、提交、局部状态与副作用逻辑
- 承接 `feature-ui` 产出的页面结构并转为 React 代码

不负责处理：
- 跨框架通用 UI 生成策略
- “去 AI 感”、统一风格、页面观感优化
- 脱离 React 上下文的纯视觉结构设计
- 组件库或设计系统本体的定义
- 为 Vue / Svelte / Taro / Native 等其他技术栈提供通用实现模板

# Use With Other Skills
- 若任务是从 0 到 1 新建页面 UI，先使用 `feature-ui`，再用本 skill 落地 React 实现
- 若任务是优化已有页面观感和一致性，优先使用 `ui-refine`
- 若任务既有新页面 UI 又有 React 实现，组合使用 `feature-ui` + `feature-react`
- 若任务是 API / Data / Integration 层变化，本 skill 只负责 React 调用方和状态接入，接口契约仍由对应任务层 skill 决定

# Input from feature-ui
若承接 `feature-ui` 的输出，先检查以下内容是否明确：
- 页面结构是否清晰，主区块与次区块是否已定义
- 组件边界是否明确，哪些部分应拆成组件是否可判断
- 状态覆盖是否完整，至少包含关键的加载、空态、错误和成功反馈
- 交互流程是否明确，关键操作的触发与反馈是否可实现
- 平台适配点是否已标出，是否需要针对当前平台补充处理

若以上信息缺失，不要直接进入 React 代码实现；先补齐结构和交互定义，再继续落地。

# Steps
1. 确认 Context Gate 已识别为 React 项目，并读取项目现有组件、状态、请求模式
2. 明确功能目标、任务层来源和 React 侧职责边界
3. 明确 UI、状态、数据来源、接口契约和错误反馈
4. 识别应放在 component / hook / store / api 的位置
5. 优先复用已有组件、hooks、请求封装、路由和状态模式
6. 按层实现，避免把数据请求、状态转换和 UI 细节堆在单个组件中
7. 处理 loading / empty / error / success / disabled 等状态
8. 按 `rules/testing.md` 判断是否需要测试先行或补充回归测试
9. 验证主流程、关键边界、错误路径和响应式表现
10. 将项目特有 React 模式写入 project memory，通用实现经验再考虑升级

# Output
- 功能拆分
- React 组件与 hooks 组织方式
- 关键状态流
- 影响文件
- 验证结果与剩余风险

## Boundaries
- 不因项目使用 React 就跳过 `feature-ui`、`api-change`、`bugfix` 等任务层判断
- 不把 React 项目里的局部习惯升级成跨技术栈规则
- 不新增平行的 stack-specific skill，除非该技术栈在多个项目中稳定复用且已有清晰边界
- 若现有项目模式与本 skill 建议冲突，优先遵循项目现有模式并记录原因
