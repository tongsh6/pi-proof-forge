# Matching Report Schema（匹配报告）

## 目标
- 输出可解释的匹配结果与缺口。
- 支持版本化与回溯。

## 字段（MVP）
- `job_profile_id`
- `evidence_card_ids`
- `score_total`
- `score_breakdown`
- `top_cards`
- `gaps`
- `gap_tasks`
- `generated_at`
- `version_id`

## 字段说明
- `score_breakdown`：K/D/S/Q/E/R 分项得分与解释
- `top_cards`：入选证据卡与理由
- `gaps`：缺关键词/缺能力/缺指标
- `gap_tasks`：补证据任务清单

## 约束规则
- `score_breakdown` 必须包含 K/D/S/Q/E/R
- `top_cards` 至少 3 项
- `version_id` 必填

## 示例（YAML）
```yaml
job_profile_id: "jp-2026-001"
evidence_card_ids:
  - "ec-2026-001"
  - "ec-2026-002"
score_total: 82
score_breakdown:
  K: { score: 18, reason: "关键词覆盖 9/12" }
  D: { score: 12, reason: "电商领域匹配" }
  S: { score: 14, reason: "Owner + 跨团队推进" }
  Q: { score: 16, reason: "3 条量化结果" }
  E: { score: 14, reason: "含复盘 + 监控截图" }
  R: { score: 8, reason: "近 12 个月 2 张卡" }
top_cards:
  - id: "ec-2026-001"
    reason: "稳定性治理 + 量化结果明显"
gaps:
  - "缺少成本优化相关证据"
gap_tasks:
  - "补充成本下降指标或压测报告"
generated_at: "2026-02-27T22:30:00+08:00"
version_id: "mr-2026-001"
```
