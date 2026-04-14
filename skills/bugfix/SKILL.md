---
name: bugfix
description: 用于定位和修复报错、异常行为、边界条件失败、状态不一致等问题。
---

# When to Use
当任务包含以下特征时使用：
- 有报错日志
- 有复现路径
- 行为与预期不一致
- 某功能之前正常、现在异常
- 状态或界面不同步

# Steps
1. 明确现象
2. 明确输入 / 操作 / 预期 / 实际结果
3. 找到触发入口
4. 定位根因
5. 先说明根因，再做最小修改
6. 验证主路径
7. 验证相关边界
8. 记录到 memory

# Output
- 症状
- 根因
- 修改点
- 风险范围
- 验证建议

# Memory Usage
- 项目专属问题 -> memory/projects/{project}.md
- 通用问题模式 -> memory/global/reusable-patterns.md
