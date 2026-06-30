# Agent OS VSCode 插件

让 Agent OS 以工作区能力的方式直接运行在 VSCode 里。

它可以把 Agent OS 注入当前项目，提供状态查看、总览入口和安装管理，帮助用户在编辑器中快速确认 Agent OS 是否正常工作。

## 它做什么

- 把 Agent OS 安装到当前工作区
- 让用户在 VSCode 中查看运行状态、健康状态和总览
- 配置 LLM Semantic Compiler，用于把用户请求编译成 Mission IR
- 将项目约束、计划、执行结果和运行记录保持在统一的 Agent OS 结构里

## 边界

- 插件负责注入、查看和管理
- 插件不替代核心 Agent OS 源码
- 插件不承担聊天运行时
- 插件配置的 LLM 只负责语义编译，不拥有最终写入、提交或部署权限
- 插件不负责把业务逻辑散落到工作区之外

## LLM 意图编译器

Agent OS 默认使用本地规则算法识别意图。用户也可以在插件中配置 OpenAI-compatible LLM：

- `apiKey`：保存到 VSCode SecretStorage，不写入项目文件
- `baseUrl`：例如 `https://api.openai.com/v1`
- `model`：用于 Mission IR 编译的模型
- `provider`：用于状态展示和运行记录

启用后链路是：

```text
User Request
  -> LLM Semantic Compiler
  -> Draft Mission IR
  -> Agent OS Validator / Normalizer / Optimizer
  -> Locked Mission IR
  -> Execution Gate
```

LLM 调用失败、超时、返回非 JSON、字段不合规或权限越界时，Agent OS 会回退到本地规则算法。

插件中的“测试意图编译器”会调用工作区内 `.agent-os/scripts/agent-runtime.py runtime-compile-mission`，因此测试结果与核心 Runtime 实际消费的 Locked Mission IR 保持一致。

## Memory

- Agent OS 会根据工作区状态和运行记录维护记忆
- 记忆用于保留项目约束、稳定偏好、已验证决策和可复用经验
- 插件只负责展示和操作入口，不单独承担记忆系统本身

## 核心价值

- 把 Agent OS 变成可直接使用的工作区能力
- 让用户在当前编辑器里完成注入、查看和管理
- 把运行状态、健康状态和总览入口集中到一个插件里

## 主要能力

- 注入当前工作区
- 查看安装状态和健康状态
- 打开合并后的总览页
- 配置和测试意图编译器
- 只负责查看和管理，不承担聊天运行时职责

## 命令

- `Agent OS: 注入当前工作区`
- `Agent OS: 刷新状态`
- `Agent OS: 打开总览`
- `Agent OS: 配置意图编译器`
- `Agent OS: 测试意图编译器`

## 说明

- 插件从当前工作区的 `.agent-os/` 目录读取 Agent OS 状态。
- 用户项目的执行文档仍然放在 `docs/agent-os/`。
- 插件不会替代核心 Agent OS 运行时。
