# PiProofForge 核心 Pipeline 规范

**状态**: active  
**版本**: v1.0  
**创建日期**: 2026-03-02  
**所有者**: pi-proof-forge team

---

## 概述

PiProofForge 是一个 evidence-first 框架，将原始工作材料（日志、PR、报告、截图等）转为结构化证据（Evidence Cards），再通过可解释匹配生成事实保真的目标文档（简历等）。

---

## 核心实体规范

### Evidence Card

```yaml
schema: evidence_card_v1
required_fields:
  - id          # 唯一标识，格式：ec-YYYY-MM-DD-NNN
  - title       # 简短描述
  - raw_source  # 原始材料路径或引用
  - results     # 可量化的成果（必填，否则不进入候选池）
  - artifacts   # 关联产出物（必填，否则不进入候选池）
optional_fields:
  - tags        # 技能标签
  - period      # 时间范围
  - context     # 背景说明
```

**约束**：`results` 或 `artifacts` 任意一项缺失，该 Evidence Card 不进入匹配候选池。

### Job Profile

```yaml
schema: job_profile_v1
required_fields:
  - id          # 格式：jp-YYYY-NNN
  - title       # 岗位名称
  - keywords    # 关键词列表
  - level       # 级别信号（junior/mid/senior/staff）
optional_fields:
  - tone        # 语气偏好
  - must_have   # 硬性要求
  - nice_to_have # 加分项
```

### Matching Report

```yaml
schema: matching_report_v1
required_fields:
  - job_profile_id    # 关联岗位
  - evidence_cards    # 入选证据卡列表（含分项得分）
  - gap_tasks         # 缺口任务列表
  - score_breakdown   # 各维度得分（必须可解释）
```

---

## Pipeline 阶段规范

### 阶段 1：证据提炼（Evidence Extraction）

**输入**: 原始材料文件（txt/md/pdf）  
**输出**: Evidence Cards（YAML 格式）  
**工具**: `tools/extract_evidence.py`  
**约束**:
- 不得推断或补充原材料中没有的信息
- 每个 Evidence Card 必须有明确的 `raw_source` 引用

### 阶段 2：匹配评分（Matching & Scoring）

**输入**: Evidence Cards + Job Profile  
**输出**: Matching Report  
**工具**: pipeline 内部逻辑  
**约束**:
- 所有评分维度必须有对应证据支撑
- 缺口任务必须明确列出（不得静默忽略）

### 阶段 3：文档生成（Generation）

**输入**: Matching Report + 选定的 Evidence Cards  
**输出**: 目标文档（markdown/pdf）  
**约束**:
- 严禁生成无证据支撑的内容
- 语气调整不改变事实

### 阶段 4：质量评估（Evaluation）

**输入**: 生成文档 + 原始证据  
**输出**: 质量评分报告  
**约束**:
- 每项质量分必须可追溯到具体检查点

---

## CLI 接口规范

```bash
# 证据提炼
python3 tools/extract_evidence.py --input <raw_file>

# 完整 pipeline
python3 tools/run_pipeline.py \
  --raw tools/sample_raw.txt \
  --job-profile job_profiles/jp-2026-001.yaml
```

---

## 变更流程

1. 使用 `/opsx:propose` 提交变更提案
2. 通过 brainstorming skill 细化设计
3. 通过 writing-plans skill 生成实现计划
4. TDD 实现（test-driven-development skill）
5. code review（requesting-code-review skill）
6. 使用 `/opsx:archive` 归档已实施变更

---

## 参考文档

- 业务域：`context/business/DOMAIN.md`
- 架构：`context/tech/ARCHITECTURE.md`
- Evidence Card Schema：`context/tech/SCHEMA_EVIDENCE_CARD.md`
- Job Profile Schema：`context/tech/SCHEMA_JOB_PROFILE.md`
- 生成规范：`context/tech/GENERATION.md`
- 评估规范：`context/tech/EVALUATION.md`
