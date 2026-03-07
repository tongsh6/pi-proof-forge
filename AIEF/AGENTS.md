# PiProofForge AI 指南

这是 AI 辅助工程的项目级入口。

语言：
- 默认使用中文交流
- 代码/命令/标识符保留英文

项目：
- 一句话介绍：Evidence-first 框架，将原始工作材料转为结构化证据并生成事实保真的目标文档。
- 核心价值：不假设知识已结构化；强调证据提炼、可解释匹配与事实保真生成。

## AIEF 状态
- 当前级别：L3（持续运行）
- 入口文件：AGENTS.md, context/INDEX.md
- 仓库快照：context/tech/REPO_SNAPSHOT.md
- 工作流索引：workflow/INDEX.md
- 标准索引：docs/standards/INDEX.md
- 经验索引：context/experience/INDEX.md

快速命令：
- build: n/a（暂未设置）
- test: n/a（暂未设置）
- run: python3 tools/run_evidence_extraction.py --input <file>
- pipeline: python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml

上下文入口：
- context/INDEX.md

说明：
- `tools/run_evidence_extraction.py` 是推荐工作流入口；`tools/extract_evidence.py` 仍保留为底层规则实现/兼容脚本。

知识库：

| 目录 | 用途 | 何时加载 |
|-----------|---------|-------------|
| context/business/ | 业务知识 | 理解需求与领域模型 |
| context/tech/ | 技术文档 | 架构、API、约定 |
| context/experience/ | 经验库 | 避免重复踩坑 |
| workflow/ | 工作流 | 复杂任务阶段指南（可选） |
| docs/standards/ | 标准 | Skill/Command/Agent 规范（L1，可选） |
| docs/standards/patterns/ | 模式 | 阶段路由、经验管理、上下文加载（L2，可选） |

## 自动行为

### 任务识别与路由
- 提炼任务 -> workflow/phases/evidence-extraction.md
- 匹配任务 -> workflow/phases/matching-scoring.md
- 生成任务 -> workflow/phases/generation.md
- 评测任务 -> workflow/phases/evaluation.md

### 上下文自动加载
- 基础入口：AGENTS.md -> context/INDEX.md
- 按任务加载：对应 phase + 对应 tech 文档
- 实现类任务默认加载：context/experience/INDEX.md

### 经验沉淀（L3）
- 每个重要变更至少新增一条 lessons 记录
- 高频主题同步更新 summaries

## 工具链集成

### 三工具架构

| 工具 | 职责 | 入口 |
|------|------|------|
| OpenSpec | 规范驱动开发（先写 spec，再实现） | `openspec/specs/` |
| superpowers | AI 执行质量（brainstorm→plan→TDD→review） | `.opencode/skills/` |
| spec-kit | 项目原则守护（不可妥协的工程约定） | `constitution.md` |

### 任务路由（三工具版）

- 新功能提案 → `/opsx:propose "你的想法"` → brainstorming skill
- 设计阶段 → brainstorming skill → writing-plans skill → `docs/plans/`
- 实现阶段 → test-driven-development skill（强制 TDD）
- 审查阶段 → requesting-code-review skill
- 规范变更归档 → `/opsx:archive`

### 原则守护（constitution.md）

以下行为触发宪法违规，立即停止：
- 代码先于 spec 被提议
- Evidence Card 无 results/artifacts 进入生成
- 测试在实现之后补写

### 快速参考

- OpenSpec 规范目录：`openspec/specs/`
- 变更目录：`openspec/changes/`
- 实现计划目录：`docs/plans/`
- 项目宪法：`constitution.md`
- spec-kit 配置：`.specify/config.yaml`
