# 架构与执行链路审核报告（2026-11-07）

## 范围与方法

本次审核以「项目整体性、系统性、架构合理完整性」为目标，对照：

- 项目愿景：`PLAN.md`（evidence-first 求职引擎）。
- 项目宪法：`constitution.md` 八条不可妥协原则（Evidence-First、事实保真、Spec-First、
  TDD、外部自动化驱动真实页面验收、轻量工程、新增前先探索、门禁分层）。
- 架构规范：`openspec/specs/pi-proof-forge-core.md`「统一核心引擎架构规范」
  （六边形分层、零 subprocess 串联、唯一实现、OCP、DIP、组合优于继承、ISP）。
- 验收口径：`docs/execution-roadmap.md`、`acceptance/journey_implementation_matrix.yaml`。

方法：文档与实现交叉核对 + 分层依赖静态扫描 + 全量测试基线 + 真实 CLI 运行验证。
基线（重构前）：全量测试 1765 passed / 1 skipped / 53 subtests。

## 总体结论

项目愿景、宪法与 OpenSpec 规范完整且自洽；问题出在**实现层与规范脱轨**：
规范要求「engines 是唯一业务实现、入口层薄、阶段间纯 Python 调用」，实际却是
两套实现并存——v2 engines 只有演示级最小实现，真实生产逻辑散落在
`tools/run_*.py` 根目录脚本、`tools/infra/semantic_matching.py` 与 sidecar
handlers 中，并通过 `PPF_FORCE_LEGACY_MAIN` 双路由与 `subprocess` 串联掩盖了这一点。

本次按「真实逻辑唯一实现」原则完成 8 批重构：执行链路统一、分层错位归位、
架构门禁加严、文档与契约同步、测试与巨型模块拆分。剩余唯一架构债是
「Agent Run 仍注入简化引擎」（见「剩余路线 R1」），已显式记录、不冒称完成。

## 问题清单与处置

### P0-1 规范与实现双轨（已修复）

- 现象：`engines/evidence/rule_extractor.py` 41 行、`engines/matching/rule_scorer.py`
  等是演示级实现；真实规则/渲染/评测在 `tools/run_*.py`（合计约 2100 行）与
  `tools/extract_evidence*.py`（445 行）。
- 影响：架构声明失真；修改规则需改两处或只改脚本，规范无法约束实现。
- 处置：真实逻辑整体迁入 engines（evidence/matching/generation/evaluation），
  编排流程迁入 orchestration，删除根目录脚本。

### P0-2 legacy 双路由与 subprocess 串联（已修复）

- 现象：`cli/commands/*.py` → `_runner.run_legacy_main` → 设置
  `PPF_FORCE_LEGACY_MAIN=1` → 反向 import 回 `tools/run_*.py`；`run_pipeline.py`
  用 `subprocess.run` 依次执行四个脚本，Run Record 事件里记录命令行。
- 影响：阶段错误传播靠 returncode、无法复用进程内对象、入口层无法测试；规范
  明令「零 subprocess 串联」。
- 处置：删除 `_runner` 与全部 `tools/run_*.py`；pipeline 改为进程内四阶段；
  Quick Run 保留的外层进程边界仅用于隔离模型环境与超时（`Popen` 执行
  `python3 -m tools.cli.entrypoints pipeline`），不再是阶段间调用方式。
- 门禁：`check_v2_constraints.py` 新增 legacy 模式与根目录脚本检查。

### P0-3 双引擎并存（未修复，列入剩余路线）

- 现象：Quick Run 走统一后的真实链路；Agent Loop 仍由 `Composer` 注入
  `RuleMatchingEngine` / `TemplateAssembler` / `RuleEvaluationEngine` 三个简化引擎
  （domain model 输入，与真实 YAML 数据流并行）。
- 影响：同一次 job 用 Agent Run 与 Quick Run 会得到不同质量与不同口径的结果。
- 根因：domain 模型与真实数据结构（`parse_simple_yaml` 的 scalars/lists、字段级
  provenance、claims trace）之间存在类型鸿沟。需要先建立「真实数据 ↔ domain
  模型」映射层，再让 Composer 注入真实引擎适配器；不在本次静态重构范围内。
- 路线：见下文「剩余路线 R1」。

### P1-1 分层错位（已修复）

- `tools/infra/semantic_matching.py`（语义匹配引擎，369 行）→
  `tools/engines/matching/semantic_matching.py`。
- `tools/discovery/filters.py`（候选过滤引擎）→ `tools/engines/discovery/filters.py`，
  删除空的顶层 `tools/discovery`。
- `tools/infra/resume_content.py` 反向依赖 `tools/engines`（生成渲染器）→ 改为本层
  只读解析（含 source_sha256），恢复 infra 不依赖 engines。
- 门禁：新增分层依赖方向检查（domain 零层依赖；infra 不依赖 engines/orchestration/cli；
  engines 不依赖 orchestration/cli；orchestration 不依赖 cli/sidecar；cli 不依赖
  sidecar/acceptance；sidecar 不依赖 acceptance）。

### P1-2 巨型模块（已修复）

- sidecar handlers：subscription/evidence/jobs/native_pdf/settings 等 5 个 700–1800 行
  模块按域拆分（原模块保留公开 handler 与全部原符号 re-export），新增
  `handlers/_shared/` 承载跨域共享实现；`agent.py`（2225 行）拆为 141 行门面 +
  `quick_run` / `quick_run_progress` / `quick_run_results` / `agent_run` /
  `agent_delivery` / `agent_review` 六个域子模块。拆分后 sidecar handlers 全部 ≤600 行；
  patch 语义兼容（路径常量、Popen、运行态仍由门面持有，子模块运行时读取）。
- UI 页面：evidence 1755 → 833、submissions 1473 → 866、quick-run 894 → 509；
  新增 21 个区块组件与 3 个 helpers，子组件纯展示、扁平依赖；配套 21 个 GUI 契约
  测试 harness 适配（模块 loader / jsx 展开 / 页面目录聚合源码），断言内容未弱化。

### P2-1 测试组织与分层不对应（已修复）

- `tests/domain/` 与 `tests/unit/domain/` 重复；`tests/unit/domain` 混放
  engines/orchestration/cli/config/errors/submission/工具脚本测试。
- 处置：按实现分层重组（domain/engines/orchestration/cli/config/errors/channels/
  submission/tooling），纯移动不改测试内容。

### P2-2 文档引用漂移（已修复当前事实文档）

- README、tools/README、OpenSpec core spec、AIEF 当前技术文档、sidecar RPC 契约
  均引用已删除的脚本。
- 处置：已同步。历史台账/路线图/变更提案/经验文档按历史记录保留原文。

### P3-1 仓库整洁（已清理）

- `tools/poc_*.py`（8 个）、`tools/test_liepin_direct.py`、`tools/capture_job_url.py`
  为 2026-05 投递能力探索期脚本，无任何代码/文档引用；工作区 `debug_dom*.html/png`
  为本地调试产物。均已删除。

## 批次化提交（可 review 粒度）

| 提交 | 主题 |
| --- | --- |
| `57a52aa` | chore：移除早期探测脚本与本地调试产物 |
| `f2e6180` | refactor(evidence)：证据提炼下沉引擎层并收敛为单一 CLI 入口 |
| `8c6584e` | refactor(pipeline)：统一执行链路，业务逻辑下沉引擎与编排层 |
| `ce74dc7` | refactor(arch)：修正分层错位并加严架构门禁 |
| `52b4b21` | docs：同步执行入口重构后的文档与契约 |
| `6d50ad6` | refactor(ui)：拆分 Evidence / Submissions / Quick Run 三个超大页面 |
| `86d5e19` | test：按实现分层重组测试目录 |
| `5d3fe0d` | refactor(sidecar)：拆分超大 handler 模块并消除跨模块私有依赖 |
| `0865fc7` | refactor(sidecar)：将 agent handler 巨型模块拆为域子模块 |

## 验证证据（最终）

- 全量 Python 测试：**1766 passed, 1 skipped, 53 subtests**（重构前 1765；差异来自
  删除 6 项 legacy 重定向护栏测试、新增 6 项架构门禁自检，另净增 1）。
- 架构门禁：`python3 tools/check_v2_constraints.py --root .` PASS，含 6 项自检
  （违规分层、legacy 残留、根目录遗留脚本、orchestration argparse、重复 LLM helper
  均能被抓到）。
- 项目门禁：`python3 tools/check_execution_roadmap.py --root .` PASS；
  `python3 tools/check_aief_l3.py --root . --base-dir AIEF` PASS。
- UI：`npx tsc --noEmit` PASS；`pnpm build` PASS；GUI 契约测试 143 passed。
- 真实端到端：`python3 -m tools.cli.entrypoints pipeline --raw tools/sample_raw.txt
  --job-profile job_profiles/jp-2026-001.yaml` 规则模式跑通，写出统一 Run Record
  （`PIPELINE_START/STEP_SUCCESS/DONE`）、A/B Markdown、scorecard；CLI `extract` 与
  `match` 也已真实运行验证。
- 边界：本次为本地静态/单测/CLI 验证，不包含真实外部平台验收；GUI 验收仍须按
  `constitution.md` 第 5 条由外部自动化驱动真实页面，既有 roadmap 验收状态不变。

## 剩余路线（显式，不计入本次完成）

- R1 统一 Agent 编排引擎：建立真实数据结构与 domain 模型的映射层，让
  `Composer` 注入真实引擎适配器，消除「Agent Run 与 Quick Run 两套引擎」。
- R2 提交前检查脚本归一：`check_*` / `kb` / 发布脚本仍位于 tools 根目录，后续可
  收敛为 `python3 -m tools.cli.entrypoints` 子命令（低优先级，当前不影响分层门禁）。
- R3 UI 页面 hooks 提取：三个页面剩余行数主要来自与多状态耦合的 hooks 逻辑，后续
  可评审是否提取自定义 hook（会改变 effect 依赖结构，需独立回归）。

## 假设与边界

- 「不需要兼容历史」按用户授权执行：删除 legacy 脚本与双路由，不保留兼容 shim。
- 规格驱动的业务流程（Quick Run / Agent Run / 投递）行为不变；本次只改变实现位置
  与调用方式，RPC 契约、产物路径、事件类型与状态语义保持兼容。
- 项目未发布上线，因此不涉及外部用户迁移；本机数据目录（outputs/materials 等）
  未纳入重构与删除范围。
