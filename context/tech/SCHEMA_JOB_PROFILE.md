# Job Profile Schema（岗位画像）

## 目标
- 统一 JD 解析后的结构化输入。
- 支持匹配评分与生成方向控制。

## 字段（MVP）
- `target_role`
- `must_have`
- `nice_to_have`
- `keywords`（ATS/JD 关键词）
- `business_domain`
- `seniority_signal`（Owner/决策/带人/跨团队推进）
- `tone`（偏架构/偏交付）

## 约束规则
- `target_role` 必填
- `keywords` 至少 5 个
- `must_have` 不少于 3 条

## 示例（YAML）
```yaml
target_role: "Backend Tech Lead"
must_have:
  - "高并发系统设计"
  - "稳定性治理"
  - "跨团队协作"
nice_to_have:
  - "数据治理"
  - "成本优化"
keywords:
  - "Java"
  - "Redis"
  - "Kafka"
  - "SLA"
  - "SLO"
business_domain: "电商"
seniority_signal:
  - "Owner"
  - "跨团队推进"
tone: "偏架构"
```
