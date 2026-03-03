# JP 配置需与 Engine 评分逻辑对齐

**日期**：2026-03-02
**场景**：为得物 App Java 技术专家 JD 创建 jp-2026-002.yaml，首次运行匹配得分 59/100（D=0, S=0），修正后 84/100

## 问题

`run_matching_scoring.py` 的评分 engine 内置了硬编码逻辑：

1. **D（业务域）评分**：`domain_signals_map` 只有 `"电商"`/`"零售"`/`"金融"` 三个 key。如果 `business_domain` 填 `"消费电商"` 找不到 key，会 fallback 到 `[business_domain]` 自身去匹配——"消费电商"四个字同时出现在 EC 文本中的概率极低，导致 D=0

2. **S（职级信号）评分**：只识别四个硬编码模式：`owner`、`跨团队`、`带人`、`决策`。如果填 `"独立担当功能模块架构设计"` 等描述性文字，engine 无法匹配，导致 S=0

## 修正

- `business_domain` 必须使用 `domain_signals_map` 里已有的 key：`"电商"` / `"零售"` / `"金融"`
- `seniority_signal` 必须使用 engine 能识别的关键词：`"owner"` / `"跨团队"` / `"带人"` / `"决策"`

## 建议

- 写 JP 文件前先阅读 `tools/run_matching_scoring.py` 第 165-185 行的评分逻辑
- 或将 `domain_signals_map` 和 `seniority_signal` 的匹配规则文档化到 `context/tech/SCHEMA_JOB_PROFILE.md`
- 长期：考虑让 engine 支持自定义 domain/seniority 映射，消除硬编码依赖
