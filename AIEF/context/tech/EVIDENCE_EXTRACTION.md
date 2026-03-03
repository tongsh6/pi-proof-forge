# 证据提炼（Evidence Extraction）

## 目标
- 从原始语料中提炼结构化 evidence cards。
- 确保 results/artifacts 不缺失，避免“像但不真”。

## 输入类型
- 周报/复盘/排障记录
- PR 描述/设计文档
- 监控截图/压测报告

## 输出
- Evidence Card（见 schema）
- 缺口清单（缺指标/缺证据/缺上下文）

## 提炼流程（建议）
1. 原始语料清洗：去噪、分段、提取标题与时间
2. 关键信息抽取：场景/约束/动作/结果
3. 证据门控：results 与 artifacts 必填
4. 生成缺口任务：提示用户补证据

## CLI 入口
- 规则版：`tools/extract_evidence.py`
- LLM 版：`tools/extract_evidence_llm.py`

## 规则约束
- 不允许编造指标或 artifacts。
- 所有量化结果需可追溯原文或补证据说明。

## 质量检查
- actions 是否 >= 3 条
- results 是否量化
- artifacts 是否可指向文件/链接
