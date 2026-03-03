# 模式：阶段路由（官方命名别名）

将任务信号映射到对应工作流阶段。

> 本文件遵循 AIEF 官方 L1 命名约定。
> 项目完整路由规则见：[docs/standards/patterns/phase-routing.md](phase-routing.md)

## 通用路由逻辑（AIEF 标准）

```
任务信号 → 识别阶段 → 加载对应 workflow/phases/<phase>.md → 执行
```

## 本项目路由表

| 任务信号 | 工作流阶段 | 执行工具 |
|---|---|---|
| 提炼 / 语料 / evidence | evidence-extraction | tools/run_evidence_extraction.py |
| 匹配 / 评分 / JD | matching-scoring | tools/run_matching_scoring.py |
| 生成 / 简历 / 版本 | generation | tools/run_generation.py |
| 评测 / scorecard / 质量 | evaluation | tools/run_evaluation.py |
| 端到端 / pipeline | all | tools/run_pipeline.py |
| 提案 / 为什么 / 动机 | proposal | workflow/phases/proposal.md |
| 设计 / 方案 / 权衡 | design | workflow/phases/design.md |
| 实现 / 开发 / 编码 | implement | workflow/phases/implement.md |
| 审查 / 验收 / 评审 | review | workflow/phases/review.md |
