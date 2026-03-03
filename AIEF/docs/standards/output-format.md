# 提炼输出规范

## 格式
- evidence extraction 输出必须是 YAML
- 顶层包含 `evidence_card` 与 `gaps`

## 字段约束
- `evidence_card.results` 与 `evidence_card.artifacts` 允许为空，但必须显式给出
- `gaps` 必须是数组

## 示例
```yaml
evidence_card:
  id: "ec-2026-010"
  title: "示例"
  time_range: "2026-01"
  context: ""
  role_scope: "执行"
  actions: []
  results: []
  stack: []
  artifacts: []
  tags: []
  interview_hooks: []
gaps:
  - "缺少量化结果"
```
