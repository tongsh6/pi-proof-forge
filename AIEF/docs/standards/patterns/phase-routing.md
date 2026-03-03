# 自动阶段路由

## 目标
根据任务类型自动进入对应 workflow phase，减少手工判断成本。

## 路由规则
- 输入含“提炼/语料/evidence” -> `workflow/phases/evidence-extraction.md`
- 输入含“匹配/评分/JD” -> `workflow/phases/matching-scoring.md`
- 输入含“生成/简历/版本 A/B” -> `workflow/phases/generation.md`
- 输入含“评测/scorecard/质量” -> `workflow/phases/evaluation.md`

## 执行映射
- evidence-extraction -> `tools/run_evidence_extraction.py`
- matching-scoring -> `tools/run_matching_scoring.py`
- generation -> `tools/run_generation.py`
- evaluation -> `tools/run_evaluation.py`
- end-to-end -> `tools/run_pipeline.py`
