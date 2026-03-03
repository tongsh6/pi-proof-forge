# 证据提炼 Prompt

## System
从原始语料中提炼结构化 evidence card。禁止编造事实。
若 results 或 artifacts 缺失，输出 gaps 清单，不要捏造。

## Input
<RAW_MATERIAL>

## Output (YAML)
```yaml
evidence_card:
  id: ""
  title: ""
  time_range: ""
  context: ""
  role_scope: ""
  actions: []
  results: []
  stack: []
  artifacts: []
  tags: []
  interview_hooks: []
gaps:
  - ""
```

## Rules
- 只使用原始语料中出现的事实。
- results 或 artifacts 缺失时保持为空，并写入 gaps。
- actions 需 3-5 条。
