# Proposal: autonomous-agent-delivery-loop

## Problem
当前系统具备 extraction/matching/generation/evaluation/submission 的阶段能力，但仍是手动串行触发，缺少统一的 Agent 编排能力：

1. 无统一策略入口：投递次数、循环次数、目标方向未集中管理。
2. 无闭环循环：评测失败后无法自动回流并重试至通过。
3. 无多通道统一投递：现有仅有 Liepin 通道，没有邮件投递抽象。
4. 无一次触发自动执行：无法按规则自动从线索到投递完成全链路。

## Goals
1. 提供一个单入口触发的 Autonomous Agent（一次触发，自动执行多轮）。
2. 用 policy 配置驱动关键规则：`delivery_count`、`loop_count`、`target_direction`。
3. 建立 N-pass 质量门禁：matching + evaluation + channel readiness 联合判定。
4. 支持至少两种投递通道：招聘平台（Liepin）和 Email。
5. 自动从已有资料中推导可投递方向/公司/JD（在 `job_leads` 缺失时仍可工作）。
6. 输出可追溯运行日志，记录每轮决策、得分、投递结果。

## Non-Goals
1. 大规模爬虫与反爬绕过（本阶段不做，后续可按触发条件进入范围）。
2. 外部调度系统（Airflow/Celery 等）（本阶段不做，后续按运行规模触发）。
3. 重写现有 matching/generation/evaluation 算法（本变更不做）。

## Non-Goals Rationale and Triggers
| Item | 当前判定 | 为什么现在不做 | 进入范围触发条件 |
| --- | --- | --- | --- |
| 大规模爬虫与反爬绕过 | later with trigger | 当前优先验证 Agent 闭环与投递质量，不把风险集中在采集对抗 | 连续 2 周 `job_leads + 手工导入` 覆盖率 < 60%，且方向池不足以满足 `max_deliveries` |
| 外部调度系统（Airflow/Celery） | currently out-of-scope | V1 目标是“单次触发可自动闭环”，不需要额外运维复杂度 | 需要跨时区定时运行，且并发 agent runs > 3，或单日触发 > 20 次 |
| 重写 matching/generation/evaluation 算法 | never in this change | 本变更目标是编排层升级，重写算法会导致范围失控并延后交付 | 不适用（需另起独立 OpenSpec change） |

## Scope
- 新增 Agent 编排层，迁移并吸收现有 legacy CLI 脚本能力（以下脚本为当前资产来源，不代表目标架构仍以脚本串联为主）：
  - `tools/run_pipeline.py`
  - `tools/run_matching_scoring.py`
  - `tools/run_generation.py`
  - `tools/run_evaluation.py`
  - `tools/submission/run_submission.py`
  - `tools/check_submission_readiness.py`
- 新增 policy 配置文件与运行日志结构。
- 新增 Email 通道最小可用实现。
- 新增从已有资料推导方向/公司/JD 的 discovery 回退路径（`evidence_cards`、`jd_inputs`、`job_profiles`）。

## Expected Outcomes
1. 用户可通过单条命令触发 Agent 执行全流程。
2. 质量门禁未通过时自动进入下一轮，直到达到 `n_pass_required` 或 `max_rounds`。
3. 在预算范围内自动选择候选方向/公司/JD 并执行投递（优先 `job_leads`，缺失时自动从已有资料推导）。
4. Email 与招聘渠道至少一个通道可实际投递成功。
5. 产出完整 run log，支持复盘和后续优化。
