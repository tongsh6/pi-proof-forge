# 工作流索引

## 目标
为 PiProofForge 的核心任务提供标准化执行路径。

## 工作流
- 证据提炼：workflow/phases/evidence-extraction.md
- 匹配评分：workflow/phases/matching-scoring.md
- 简历生成：workflow/phases/generation.md
- 质量评测：workflow/phases/evaluation.md
- 自动投递：workflow/phases/submission.md

## 通用变更工作流（AIEF L1 标准阶段）
- 提案阶段：workflow/phases/proposal.md
- 设计阶段：workflow/phases/design.md
- 实现阶段：workflow/phases/implement.md
- 审查阶段：workflow/phases/review.md

## 执行脚本映射
- 证据提炼：tools/run_evidence_extraction.py
- 匹配评分：tools/run_matching_scoring.py
- 简历生成：tools/run_generation.py
- 质量评测：tools/run_evaluation.py
- 自动投递（规划）：tools/submission/run_submission.py
- 一键流水线：tools/run_pipeline.py

## 使用方式
当任务涉及新功能/修复/重构时，先选择对应流程，再执行。
