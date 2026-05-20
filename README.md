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

- 当前规范目标：统一核心引擎 v2（组件层已落地，CLI 主链路仍保留 legacy 兼容串联）
- 架构方向：`domain/` + `infra/` + `engines/` + `orchestration/` + `config/` + `channels/` + `cli/`
- GUI 终版路线：`Tauri desktop app + React/TypeScript frontend + Python sidecar`
- 设计原则：高内聚、低耦合、组合优于继承、扩展优于修改、evidence-first
- 迁移策略：旧 CLI 保持兼容；`agent` 入口已使用 Composer/AgentLoop，`pipeline` 入口仍会转入 legacy subprocess 兼容路径

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
- 当前仓库已具备 Tauri 桌面壳、React 前端、Python sidecar、JSON-RPC bridge 与一键启停脚本；9 页 GUI 已完成产品化垂直切片，并为各页保留真实 Tauri native verifier
- Quick Run 已接入 `run.quick.start` / `run.quick.cancel`，可从 GUI 直接启动本地单次 pipeline；CLI 命令仍保留为 fallback。Resumes 页已接入 PDF export RPC。Markdown 转 PDF 会优先使用 `weasyprint`/`markdown` 高保真渲染；依赖缺失时自动使用内置基础 PDF writer，避免 runtime 断链。高保真 PDF 依赖见 `requirements-pdf.txt`；安装后 `pnpm --dir ui run prepare:python-runtime` 会把可选 PDF runtime 带入 Tauri packaged sidecar。
- Quick Run 自动化主入口是 native verifier：`pnpm --dir ui run e2e:quick-run` 会用 `pnpm tauri dev` 启动真实 Tauri 窗口，并通过 `VITE_QUICK_RUN_VERIFY_AUTORUN=quick-run` 驱动页面点击稳定 selector，最后用 `outputs/quick_runs` 与 run summary 校验结果。`e2e:quick-run:webdriver` 仅保留为 Windows/Linux 的可选补充。
- System Settings 桌面验收主入口是 `pnpm --dir ui run e2e:system-settings`。该命令启动真实 Tauri dev shell，自动导航到 `/system-settings`，并等待页面通过真实 Tauri bridge + sidecar `settings.get` 写出 `system_settings.load.ready` 事件；普通 Vite 浏览器页或 mock bridge 不算该页面的最终验收。
- 其它 GUI 页面 native verifier 入口包括：`e2e:overview`、`e2e:resumes`、`e2e:evidence`、`e2e:jobs`、`e2e:agent-run`、`e2e:submissions`、`e2e:policy`。这些脚本都会启动真实 Tauri dev shell，自动导航到目标页面，并等待真实 bridge + sidecar 写出对应 `*.load.ready` 事件。

## 快速开始

### 环境要求

- Python 3.10+（或兼容 Python 3 运行时）

可选高保真 PDF 导出：

```bash
python3 -m pip install -r requirements-pdf.txt
pnpm --dir ui run prepare:python-runtime
```

### 一键启动 / 停止桌面 App

```bash
./app start    # 后台启动 Tauri dev app
./app status   # 查看状态和日志路径
./app stop     # 停止 Tauri/Vite/sidecar 进程链
./app restart  # 重启
```

运行日志写入 `.app-runtime/piproofforge-app.log`。

### 一键跑通样例

```bash
python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml
```

### 本地 Demo 验收

```bash
bash scripts/acceptance/run-demo.sh
```

该命令包装现有样例 pipeline，校验 Evidence Card、Matching Report、A/B Markdown Resume、Scorecard、Run Record 与关键事件是否齐全，并写出：

- `outputs/demo/<run_id>/demo-report.json`
- `outputs/demo/<run_id>/demo-report.md`

演示前推荐使用聚合检查入口：

```bash
bash scripts/acceptance/run-demo-readiness.sh
```

默认只运行本地确定性 Demo 检查。需要同时启动真实 Tauri Quick Run 验收时，显式加：

```bash
bash scripts/acceptance/run-demo-readiness.sh --include-gui
```

聚合报告写入 `outputs/demo/<run_id>/readiness-report.json` 与 `readiness-report.md`。

演示顺序和排障清单见 `docs/demo-runbook.md`。

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

### v2 CLI 统一入口（新增）

```bash
python3 -m tools.cli.entrypoints <command> [args]
```

命令包括：`extract`、`match`、`generate`、`evaluate`、`pipeline`、`agent`。

例如：

```bash
python3 -m tools.cli.entrypoints agent --policy policy.yaml --dry-run --run-id run-001 --output-dir outputs/agent_runs
```

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
- extraction/matching/generation/evaluation 已可从 CLI 端到端运行，默认产物是 Markdown 简历与 Scorecard
- 普通 `tools/run_pipeline.py` 可跑通，并会写统一 Run Record 到 `outputs/agent_runs/<run_id>/run_log.json` 与 `summary.json`；内部仍保留 legacy subprocess 串联
- Agent manual REVIEW 会在审批点写入 `outputs/review_queue/<run_id>.json` 并返回 `REVIEW_PENDING`，不会未经审批进入投递
- Markdown 简历转 PDF 的代码路径已接入 sidecar；当前环境缺少 `weasyprint`/`markdown` 时也可用内置基础 PDF writer 导出非空 PDF；如安装 `requirements-pdf.txt`，staging 会将可选 PDF 包复制进 packaged runtime
- job-discovery 和 submission 属于支撑系统；当前项目主线仍以 evidence-first 求职材料工程为准
- GUI 终版规范已冻结，当前实现仍是垂直切片；Quick Run 已能从桌面 GUI 直接运行本地单次 pipeline
- 2026-05-17 收束审计见 `docs/reports/project-state-and-core-flow-review.md`

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

- Current target spec: Unified Core Engine v2 (component layer implemented; CLI pipeline still keeps a legacy subprocess compatibility path)
- Architecture direction: `domain/` + `infra/` + `engines/` + `orchestration/` + `config/` + `channels/` + `cli/`
- Final GUI path: `Tauri desktop app + React/TypeScript frontend + Python sidecar`
- Design principles: high cohesion, low coupling, composition over inheritance, extension over modification, evidence-first
- Migration strategy: keep legacy CLI compatible; the `agent` entrypoint uses Composer/AgentLoop, while the `pipeline` entrypoint still falls back to the legacy subprocess path

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
- The repository now includes the Tauri desktop shell, React frontend, Python sidecar, JSON-RPC bridge, and one-command app control. All 9 GUI pages have productized vertical slices with real Tauri native verifiers.
- Quick Run is wired to `run.quick.start` / `run.quick.cancel` and can launch a local single-pass pipeline directly from the GUI; CLI commands remain as a fallback. The Resumes page has a PDF export RPC; Markdown-to-PDF prefers `weasyprint` and `markdown` for high-fidelity rendering, then falls back to the built-in basic PDF writer when those packages are missing. High-fidelity PDF dependencies are listed in `requirements-pdf.txt`; after installation, `pnpm --dir ui run prepare:python-runtime` stages the optional PDF runtime into the Tauri packaged sidecar.
- The primary Quick Run automation path is a native verifier: `pnpm --dir ui run e2e:quick-run` starts the real Tauri window via `pnpm tauri dev`, uses `VITE_QUICK_RUN_VERIFY_AUTORUN=quick-run` to click stable selectors inside the page, and verifies `outputs/quick_runs` plus the run summary. `e2e:quick-run:webdriver` remains only as an optional Windows/Linux supplement.
- Other GUI page native verifier entrypoints are `e2e:overview`, `e2e:resumes`, `e2e:evidence`, `e2e:jobs`, `e2e:agent-run`, `e2e:submissions`, and `e2e:policy`. Each starts the real Tauri dev shell, routes to the target page, and waits for the real bridge + sidecar to emit the page-specific `*.load.ready` event.

### Quick Start

Requirements:

- Python 3.10+ (or compatible Python 3 runtime)

Optional high-fidelity PDF export:

```bash
python3 -m pip install -r requirements-pdf.txt
pnpm --dir ui run prepare:python-runtime
```

Start and stop the desktop app:

```bash
./app start
./app status
./app stop
./app restart
```

Runtime logs are written to `.app-runtime/piproofforge-app.log`.

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
- End-to-end extraction/matching/generation/evaluation is runnable from the CLI and currently produces Markdown resumes plus scorecards by default
- `tools/run_pipeline.py` is runnable and writes a unified run record under `outputs/agent_runs/<run_id>/run_log.json` plus `summary.json`; internally it still keeps the legacy subprocess chain
- Agent manual REVIEW writes `outputs/review_queue/<run_id>.json` and returns `REVIEW_PENDING` instead of delivering without approval
- Markdown-to-PDF export is wired through the sidecar and remains available without `weasyprint`/`markdown` through the built-in basic PDF writer; installing `requirements-pdf.txt` lets staging copy the optional PDF packages into the packaged runtime
- Job discovery and submission are supporting systems; the project mainline remains evidence-first career-material engineering
- The final GUI specification is frozen; the current desktop app is still a vertical-slice implementation, and Quick Run can now launch the local single-pass pipeline directly
- 2026-05-17 state audit: `docs/reports/project-state-and-core-flow-review.md`

### License

MIT. See `LICENSE`.
