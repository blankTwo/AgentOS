# Frontend React Rules

## Component Design
- 组件尽量单一职责
- 页面负责组织，业务逻辑尽量下沉
- 复杂逻辑优先抽 hooks / service / store

## State
- 本地状态与全局状态分清
- 全局状态集中管理
- 避免组件间隐式耦合
- query 状态与 UI 状态不要混淆

## Data Fetching
- 请求层统一封装
- query key 要稳定
- 参数变化必须体现在缓存标识中
- 错误态、空态、加载态明确处理

## UI
- 先保证逻辑正确，再优化表现
- 避免把大量条件判断直接堆在 JSX
- 复杂渲染拆成子组件或纯函数
