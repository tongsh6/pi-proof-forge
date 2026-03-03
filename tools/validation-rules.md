# Phase 0 校验规则

## Evidence Card
- 必填字段：id, title, time_range, context, role_scope, actions, results, stack, artifacts, tags
- actions：至少 3 条
- results：至少 1 条
- artifacts：至少 1 条

## Job Profile
- 必填字段：target_role, must_have, keywords, business_domain, seniority_signal, tone
- must_have：至少 3 条
- keywords：至少 5 个

## Matching Report
- 必填字段：job_profile_id, evidence_card_ids, score_total, score_breakdown, top_cards, gaps, gap_tasks, generated_at, version_id
- score_breakdown 必须包含 K/D/S/Q/E/R
- top_cards 至少 3 项

## 命名约定
- evidence_cards: `ec-YYYY-NNN.yaml`
- job_profiles: `jp-YYYY-NNN.yaml`
- jd_inputs: `jd-YYYY-NNN.txt`
- matching_reports: `mr-YYYY-NNN.yaml`
