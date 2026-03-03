# 质量评测（Evaluation）

## 目标
- 输出可执行的质量评测与改进建议。
- 发现缺口并生成补证据任务。

## 指标（Scorecard）
- must-have 关键词覆盖率
- 量化占比（含数字 bullets 比例）
- 空话率/重复度（泛词、同义重复、无主语无结果）
- 篇幅控制（1 页；段落长度阈值）
- 证据引用检查（关键表达是否可追溯到 artifacts）

## 输出
- Scorecard（总分 + 分项）
- 改进建议（按优先级）
- 补证据任务队列（可自动生成）

## 规则约束
- 所有指标必须可解释与可复现。
- 缺口建议必须指向具体 evidence card 字段或新卡需求。

## LLM 辅助模式
- CLI：`tools/run_evaluation.py --use-llm`
- Prompt：`tools/prompts/evaluation.md`
- 严格模式：`--use-llm --require-llm`（LLM 不可用即失败）

## 当前实现状态
- 默认使用规则计分（可复现）：覆盖率、量化占比、空话/重复、篇幅、证据引用。
- `--use-llm` 打开时仅追加解释层，不覆盖规则分数。
