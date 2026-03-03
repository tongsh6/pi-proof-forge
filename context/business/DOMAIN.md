# 业务域概览

## 使命
构建 evidence-first 框架，将原始工作材料转为结构化证据，并生成事实保真的目标文档。

## 核心原则
- Evidence-first：任何输出必须可追溯到 evidence cards。
- 不假设知识已结构化：证据提炼是第一步。
- 可解释匹配：分项得分与缺口清单必须存在。
- 闭环：输出质量反驱证据补全。

## 核心实体
- Raw Materials：日志、PR、报告、截图、文档等原始材料。
- Evidence Card：带 results + artifacts 的结构化可验证单元。
- Job Profile：岗位要求、关键词、级别信号、语气偏好。
- Matching Report：分项得分、入选证据卡、缺口任务。
- Output Document：简历或其他目标文档。
- Tracking Record：带版本与结果的追踪记录。

## 约束
- results 或 artifacts 缺失的 evidence cards 不进入候选池。
- 生成不得引入新事实。
- 所有评分维度必须可解释。

## MVP 不包含
- 全自动投递。
- 重型 UI 平台。
- 复杂多 Agent 辩论工作流。
