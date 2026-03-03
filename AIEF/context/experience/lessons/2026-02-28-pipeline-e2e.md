# 2026-02-28 一键流水线端到端经验

## 背景
需要将提炼、匹配、生成、评测四个阶段串成单命令执行。

## 问题
分阶段脚本可运行，但手动串联成本高，且运行参数不一致容易出错。

## 根因
缺少统一 run-id 与统一输出目录约定。

## 解决方案
1. 新增 `tools/run_pipeline.py`，统一串联四阶段。
2. 统一命名：`ec-<run_id>` / `mr-<run_id>` / `outputs/<run_id>/`。
3. 支持 `--use-llm`，无 key 时自动回退到规则/占位输出。

## 验证
1. 执行 `python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml`。
2. 检查 evidence/matching/resume/scorecard 四类产物均生成。

## 可复用结论
复杂流程先统一输入输出约定，再做阶段串联，稳定性明显更高。
