# 提炼输出规范

## 格式
- evidence extraction 输出必须是 YAML
- 顶层包含 `evidence_card` 与 `gaps`

## 字段约束
- `evidence_card.results` 与 `evidence_card.artifacts` 必须显式给出（可为空数组）
- 候选池门控规则：仅当 `results` 与 `artifacts` 均为非空时，证据卡可进入匹配/生成候选池
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
