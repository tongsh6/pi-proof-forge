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
Raw materials -> Evidence cards -> Matching report -> Resume generation -> Evaluation
```

流程文档：

- `workflow/phases/evidence-extraction.md`
- `workflow/phases/matching-scoring.md`
- `workflow/phases/generation.md`
- `workflow/phases/evaluation.md`
- `workflow/phases/submission.md`（自动投递阶段：规划中）

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

## 目录结构

```text
context/            项目知识库与技术文档
workflow/           阶段流程定义
docs/standards/     标准与模式
evidence_cards/     结构化证据资产
job_profiles/       岗位画像
jd_inputs/          JD 原文输入
matching_reports/   匹配报告
tools/              CLI 工具
ui/prototype/       GUI 原型
```

## 当前状态

- AIEF Level: L3
- extraction/matching/generation/evaluation 已可端到端运行
- submission 自动投递已完成流程设计，代码实现进行中

## 约定

- 项目入口：`AGENTS.md`
- 上下文入口：`context/INDEX.md`
- 标准索引：`docs/standards/INDEX.md`
- 命名规范：`docs/standards/naming.md`

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
Raw materials -> Evidence cards -> Matching report -> Resume generation -> Evaluation
```

Workflow docs:

- `workflow/phases/evidence-extraction.md`
- `workflow/phases/matching-scoring.md`
- `workflow/phases/generation.md`
- `workflow/phases/evaluation.md`
- `workflow/phases/submission.md` (submission automation design, implementation in progress)

### Quick Start

Requirements:

- Python 3.10+ (or compatible Python 3 runtime)

Run the full sample pipeline:

```bash
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml
```

For phase-by-phase commands, see `tools/README.md`.

### Repository Layout

```text
context/            Knowledge base and technical docs
workflow/           Phase workflows
docs/standards/     Standards and patterns
evidence_cards/     Structured evidence assets
job_profiles/       Target role profiles
jd_inputs/          Raw JD inputs
matching_reports/   Match/scoring outputs
tools/              CLI scripts
ui/prototype/       GUI prototype
```

### Status

- AIEF level: L3
- End-to-end extraction/matching/generation/evaluation is runnable
- Submission automation is documented and planned for implementation

### License

MIT. See `LICENSE`.
