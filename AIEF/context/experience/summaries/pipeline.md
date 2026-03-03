# Pipeline 经验摘要

## 适用场景
- 需要一键跑通提炼→匹配→生成→评测。

## 关键结论
- 统一 run-id 可显著降低产物追踪成本。
- 先保证 fallback 可跑，再接入 LLM 模式。
- 流程脚本必须输出阶段日志，便于定位失败点。

## 关联经验
- context/experience/lessons/2026-02-28-pipeline-e2e.md
