# Reusable Patterns

## Template
- Name:
- Trigger:
- Pattern:
- Why:
- Caution:

---

## Example
- Name: Stable Query Key
- Trigger: React Query 列表/详情查询
- Pattern: 把业务唯一标识纳入 query key
- Why: 防止旧缓存串数据
- Caution: 不要把不稳定对象直接放进 key
