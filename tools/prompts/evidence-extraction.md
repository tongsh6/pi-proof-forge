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

## 字段写作约束（2026-11-08）

- `context` 只写业务背景/约束/目标（读者是招聘方），不要写「此卡」「本卡」「工作汇总」「所属工作」「汇总说明」等内部元描述。
- `time_range` 必须来自材料中的项目起止依据（年月），不得使用材料整理日期、截图日期或单次事件日期代替项目期间。
- `role_scope` 只写本人在该项目中的职责范围，不得升级为团队成果或他人职责。
