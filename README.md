# PiProofForge

中文 | [English](#english)

Evidence-first 框架：把碎片化工作语料转为结构化证据，再进行 JD 匹配与事实保真简历生成。

## 项目价值

大多数简历工具假设你的经验已经是结构化文本。现实里常见的是周报、复盘、PR、截图、故障记录等离散材料。

PiProofForge 补的是前半段关键链路：

1. 从原始语料提炼证据（Evidence Cards）
2. 用目标岗位画像做可解释匹配
3. 基于证据生成针对性简历草稿
4. 评测质量并产出补证据任务

## 核心流程

```text
Job discovery (optional) -> Raw materials -> Evidence cards -> Matching report -> Resume generation -> Evaluation
```

## 架构状态

- 当前规范目标：统一核心引擎 v2
- 架构方向：`domain/` + `infra/` + `engines/` + `orchestration/` + `config/` + `channels/` + `cli/`
- GUI 终版路线：`Tauri desktop app + React/TypeScript frontend + Python sidecar`
- 设计原则：高内聚、低耦合、组合优于继承、扩展优于修改、evidence-first
- 迁移策略：旧 CLI 保持兼容，逐步迁移到底层 v2 架构

关键文档：

- `openspec/specs/pi-proof-forge-core.md`
- `openspec/changes/autonomous-agent-delivery-loop/design.md`
- `AIEF/docs/plans/autonomous-agent-delivery-loop-v2.md`

流程文档：

- `AIEF/workflow/phases/evidence-extraction.md`
- `AIEF/workflow/phases/matching-scoring.md`
- `AIEF/workflow/phases/generation.md`
- `AIEF/workflow/phases/evaluation.md`
- `AIEF/workflow/phases/job-discovery.md`（多源职位发现）
- `AIEF/workflow/phases/submission.md`（自动投递阶段：规划中）

GUI 关键文档：

- `ui/design/DESIGN.md`
- `ui/design/piproofforge.pen`
- `AIEF/context/tech/GUI_ARCHITECTURE.md`

## GUI 当前状态

- GUI 产品规范已定版，采用桌面应用路线：Tauri + React/TypeScript + Python sidecar
- 当前 GUI 真源为 `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen`
- 当前 GUI 信息架构为 9 页：Overview、Resumes、Evidence、Jobs、Quick Run、Agent Run、Submissions、Policy、System Settings
- 当前仓库尚未提交正式的桌面端实现代码；后续实现、验收与拆解均以终版设计文档为准

## 快速开始

### 环境要求

- Python 3.10+（或兼容 Python 3 运行时）

### 一键跑通样例

```bash
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml
```

### 分阶段执行

```bash
# 证据提炼
python3 tools/run_evidence_extraction.py --input tools/sample_raw.txt --output evidence_cards/ec-2026-010.yaml

# 匹配评分
python3 tools/run_matching_scoring.py --job-profile job_profiles/jp-2026-001.yaml --evidence-dir evidence_cards --output matching_reports/mr-2026-002.yaml

# 简历生成
python3 tools/run_generation.py --matching-report matching_reports/mr-2026-002.yaml --output-dir outputs

# 质量评测
python3 tools/run_evaluation.py --input outputs/resume_mr-2026-002_A.md --output outputs/scorecards/scorecard_mr-2026-002_A.md --job-profile job_profiles/jp-2026-001.yaml
```

更多命令示例：`tools/README.md`

### AIEF 单目录模式（--base-dir）

如果需要把 AIEF 资产直接生成到独立目录（例如 `AIEF/`）：

```bash
npx --yes @tongsh6/aief-init@latest retrofit --level L1 --base-dir AIEF
```

会生成：`AIEF/context/`、`AIEF/workflow/`、`AIEF/docs/standards/`、`AIEF/templates/`、`AIEF/scripts/`

## 目录结构

```text
AIEF/context/       项目知识库与技术文档
AIEF/workflow/      阶段流程定义
AIEF/docs/standards/标准与模式
AIEF/docs/plans/         实现前计划与设计拆分
evidence_cards/     结构化证据资产
job_profiles/       岗位画像
jd_inputs/          JD 原文输入
matching_reports/   匹配报告
profiles/           求职者档案
release-notes/      发版记录
tools/              CLI 工具
ui/design/          GUI 设计主线（Pencil 设计资产 + 设计文档）
```

## v2 目标代码结构

```text
tools/
  domain/           领域核心（零外部依赖）
  infra/            基础设施唯一实现层
  engines/          提炼/匹配/生成/评测/发现引擎
  orchestration/    Stage 组合编排与 Agent Loop
  config/           配置切片与 Composer 组装
  errors/           不可恢复异常与错误路由
  channels/         投递通道
  cli/              薄入口层
```

## 当前状态

- AIEF Level: L3
- extraction/matching/generation/evaluation 已可端到端运行
- job-discovery 多源职位发现流程已定义，自动化采集实现中
- submission 自动投递已完成流程设计，代码实现进行中
- GUI 终版规范已冻结，桌面端实现待按终版文档落地

## 约定

- 项目入口：`AIEF/AGENTS.md`
- 上下文入口：`AIEF/context/INDEX.md`
- 标准索引：`AIEF/docs/standards/INDEX.md`
- 命名规范：`AIEF/docs/standards/naming.md`

## 注意

- `outputs/` 默认被 git 忽略（生成产物）
- `.env*` 默认被 git 忽略（避免敏感信息误提交）

## License

MIT，详见 `LICENSE`。

---

## English

PiProofForge is an evidence-first framework that turns raw work materials into structured evidence, then performs JD matching and fact-preserving resume generation.

### Why It Exists

Most resume tools assume your experience is already structured. In practice, people have scattered artifacts: weekly reports, PR notes, incidents, docs, and screenshots.

PiProofForge focuses on the missing front-half:

1. Extract evidence from raw materials
2. Match evidence against target job profiles
3. Generate targeted resume drafts with factual constraints
4. Evaluate output quality and produce gap-filling tasks

### Core Workflow

```text
Job discovery (optional) -> Raw materials -> Evidence cards -> Matching report -> Resume generation -> Evaluation
```

### Architecture Status

- Current target spec: Unified Core Engine v2
- Architecture direction: `domain/` + `infra/` + `engines/` + `orchestration/` + `config/` + `channels/` + `cli/`
- Final GUI path: `Tauri desktop app + React/TypeScript frontend + Python sidecar`
- Design principles: high cohesion, low coupling, composition over inheritance, extension over modification, evidence-first
- Migration strategy: keep legacy CLI compatible while moving the core to v2

Key docs:

- `openspec/specs/pi-proof-forge-core.md`
- `openspec/changes/autonomous-agent-delivery-loop/design.md`
- `AIEF/docs/plans/autonomous-agent-delivery-loop-v2.md`

Workflow docs:

- `AIEF/workflow/phases/evidence-extraction.md`
- `AIEF/workflow/phases/matching-scoring.md`
- `AIEF/workflow/phases/generation.md`
- `AIEF/workflow/phases/evaluation.md`
- `AIEF/workflow/phases/job-discovery.md` (multi-source job discovery)
- `AIEF/workflow/phases/submission.md` (submission automation design, implementation in progress)

GUI key docs:

- `ui/design/DESIGN.md`
- `ui/design/piproofforge.pen`
- `AIEF/context/tech/GUI_ARCHITECTURE.md`

### GUI Status

- The GUI product spec is finalized as a desktop application: Tauri + React/TypeScript + Python sidecar
- The GUI source of truth is `ui/design/DESIGN.md` plus `ui/design/piproofforge.pen`
- The GUI information architecture now contains 9 pages: Overview, Resumes, Evidence, Jobs, Quick Run, Agent Run, Submissions, Policy, and System Settings
- The formal desktop implementation is not yet committed; future implementation and acceptance should follow the finalized GUI docs

### Quick Start

Requirements:

- Python 3.10+ (or compatible Python 3 runtime)

Run the full sample pipeline:

```bash
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml
```

For phase-by-phase commands, see `tools/README.md`.

### AIEF Single-Directory Mode (`--base-dir`)

To generate AIEF assets directly under a dedicated base folder (for example `AIEF/`):

```bash
npx --yes @tongsh6/aief-init@latest retrofit --level L1 --base-dir AIEF
```

Generated paths: `AIEF/context/`, `AIEF/workflow/`, `AIEF/docs/standards/`, `AIEF/templates/`, `AIEF/scripts/`.

### Repository Layout

```text
AIEF/context/       Knowledge base and technical docs
AIEF/workflow/      Phase workflows
AIEF/docs/standards/ Standards and patterns
AIEF/docs/plans/         Pre-implementation plans
evidence_cards/     Structured evidence assets
job_profiles/       Target role profiles
jd_inputs/          Raw JD inputs
matching_reports/   Match/scoring outputs
profiles/           Candidate profiles
release-notes/      Release notes
tools/              CLI scripts
ui/design/          GUI design mainline (Pencil design assets + design docs)
```

### Status

- AIEF level: L3
- End-to-end extraction/matching/generation/evaluation is runnable
- Job discovery workflow is defined; automation implementation is in progress
- Submission automation is documented and planned for implementation
- The final GUI specification is frozen; desktop implementation remains to be built against the final docs

### License

MIT. See `LICENSE`.
