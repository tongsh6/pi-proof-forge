# 架构概览

## 目标
- 从证据到输出的流程可复现、可追溯。
- 可解释匹配与评分。
- 事实保真生成与来源可追踪。
- 模块化设计，便于开源扩展。

## MVP 不做
- 端到端自动填表。
- 复杂 UI 平台（仅做轻量 GUI 工作台）。
- 多 Agent 辩论。

## 系统组件
- Evidence Extraction
  - 输入：原始材料
  - 输出：验证后的 evidence cards
- Indexing & Retrieval
  - 关键词/标签检索（可选 BM25）
  - 可选 embeddings/rerank
- Matching Engine
  - 评分维度：K/D/S/Q/E/R
  - 输出：match report + gap tasks
- Document Assembly
  - 模板优先拼装
  - 受控改写（不新增事实）
- Evaluation
  - Scorecard 指标
  - 缺口任务生成
- Tracking（可选）
  - 版本化输出与结果
- GUI Workspace
  - 输入：raw materials + job profile
  - 输出：pipeline 执行状态 + 结果预览

## 数据流（高层）
1. Raw materials → evidence extraction → evidence cards
2. JD input → job profile
3. Evidence cards + job profile → matching report
4. Selected cards → template assembly → controlled rewrite → output document
5. Output → scorecard → evidence gap tasks
6. GUI 工作台读取与展示 pipeline 产物

## 数据存储（MVP）
- Evidence cards：YAML/Markdown + Git 版本管理
- Inputs/outputs：版本化文件
- Tracking：CSV/SQLite

## 可插拔接口
- LLM provider
- Embedding provider
- Exporter（PDF/DOCX）
- GUI adapter（CLI pipeline 调用层）

## 未决问题
- Fact-attribution 的约束与校验策略
- 受控改写的 diff 校验方法
- 最小可用 exporter 选型
