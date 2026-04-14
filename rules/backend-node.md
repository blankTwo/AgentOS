# Backend Node Rules

## API
- 输入校验前置
- 错误返回统一格式
- 不把内部异常直接暴露给调用方
- controller / service / repository 尽量分层

## Data
- 数据库操作明确边界
- 修改型操作优先考虑事务
- schema / model 变化必须评估兼容性

## Reliability
- 日志要能支持定位
- 避免 silent failure
- 外部依赖要有失败分支处理
