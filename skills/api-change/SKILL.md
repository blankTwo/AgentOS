---
name: api-change
description: 用于新增或修改后端接口、请求参数、返回结构、数据处理逻辑。
---

# When to Use
- 新增接口
- 修改接口字段
- 修改数据库写入逻辑
- 调整请求/响应协议

# Steps
1. 明确输入输出
2. 确认兼容性影响
3. 调整 controller / service / repository
4. 明确异常分支
5. 验证调用链
6. 记录协议变化

# Output
- 接口变更点
- 兼容性影响
- 验证建议
