# Taro / Miniapp Rules

## Structure
- 页面逻辑与云函数调用分开
- 数据流尽量单向
- 下拉刷新、上拉加载、分页状态明确隔离

## Cloud
- 云函数输入输出结构明确
- 数据库写入前先校验字段
- 分页接口要明确 page / pageSize / cursor 策略

## UI Logic
- 避免把大量状态直接塞进页面文件
- 公共逻辑优先抽 hook / util / service
