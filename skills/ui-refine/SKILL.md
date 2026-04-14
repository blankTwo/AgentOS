---
name: ui-refine
description: 用于统一页面UI风格、替换不规范Tailwind写法、优先复用组件库与已有组件，并提升界面一致性。
---

# Trigger Keywords
- 优化UI
- 美化页面
- 统一样式
- 调整布局
- 改好看一点
- 改成和其他页面一致
- 替换原生标签
- 统一 Tailwind 写法

# When to Use
当任务包含以下目标时使用：
- 页面风格不统一
- 使用了过多原生 HTML 拼装 UI
- Tailwind 写法和项目现有风格不一致
- 用户要求优化界面、统一风格、提升观感
- 需要向组件库风格靠拢

# Steps
1. 先寻找项目中 2~3 个相似页面
2. 提取这些页面的共同模式：
   - 布局结构
   - 组件使用方式
   - Tailwind 命名习惯
   - 字号/间距/圆角/按钮风格
3. 检查当前页面问题：
   - 是否滥用原生标签
   - 是否滥用任意值
   - 是否存在与现有系统不一致的 class
   - 是否缺少 hover / disabled / empty / loading 状态
4. 优先替换为：
   - 项目已有组件
   - 组件库组件
   - 项目统一 Tailwind 写法
5. 保持业务逻辑不变，只优化表现层和结构层
6. 输出：
   - 发现了哪些不一致
   - 做了哪些统一
   - 还有哪些可继续优化

# Output
- 不一致点
- 替换策略
- 统一后的结构说明
- 剩余风险

# Memory Usage
- 若形成项目级 UI 模式，写入 memory/projects/{project}.md
- 若形成跨项目可复用规范，提议升级到 rules/ui-consistency.md