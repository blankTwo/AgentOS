# .codex Mother System v2

## Purpose
这是一个单母体、多项目复用的 Codex 系统目录。

## Structure
- AGENTS.md: 总控入口
- rules/: 稳定规范
- skills/: 可复用流程
- memory/global/: 通用偏好、模式、进化日志
- memory/projects/: 各项目隔离记忆

## Usage
- 不需要给每个项目单独建 AGENTS.md
- 直接在不同项目中使用同一套母体
- 项目差异主要通过 memory/projects/{project}.md 解决
- 若某类经验重复出现，可升级为 skill
- 若 skill 跨项目稳定复用，可升级为 rule

## Maintenance Advice
- 高频更新 memory
- 低频更新 skills
- 更低频更新 rules
- 几乎不要动 AGENTS.md
