# 自动阶段路由

## 目标
根据任务类型自动进入对应 workflow phase，减少手工判断成本。

## 路由规则
- 输入含“提炼/语料/evidence” -> `workflow/phases/evidence-extraction.md`
- 输入含“匹配/评分/JD” -> `workflow/phases/matching-scoring.md`
- 输入含“生成/简历/版本 A/B” -> `workflow/phases/generation.md`
- 输入含“评测/scorecard/质量” -> `workflow/phases/evaluation.md`

## 执行映射
- evidence-extraction -> `python3 -m tools.cli.entrypoints extract`
- matching-scoring -> `python3 -m tools.cli.entrypoints match`
- generation -> `python3 -m tools.cli.entrypoints generate`
- evaluation -> `python3 -m tools.cli.entrypoints evaluate`
- end-to-end -> `python3 -m tools.cli.entrypoints pipeline`
