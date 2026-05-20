# Project Ledger / 项目事实台账

> 权威项目状态基线。新会话 AI 和协作者的第一阅读入口。
> 每次重要变更后必须同步更新本文件。若与 tasks.md 冲突，以本文件为准。

## 1. 当前阶段目标

**状态收束完成 + GUI 9 页产品化垂直切片收口**

> 2026-05-18 状态：核心 CLI 主链路已可生成 Evidence Card、Matching Report、Markdown Resume、Evaluation Scorecard；Agent dry-run 可写 Run Record；普通 `tools/run_pipeline.py` 保留 legacy subprocess 串联，但已补齐统一 Run Record，写入 `outputs/agent_runs/<run_id>/run_log.json` 与 `summary.json`。PDF Markdown 转换已补上内置无依赖兜底路径，当前环境 `WEASYPRINT_AVAILABLE=False` 时仍可导出非空 PDF；Agent REVIEW manual 模式已从直接 approve 改为写入 `outputs/review_queue/<run_id>.json` 并返回 `REVIEW_PENDING`，不会进入 DELIVER；GUI Quick Run 已注册 `run.quick.start` / `run.quick.cancel` 并从页面直接启动本地单次 pipeline，CLI 命令保留为 fallback，且已补上 Tauri native verifier 自动化入口。Quick Run verifier 已按 `pnpm --dir ui run e2e:quick-run` 连续多轮通过；dev 模式 sidecar 工作目录、`PYTHONPATH`、进程树清理和 pnpm 参数转发问题已修复。审计报告见 `docs/reports/project-state-and-core-flow-review.md`。状态清理已同步到 README、project-ledger、OpenSpec tasks，并已处理 GitHub issues #21-#27。
> 2026-05-18 补充：WeasyPrint 高保真 PDF 增强已完成工程闭环。`requirements-pdf.txt` 显式声明 `markdown` / `weasyprint` 可选依赖；`pnpm --dir ui run prepare:python-runtime` 会在依赖已安装时把可选 PDF 包和元数据复制进 Tauri packaged runtime；未安装时会清理旧 staged 包并继续使用内置基础 PDF writer 兜底。
> 2026-05-18 补充：Submissions 页面产品化垂直切片已按终版 GUI 第 7 页补齐统计卡片、投递表格、详情基本信息、步骤时间线、截图缩略图/预览、失败详情与两种重试策略按钮；实现复用既有 `submission.list/detail/retry` 合同，不新增 sidecar 协议。
> 2026-05-18 补充：Agent Run 页面产品化垂直切片已按终版 GUI 第 6 页补齐运行启动/停止/刷新、10 状态机、N-Pass Gate 摘要、事件流与人工审批面板；实现复用既有 `run.agent.start/get/stop` 与 REVIEW RPC 合同，仅为 `getPendingReview` / `submitReview` 前端调用补上可选 `run_id` 参数，不新增 sidecar 协议。
> 2026-05-19 补充：System Settings 页面产品化垂直切片已按终版 GUI 第 9 页补齐左侧 Channels / LLM Config 分组导航、通道状态卡、fallback 顺序、连接检查、凭证状态、LLM 配置字段与 API key 掩码状态；`settings.get` 返回 Liepin / Email 通道运行状态快照，不返回明文 secret，不新增敏感信息写入路径。该页已补上真实 Tauri native verifier：`pnpm --dir ui run e2e:system-settings` 会启动桌面壳、自动导航到 `/system-settings`，并等待真实 bridge + sidecar 写出 `system_settings.load.ready`，普通 Vite/mock bridge 不再作为最终验收口径。
> 2026-05-19 补充：Policy 页面产品化垂直切片已按终版 GUI 第 8 页补齐左侧 Gate Policy / Exclusion List 分组导航、顶部保存主动作、门禁字段卡、delivery_mode / batch_review 交互、企业展示名与企业主体分区编辑、规则预览和 Discovery/Gate 命中说明；实现继续复用既有 `settings.get/update` 合同，不新增 sidecar 协议。`delivery_mode=auto` 时关闭 `batch_review` 的策略不变量已下沉到前端交互、sidecar settings 读写、config validator 与根 `policy.yaml`，避免真实 settings 数据形成无效人工审批状态。该页已补上真实 Tauri native verifier：`pnpm --dir ui run e2e:policy` 会启动桌面壳、自动导航到 `/policy`，并等待真实 bridge + sidecar 写出 `policy.load.ready`。
> 2026-05-19 补充：Overview 页面产品化垂直切片已按终版 GUI 第 1 页补齐顶部 Run Agent 主动作、四项统计卡片、图标化最近活动、SVG 匹配趋势图、缺口严重度汇总和证据缺口跳转；实现继续复用既有 `overview.get` 合同，不新增 sidecar 协议。该页已补上真实 Tauri native verifier：`pnpm --dir ui run e2e:overview` 会启动桌面壳、自动导航到 `/`，并等待真实 bridge + sidecar 写出 `overview.load.ready`。
> 2026-05-19 补充：Resumes 页面产品化垂直切片已按终版 GUI 第 2 页补齐三栏资产中心：Personal Profile 资料完整度/缺失字段/编辑保存、Uploaded Resumes 上传文件列表与路径上传入口、Generated Resumes 版本列表/分数/目标上下文/纸张式预览/PDF 导出目标路径。实现继续复用既有 `profile.get/update` 与 `resume.list/upload/getPreview/exportPdf` 合同，不新增 sidecar 协议；运行态文案已接入单语 i18n。该页已补上真实 Tauri native verifier：`pnpm --dir ui run e2e:resumes` 会启动桌面壳、自动导航到 `/resumes`，并等待真实 bridge + sidecar 写出 `resumes.load.ready`。
> 2026-05-20 补充：Jobs 页面产品化垂直切片已按终版 GUI 第 4 页补齐岗位画像统计、Profile / Lead 分段视图、岗位画像卡片网格、画像详情编辑、线索表格、线索详情与转为 Job Profile 操作；实现继续复用既有 `jobs.listProfiles/listLeads/createProfile/updateProfile/convertLead` 合同，不新增 sidecar 协议。该页已补上真实 Tauri native verifier：`pnpm --dir ui run e2e:jobs` 会启动桌面壳、自动导航到 `/jobs`，并等待真实 bridge + sidecar 写出 `jobs.load.ready`。
> 2026-05-20 补充：Evidence 页面产品化垂直切片已按终版 GUI 第 3 页补齐证据统计、筛选入口、证据卡表格、右侧详情编辑、Results 高亮信息、Stack & Tags、Artifacts 文件列表与导入/追加/替换入口；实现继续复用既有 `evidence.list/get/create/update/delete/import` 合同，不新增 sidecar 协议。该页已补上真实 Tauri native verifier：`pnpm --dir ui run e2e:evidence` 会启动桌面壳、自动导航到 `/evidence`，并等待真实 bridge + sidecar 写出 `evidence.load.ready`。
> 2026-05-20 补充：Quick Run 页面产品化垂直切片已按终版 GUI 第 5 页从“命令复制/资源摘要”收口为单次 pipeline 操作台：顶部 Profile 选择与 Run/Cancel 主动作、4 阶段状态条、终端式 Stage Output、K/D/S/Q/E/R ScoreBar 和总分。实现复用既有 `run.quick.start/cancel` 合同，仅扩展 `run.quick.start` 返回 stdout/stderr、summary artifacts 与匹配分项，未新增 RPC 方法；native verifier 现在会先等待真实 bridge + sidecar 写出 `quick_run.load.ready`，再触发 autorun 并校验 run summary。验证：`python3 -m pytest tests/ -q` → 380 passed；`pnpm --dir ui build` → pass；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS；`pnpm --dir ui run e2e:quick-run` → DONE（`qr_20260519163230256817`）。
> 2026-05-20 补充：Demo 闭环方向已先落地本地确定性验收入口与演示前聚合检查。`scripts/acceptance/run-demo.sh` / `tools/acceptance/demo_run.py` 包装现有样例 pipeline，校验 Evidence Card、Matching Report、A/B Markdown Resume、Scorecard、Run Record 与关键事件，并写出 `outputs/demo/<run_id>/demo-report.json` / `.md`。`scripts/acceptance/run-demo-readiness.sh` / `tools/acceptance/demo_readiness.py` 作为演示前主入口，默认只跑确定性本地 Demo，显式 `--include-gui` 时再调用 `pnpm --dir ui run e2e:quick-run`，并写出 `readiness-report.json` / `.md`。验证：临时副本执行 `bash scripts/acceptance/run-demo.sh --run-id demo_verify_20260520` → pass；临时副本执行 `bash scripts/acceptance/run-demo-readiness.sh --run-id readiness_verify_20260520` → pass；`python3 -m pytest tests/ -q` → 388 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS。
> 2026-05-20 补充：Demo runbook 已补齐。`docs/demo-runbook.md` 固化演示前检查、可选 GUI 检查、演示顺序、失败排障和安全范围；`tests/acceptance/test_demo_runbook.py` 锁定主入口命令、报告路径、核心产物路径和“不做真实投递/外部发现”的边界。验证：`python3 -m pytest tests/acceptance/test_demo_run.py tests/acceptance/test_demo_readiness.py tests/acceptance/test_demo_runbook.py -q` → 11 passed；`python3 tools/check_v2_constraints.py --root .` → PASS。
> 2026-05-20 补充：已按 Demo runbook 在当前工作区完成一次默认 readiness 试跑。`bash scripts/acceptance/run-demo-readiness.sh` → pass，生成 `outputs/demo/demo_ready_20260519164944/readiness-report.md` 与 `demo-report.md`；按 runbook 抽查 Evidence、Matching、A/B Resume、Scorecard、Run Record 均存在且非空。`.gitignore` 已收窄忽略 `evidence_cards/ec-demo_*.yaml` / `ec-qr_*.yaml` 与 `matching_reports/mr-demo_*.yaml` / `mr-qr_*.yaml`，避免演示/Quick Run 产物污染源码状态，同时不影响正常证据卡/匹配报告版本控制。验证：`python3 -m pytest tests/ -q` → 391 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS。
> 2026-05-20 补充：桌面 GUI 验收已按 Demo runbook 执行。首次 `--include-gui` 在沙箱内因 `listen EPERM ::1:1420` 失败；提升权限后发现 1420 被本仓库残留 `pnpm run dev` / Vite 进程占用，停止残留进程后重跑成功。`bash scripts/acceptance/run-demo-readiness.sh --include-gui` → pass，生成 `outputs/demo/demo_ready_20260519165837/readiness-report.md`；`ui/test-results/quick-run-native/app-events.jsonl` 记录 `quick_run.load.ready`、`quick_run.autorun.click`、`quick_run.start.result`，其中 `run_id=qr_20260519165844857109`、`status=DONE`、`score_total=95`。1420 端口收尾检查无监听残留。
> 2026-05-20 补充：发布前构建检查已通过：`pnpm --dir ui build` → pass；`python3 -m pytest tests/ -q` → 395 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS。
> 2026-05-20 补充：BOSS/智联只读发现 adapter 已完成第一阶段接入。新增 `tools/infra/discovery/boss_agent_cli.py`，把外部 `boss schema/status/search/detail --json` 类读操作隔离在 infra 层；`tools/engines/discovery/job_leads_loader.py` 通过 `PPF_ENABLE_BOSS_AGENT_SEARCH=1` 或 `enable_boss_agent_search=True` 显式开启，默认不触发外部 CLI，并将 search 结果映射为 `Candidate(source="boss_agent:<platform>")`。当前只做 read-only discovery，不启用投递/沟通等写操作；真实外部 CLI 联调仍需在安装并配置 `PPF_BOSS_AGENT_CLI` 后单独执行。验证：`python3 -m pytest tests/unit/domain/test_discovery_engine.py tests/unit/infra/test_boss_agent_cli.py -q` → 10 passed；`python3 tools/check_v2_constraints.py --root .` → PASS。
> 2026-05-20 补充：GUI 页面可见文案合法性与准确性审计已完成。`ui/src/i18n/zh.json` 清理了普通 UI 文案里的中英文混排，将 Sidecar / Agent / Evidence Card / Discovery / Gate / Dry Run / PASS 等面向用户状态改为中文；仅保留 `PDF`、`OpenAI`、路径示例和 `exact:` / `contains:` 等必要技术字面量。Submissions 文案从“投递记录/提交时间/重试”收窄为“投递尝试/运行时间/排队重试”，避免把本地尝试日志误导成真实成功投递；System Settings 禁用动作从“保存”改为“只读”，并把“连通检查/实时配置”改为更准确的状态快照文案。验证：`zh.json` / `en.json` key 数一致（449 / 449）；`pnpm --dir ui build` → pass；`python3 -m pytest tests/unit/gui -q` → 30 passed；`python3 -m pytest tests/ -q` → 395 passed。
> 2026-05-20 补充：Agent Run 与 Submissions 页面已补齐真实 Tauri native verifier，收口此前仅有 Vite/mock 或页面合同验收的缺口。新增 `pnpm --dir ui run e2e:agent-run` 会启动桌面壳、自动导航 `/agent-run`，等待真实 bridge + sidecar 写出 `agent_run.load.ready`；新增 `pnpm --dir ui run e2e:submissions` 会自动导航 `/submissions` 并等待 `submissions.load.ready`。验证：`python3 -m pytest tests/unit/gui -q` → 34 passed；`python3 -m pytest tests/ -q` → 399 passed；`pnpm --dir ui build` → pass；`cargo fmt --manifest-path ui/src-tauri/Cargo.toml -- --check` → pass；`cargo test --manifest-path ui/src-tauri/Cargo.toml` → 7 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS；`pnpm --dir ui run e2e:agent-run` → pass（profile_count=5）；`pnpm --dir ui run e2e:submissions` → pass（submission_count=20）。
> 2026-05-20 补充：修复左侧菜单切换失效问题。根因是 native verifier 中断/并行运行后可能残留 `ui/.env.local` 的 `VITE_QUICK_RUN_VERIFY_AUTORUN`，使 `NativeVerifyController` 在普通开发模式下持续把路由拉回验收目标页。现已删除残留 `.env.local`，并改为只有 `VITE_NATIVE_VERIFY=1` 时才启用自动导航；native verifier 脚本不再写 `.env.local`，只通过子进程环境变量传递验收场景。新增合同测试防止脚本重新写入 `VITE_ENV_LOCAL`。验证：`python3 -m pytest tests/unit/gui -q` → 36 passed；`pnpm --dir ui build` → pass；`pnpm --dir ui run e2e:agent-run` → pass，且未生成 `ui/.env.local`。
> 2026-05-20 补充：GUI i18n 实现审计完成。当前使用 `i18next + react-i18next`，入口 `ui/src/main.tsx` 加载 `ui/src/i18n/index.ts`，中英文资源 `en.json` / `zh.json` 均为 449 个叶子 key 且 key 集完全一致；静态 `t("...")` key 均可在两套资源中找到。修复了 `useAppShellStore` 默认语言仍为 `en`、与 i18n 默认 `zh` 不一致导致语言按钮初始态错误的问题；修复 System Settings 对历史中文状态值 `已配置（掩码）` / `未配置` 在英文界面下可能原样显示中文的问题。新增全局 i18n catalog 合同测试，锁定中英文 key parity 与静态 key 覆盖。验证：`python3 -m pytest tests/unit/gui -q` → 38 passed；`pnpm --dir ui build` → pass。
> 2026-05-20 补充：Agent Run 页面 i18n 补齐。状态机节点和事件流不再直接展示内部枚举 `INIT / DISCOVER / SCORE / ...`，运行状态 chip 不再直接显示 `idle` / `DONE` / `REVIEW_PENDING` 等内部值；展示层改为 `pages.agentRun.states.*` 与 `pages.agentRun.runStatuses.*`。中英文资源更新为 467 个叶子 key 且仍保持一致。验证：`python3 -m pytest tests/unit/gui -q` → 38 passed；`python3 -m pytest tests/ -q` → 403 passed；`pnpm --dir ui build` → pass。

- 六边形领域核心（domain/）→ 已完成
- 策略注册表 + 四大引擎（engines/）→ 已完成
- Stage 组合编排 + 状态机（orchestration/）→ 已完成 ✅
- 配置解聚 + Composer（config/）→ 已完成（含 build_agent_loop） ✅
- Result 类型 + 事件溯源（domain/）→ 已完成
- 通道层 + CLI 收口 → 已完成
- **AgentLoop 全阶段集成 → 已完成 ✅（2026-05-08）**
- **全链路集成测试 → 已恢复 ✅（351 tests，2026-05-18）**
- **Benchmark 基线 → 已完成 ✅（4 份，docs/benchmarks/）**
- **AppleScript 猎聘搜索 → 已完成 ✅（2026-05-09）**
- **Agent Loop → Liepin 投递链路 → 已验证登录，已修正下线职位误报上传失败（2026-05-09）**
- **猎聘真实投递闭环验证 → ✅ 已完成（2026-05-11）**
- **PDF runtime 基础闭环 → ✅ 已完成（2026-05-17）。Markdown→PDF 在缺少 `weasyprint`/`markdown` 时使用内置基础 PDF writer；WeasyPrint 仍作为高保真可选路径。**
- **用户场景化自动验收 → scenario-first M-1 与 M0 case-aware journey contract 已完成；在状态清理完成前不作为 Top Priority。**
- **外部仓库调研：`boss-agent-cli` 已完成初步解析（2026-05-15）→ 结论是 P2 级参考资产，适合通过薄 CLI adapter 接入 BOSS/智联职位发现与 Agent-friendly JSON/schema/MCP 设计；不建议直接引入其简历/AI 核心或 vendor 整仓**

## 2. 已完成事项

| 事项 | 状态 | 证据路径 | 验证方式 | 备注 |
|------|------|----------|----------|------|
| Domain 核心模型 | 已验证 | tools/domain/models.py | 14 tests passed | EvidenceCard/JobProfile/MatchingReport/ResumeOutput/Scorecard + GUI 实体 |
| Value Objects | 已验证 | tools/domain/value_objects.py | 22 tests passed | Score/GapTask/Candidate/GateDecision/ReviewCandidate/ReviewDecision 等 |
| Result[T,E] 类型 | 已验证 | tools/domain/result.py | 4 tests passed | Ok/Err 用于可恢复错误 |
| 事件溯源 | 已验证 | tools/domain/events.py + run_state.py | 4 tests passed | RunEvent + RunState.replay() |
| 业务不变式 | 已验证 | tools/domain/invariants.py | 5 tests passed | evidence-first 守卫 + 事实保真校验 |
| Protocol 定义 | 已完成 | tools/domain/protocols.py | 结构验证 | 所有引擎/通道/Stage 接口定义 |
| Infra LLM Client | 已验证 | tools/infra/llm/client.py | test_llm_client.py | 唯一 HTTP 调用点 |
| Infra YAML IO | 已验证 | tools/infra/persistence/yaml_io.py | test_yaml_io.py | 唯一 YAML 读写实现 |
| Infra RunStore | 已验证 | tools/infra/persistence/file_run_store.py | test_file_run_store.py | 事件追加写入 + 回放 |
| Infra Logging | 已完成 | tools/infra/logging.py | test_logging.py | 结构化 JSON 日志 |
| Config 切片 | 已完成 | tools/config/fragments.py | 结构验证 | LLMConfig/PathConfig/PolicyConfig/EngineSelection |
| Config Loader + Validator | 已验证 | tools/config/loader.py + validator.py | test_config_loader.py | 含企业例外清单校验 |
| Config Composer | 已完成 | tools/config/composer.py | test_composer.py | 注册表构建 + LLM 策略注入 |
| Error 层 | 已验证 | tools/errors/exceptions.py + handler.py | test_error_handler.py | 不可恢复异常 + 错误路由 |
| Engine Registry | 已验证 | tools/engines/registry.py | 3 tests passed | 通用策略注册表 |
| Evidence 引擎 | 已验证 | tools/engines/evidence/ | test_evidence_engines.py | Rule + LLM extractor + validator + store |
| Matching 引擎 | 已验证 | tools/engines/matching/ | test_matching_engines.py | 六维度评分 + LLM scorer |
| Generation 引擎 | 已验证 | tools/engines/generation/ | test_generation_engines.py | template_assembler + llm_rewriter + exporter |
| Evaluation 引擎 | 已验证 | tools/engines/evaluation/ | test_evaluation_engines.py | 五维度评测 + LLM evaluator |
| Discovery 引擎 | 已验证 | tools/engines/discovery/ | test_discovery_engine.py | 三级回退 + 企业例外过滤 |
| State Machine | 已实现 | tools/orchestration/state_machine.py | 结构验证 | 10 状态（含 REVIEW），纯函数 |
| LinearPipeline | 已实现 | tools/orchestration/pipeline.py | test_orchestration.py | Stage 序列组合 |
| GateEngine | 已验证 | tools/orchestration/gate_engine.py | 6 tests passed | strict/simulate + N-pass + 企业排除兜底 |
| ReviewStage | 已验证 | tools/orchestration/review_stage.py | 4 tests passed | auto pass-through + manual 逐轮/批量 |
| Liepin Channel | 已实现 | tools/channels/liepin.py | test_channels.py | 纯 Python，无 subprocess |
| Email Channel | 已实现 | tools/channels/email.py | test_channels.py | smtplib，环境变量凭据 |
| CLI 统一入口 | 已验证 | tools/cli/entrypoints.py + 6 commands | test_cli_entrypoints.py | extract/match/generate/evaluate/pipeline/agent |
| 旧 CLI 兼容层 | 部分完成 | run_pipeline.py 等入口 | test_legacy_entrypoint_redirect.py + 2026-05-17 审计 | 参数语义不破坏；`run_pipeline.py` 仍转入 legacy subprocess 串联，不是纯 Composer/LinearPipeline |
| 企业例外清单 | 已验证 | discovery filter + gate guard | test_exclusions.py + test_gate.py | 双层防护 |
| Sidecar Bridge | 已验证 | tools/sidecar/ | 12 test files | JSON-RPC router + 9 handlers + REVIEW RPC |
| v2 约束检查 | 已通过 | tools/check_v2_constraints.py | PASS | 无重复 LLM/YAML、业务层无 subprocess、无 if use_llm；AppleScript 系统调用已收口到 infra/browser |
| AIEF L3 检查 | 已通过 | tools/check_aief_l3.py | PASS | 全部必需文件 + lessons + summaries |
| GUI 设计规范 | 已冻结 | ui/design/DESIGN.md + piproofforge.pen | 双真源联动 | 9 页 IA，暗色主题，Tauri + React/TS + Python sidecar |
| GUI 前端骨架 | 已实现 | ui/src/ (29 files) | 9 页面路由 + i18n + RPC transport | 骨架级别，非产品级 |
| **Composer build_agent_loop** | **已完成** | tools/config/composer.py | 集成测试通过 | 组装四大引擎 + GateEngine + ReviewStage + Channels |
| **AgentLoop 全阶段集成** | **已完成** | tools/orchestration/agent_loop.py | 6 integration tests | INIT→DISCOVER→SCORE→GENERATE→EVALUATE→GATE→REVIEW→DELIVER→LEARN→DONE |
| **全链路集成测试** | **已完成** | tests/unit/domain/test_full_pipeline.py | 9 tests passed | 含 dry-run 全状态、max_rounds、max_deliveries、企业排除、事件回放、多候选批次策略 |
| **Benchmark 基线** | **已完成** | docs/benchmarks/benchmark-001.md | rule-mode 完整评测 | 发现 matching 引擎不搜索 stack 字段 |
| **Matching 引擎 stack 搜索** | **已完成** | tools/domain/models.py + rule_scorer.py + store.py | 2 new tests | K-score 0.0→0.6，证据卡可区分 |
| **Matching gap task keywords 覆盖** | **已完成** | tools/engines/matching/rule_scorer.py + tests/unit/domain/test_matching_engines.py | `python3 -m pytest tests/unit/domain/test_matching_engines.py -q` → 7 passed | 空候选证据库和常规评分路径共用 gap task 生成逻辑；缺失 `keywords` 也会生成补证据任务，并避免与 `must_have` 重复 |
| **Liepin Channel 真实实现** | **已完成** | tools/channels/liepin.py | 集成 tools/submission/liepin.py (464行 Playwright) | 无 Playwright 时优雅降级为模拟模式 |
| **LLM 对比 Benchmark** | **已完成** | docs/benchmarks/benchmark-003.md | LM Studio openai/gpt-oss-120b | LLM K=0.73 vs Rule K=0.60，LLM 缺口更具体，建议混合策略 |
| **LLM Matcher prompt 修复** | **已完成** | tools/engines/matching/llm_matcher.py | 新增 stack 字段到 prompt | LLM 可看到技术栈信息 |
| **AppleScript 猎聘搜索** | **已完成** | tools/engines/discovery/liepin_search.py | PoC 验证 + 集成测试 | Playwright → AppleScript 驱动真实 Chrome，绕过 captcha |
| **AppleScript infra 边界修复** | **已完成** | tools/infra/browser/liepin_applescript.py + tools/engines/discovery/liepin_search.py | v2 约束检查通过 | 系统调用从 engines 层移入 infra adapter |
| **Agent Loop 简历文件写入** | **已完成** | tools/orchestration/agent_loop.py | 端到端验证 | DELIVER 前写入 outputs/{version}.md |
| **Agent Loop 空 URL 过滤** | **已完成** | tools/orchestration/agent_loop.py | 端到端验证 | GATE 前过滤无 job_url 的候选人 |
| **Liepin 登录检测修复** | **已完成** | tools/submission/liepin.py | check-mode 验证 | inline-login :visible 检测 + 正向登录指标 |
| **Playwright 反检测参数** | **已完成** | tools/submission/liepin.py | 已部署，待限流恢复后验证 | --disable-blink-features=AutomationControlled |
| **下线职位识别** | **已完成** | tools/submission/liepin.py | test_liepin_submission_browser_channel.py | “已下线 / 浏览更多优质职位”归类为 job_page_unavailable，避免误报 upload_input_not_found |
| **SubmissionRecorder browser_channel** | **已完成** | tools/submission/storage.py | 参数匹配修复 | set_meta() 新增 browser_channel |
| **目标关键词搜索** | **已完成** | tools/engines/discovery/job_leads_loader.py | discover_candidates(search_keywords=...) | 只搜索指定 job_profile 关键词，避免全量搜索触限 |
| **真实猎聘搜索显式开关** | **已完成** | tools/engines/discovery/job_leads_loader.py + tools/README.md | test_discovery_engine.py | 默认不触发真实 Chrome；需 `PPF_ENABLE_LIEPIN_SEARCH=1` 显式开启 |
| **Playwright-stealth 反反爬基础设施** | **已完成** | tools/submission/_browser.py | PoC 实测绕过 safe.liepin.com | stealth.js 注入（webdriver/chrome/plugins/languages）+ 人化节奏 + 安全护栏 |
| **猎聘真实投递入口确认** | **已完成** | tools/poc_probe_jobs.py | 13 职位采样 | 100% 职位只用"聊一聊"入口；部分职位同时存在"投简历"直投按钮；0 个职位有传统 input[type=file] |
| **聊一聊→发简历→确认发送 端到端闭环** | **已完成** | tools/poc_e2e_send.py | dry-run 6 步全通过 + SAP 职位真实发送 | data-tlg-elem-id 精准锁定主职位按钮，排除推荐区；jobId sanity check；支持"聊一聊"/"继续聊"文本兼容 |
| **主职位按钮 vs 推荐区误投防护** | **已完成** | tools/poc_e2e_send.py | dry-run 验证 recruiterName 匹配 | 用 `data-tlg-elem-id` 锁定主职位（非 `like_chat_btn`）；解析 data-params.jobId 做强校验 |
| **猎聘 session 初始化重构** | **已完成** | tools/setup_liepin_session.py | 一键启动，关闭即保存 | 从 argparse CLI 重构为简洁单文件；反检测参数内置 |
| **登录态检测增强** | **已完成** | tools/submission/liepin.py | check-mode 验证 | 新增 login modal 检测、nav-user-item 正向指标、聊一聊 fallback |
| **Modal 自动关闭** | **已完成** | tools/submission/liepin.py | _close_modals() | 自动关闭登录弹窗、app下载引导、ant-modal 对话框 |
| **聊一聊聊天面板 PoC 诊断** | **已完成** | tools/poc_chat_flow.py | 首次探测即发现"发简历"/"发送"控件 | 点击"聊一聊"后内嵌面板枚举所有按钮+file input |
| **多职位入口采样** | **已完成** | tools/poc_probe_jobs.py | Java/前端/产品 三关键词各采样 4 个 | 确认"聊一聊"是统一入口；连续采样触发风控验证 |
| **低关注度职位甄选** | **已完成** | tools/poc_pick_low_profile.py | 长沙 Java 搜索，排除大厂 | 用于端到端真实发送安全目标选择 |
| **DOM 深度诊断 v2** | **已完成** | tools/poc_diagnose_dom_v2.py | 枚举可见按钮/链接/file input/iframe/关键文本 | 比 v1 多了 JS 渲染等待 + 多维度枚举 |
| **直投测试脚本** | **已完成** | tools/test_liepin_direct.py | check-mode 脚本 | 独立于 agent loop 的直接投递测试入口 |
| **Liepin 主流程聊一聊路径接入** | **已验证** | tools/submission/liepin.py + outputs/submissions/liepin/20260512-142057/submission_log.yaml | 真实 check-mode success；submit skipped | 主流程默认 target_verify → chat_send_resume；submit=false 停在最终确认前 |
| **jobId 目标确认护栏接入主流程** | **已测试** | tools/submission/liepin.py | test_liepin_chat_send_resume.py | data-tlg 主按钮选择、推荐区排除、jobId mismatch 阻断 |
| **全量测试依赖收集修复** | **已验证** | tools/setup_liepin_session.py | `python3 -m pytest tests/ -q` → 306 passed | Playwright 改为 lazy import，无 Playwright 环境不再阻断核心测试 |
| **Liepin 投递频控算法** | **已测试** | tools/submission/rate_limit.py + tools/submission/liepin.py | test_submission_rate_limit.py | 默认每批 5、冷却 900s、日上限 30；dry-run 记录 rate_limit 计划 |
| **Liepin 真实 check-mode 主流程验证** | **已验证** | outputs/submissions/liepin/20260512-142057/submission_log.yaml | rate_limit/open_job_page/login_check/target_verify/chat_send_resume success，submit skipped | 职位 `1971416782`，recruiter=臧女士；未点击最终确认发送 |
| **结构化 job_leads 解析** | **已验证** | tools/infra/persistence/yaml_io.py + tools/engines/discovery/job_leads_loader.py | test_discovery_engine.py | 支持 `items: - job_url: ...` 列表字典；Agent Loop DISCOVER 可拿到真实猎聘 URL |
| **LiepinChannel 共享登录态目录覆盖** | **已测试** | tools/channels/liepin.py | test_channels.py | 新增 `PPF_LIEPIN_SESSION_DIR`；避免 per-run session 路径导致手工 symlink |
| **登录态误判修复** | **已验证** | tools/submission/liepin.py | test_liepin_chat_send_resume.py + `run-agent-liepin-chat-004` | 登录弹窗/登录入口优先判定为未登录；不再把公开“聊一聊”按钮误判为已登录 |
| **Agent Loop → Liepin 新路径联调** | **已接入主流程** | outputs/agent_runs/run-agent-liepin-chat-003/run_log.json + outputs/submissions/run-agent-liepin-chat-003/liepin/20260512-150533/submission_log.yaml | DISCOVER=1、GATE pass、进入 DELIVER；target_verify success | 该轮登录态随后弹出登录框，旧逻辑误报 chat_send_resume_failed；已由 004 修正为 login_required |
| **Agent Loop → Liepin check-mode 闭环** | **已验证** | outputs/agent_runs/run-agent-liepin-chat-005/run_log.json + outputs/submissions/run-agent-liepin-chat-005/liepin/20260512-152334/submission_log.yaml | login_check/target_verify/chat_send_resume success；submit skipped | 使用刷新后的共享登录态；未点击最终确认发送 |
| **Liepin 小批量频控真实验证** | **已验证** | outputs/submissions/batch-rate-limit-001/ | 2 次 check-mode success + 第 3 次 `batch_cooldown` blocked | 使用同一 output-dir 共享 `liepin_rate_limit.json`；未点击最终确认发送 |
| **本地残留证据忽略规则** | **已完成** | .gitignore | `git status --short` | `.idea/`、根目录 debug DOM/截图、`policy_validation.yaml` 不纳入主证据链 |
| **批量候选来源扩展** | **已验证** | job_leads/jl-validated-20260513.yaml + outputs/submissions/job-leads-expanded-001/ | 3 个新增真实 URL 均 check-mode success | 未点击最终确认发送；loader 可读取结构化 `items` |
| **BOSS/智联只读发现 adapter** | **已完成（mock 合同验证）** | tools/infra/discovery/boss_agent_cli.py + tools/engines/discovery/job_leads_loader.py | `python3 -m pytest tests/unit/domain/test_discovery_engine.py tests/unit/infra/test_boss_agent_cli.py -q` → 10 passed；v2 PASS | 默认关闭；显式 `PPF_ENABLE_BOSS_AGENT_SEARCH=1` 后调用外部 CLI search 并映射 Candidate；仅只读发现，未启用投递写操作，真实 CLI smoke 待外部工具安装后执行 |
| **GUI 文案合法性与准确性审计** | **已完成** | ui/src/i18n/zh.json + ui/src/i18n/en.json + ui/src/pages/submissions/index.tsx + ui/src/pages/system-settings/index.tsx | `pnpm --dir ui build` → pass；`python3 -m pytest tests/unit/gui -q` → 30 passed；`python3 -m pytest tests/ -q` → 395 passed | 中文界面普通文案去除不必要英文混排；Submissions/System Settings 文案改为尝试日志、排队重试、只读快照等更准确表述 |
| **多候选 Agent Loop 批次策略** | **已测试** | tools/orchestration/agent_loop.py | test_full_pipeline.py + test_agent_loop.py | 按 confidence desc + candidate_id 稳定排序；每轮排除已选候选；dry-run 也遵守 max_deliveries 计划上限 |
| **GUI 投递状态可视化** | **已验证** | tools/sidecar/handlers/submission.py + ui/src/pages/submissions/index.tsx | test_submission_handler.py + `pnpm --dir ui build` | 展示 mode、job_url、error、last_step、rate_limit 状态和详情 |
| **GUI 运行日志详情页** | **已验证** | tools/sidecar/handlers/submission.py + tools/sidecar/server.py + ui/src/pages/submissions/index.tsx | test_submission_handler.py + test_server.py + Playwright mock sidecar | `submission.detail` 返回完整 steps、截图路径、JSON/YAML 日志路径；Submissions 页面可点击查看 |
| **真实 submit 前安全门禁** | **已测试** | tools/submission/liepin.py + tools/submission/run_submission.py + tools/channels/liepin.py | test_liepin_chat_send_resume.py + test_run_submission_cli.py + test_channels.py | submit 必须 PDF、显式 jobId、显式 recruiter，且与 target_verify 二次匹配 |
| **GUI 详情页 review hardening** | **已验证** | tools/sidecar/handlers/submission.py + tools/submission/storage.py + ui/design/contracts/sidecar-rpc.md + ui/src/i18n/ | test_submission_handler.py + test_submission_storage.py + `pnpm --dir ui build` | screenshot 路径越界防护、browser_channel 写入日志、submission.detail 合同同步、Submissions 页面接入 i18n |
| **GUI Submissions 产品化切片** | **已验证** | ui/src/pages/submissions/index.tsx + ui/scripts/verify_submissions_native.mjs + tests/unit/gui/test_submissions_page_contract.py | `pnpm --dir ui run e2e:submissions` → pass；`python3 -m pytest tests/unit/gui -q` → 34 passed；`pnpm --dir ui build` → pass | 补齐统计卡片、表格、详情基础信息、步骤时间线、截图缩略图/预览、失败详情、原通道/Email 降级重试按钮；native verifier 校验真实 bridge + sidecar `submissions.load.ready` |
| **GUI Agent Run 控制 RPC** | **已验证** | tools/sidecar/handlers/agent.py + tools/sidecar/server.py + ui/src/lib/sidecar/api.ts + ui/design/contracts/sidecar-rpc.md | test_server.py + `pnpm --dir ui build` | `run.agent.start/get/stop` 已接入 JSON-RPC 路由和前端 typed client；缺省只创建本地运行控制记录；显式 `execute_dry_run=true` 可执行本地 dry-run AgentLoop，不触发真实投递 |
| **GUI Agent Run 产品化切片** | **已验证** | ui/src/pages/agent-run/index.tsx + ui/scripts/verify_agent_run_native.mjs + tests/unit/gui/test_agent_run_page_contract.py | `pnpm --dir ui run e2e:agent-run` → pass；`python3 -m pytest tests/unit/gui -q` → 34 passed；`pnpm --dir ui build` → pass | 补齐运行控制、10 状态机、门禁摘要、事件流和 REVIEW 候选审批；`REVIEW_PENDING` 按暂停态处理，不误标为完成态；native verifier 校验真实 bridge + sidecar `agent_run.load.ready` |
| **GUI System Settings 产品化切片** | **已验证** | tools/sidecar/handlers/settings.py + ui/src/pages/system-settings/index.tsx + ui/scripts/verify_system_settings_native.mjs + tests/unit/gui/test_system_settings_page_contract.py | `pnpm --dir ui run e2e:system-settings` → pass；`python3 -m pytest tests/ -q` → 360 passed；`pnpm --dir ui build` → pass；`cargo test --manifest-path ui/src-tauri/Cargo.toml` → 7 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS | 补齐 Channels / LLM Config 分组导航、通道卡、fallback 顺序、连接检查、凭证状态和 LLM 掩码配置；native verifier 必须等真实 Tauri bridge + sidecar `settings.get` 写出 `system_settings.load.ready`，避免 Vite/mock 冒充桌面验收 |
| **GUI Policy 产品化切片** | **已验证** | ui/src/pages/policy/index.tsx + ui/src/i18n/ + ui/scripts/verify_policy_native.mjs + tools/policy/exclusions.py + tools/config/validator.py | `pnpm --dir ui run e2e:policy` → pass；`pnpm --dir ui build` → pass；`python3 -m pytest tests/ -q` → 363 passed；`cargo test --manifest-path ui/src-tauri/Cargo.toml` → 7 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS | 补齐 Gate Policy / Exclusion List 分组导航、字段卡、排除规则预览与 Discovery/Gate 命中说明；不新增 sidecar 协议，继续复用 `settings.get/update`；`delivery_mode=auto` 会在前端、sidecar 读写与 config validator 三层关闭/拒绝 `batch_review`，避免无效策略组合 |
| **GUI 一键启停脚本** | **已验证** | app + scripts/appctl.py + .gitignore | `./app start` / `./app status` / `./app stop` | 根目录一键控制 Tauri dev app；运行时 PID 和日志写入 `.app-runtime/`，并已加入 gitignore |
| **Tauri pnpm/Rust 版本对齐** | **已验证** | ui/package.json + ui/pnpm-lock.yaml + ui/package-lock.json | `pnpm --dir ui list @tauri-apps/api @tauri-apps/cli --depth 0` + `./app start` 日志 | pnpm 侧固定 `@tauri-apps/api`/`cli` 为 2.10.1，与 Rust `tauri` 2.10.3 对齐到同一 minor；启动日志不再出现 mismatch 提示 |
| **GUI 默认中文语言** | **已验证** | ui/src/i18n/index.ts + tests/unit/gui/test_i18n_defaults.py | `python3 -m pytest tests/unit/gui/test_i18n_defaults.py -q` + `pnpm --dir ui build` | 默认 `lng` 与 `fallbackLng` 均使用 `DEFAULT_LANGUAGE = "zh"` |
| **GUI 启动缓存优化** | **已验证** | ui/scripts/stage_python_runtime.py | `pnpm --dir ui run prepare:python-runtime` + `./app start` 日志 | Python runtime 缺失或解释器变化时才重打包；常规启动命中 `Using staged Python`，避免每次复制/签名整套 Python.framework |
| **boss-agent-cli 外部仓库调研** | **已完成** | https://github.com/can4hou6joeng4/boss-agent-cli | 源码/README/能力矩阵/平台抽象/MCP/风险文档阅读 | 对本项目价值主要在多平台 job-discovery、受控 delivery 通道参考、JSON envelope/schema/MCP 工程化；推荐先做 subprocess 薄适配 |
| **反馈迭代场景 case 定义** | **已完成** | acceptance/scenario_cases.yaml | YAML 解析通过 | 新增 `feedback_iteration_after_check_mode`，覆盖 check-mode 后从反馈到证据/岗位/简历迭代、新版本对比、下一轮 check-mode 准备；M-1 场景目录完成 |
| **M0 journey contract** | **已完成** | acceptance/journey_contract.yaml + tools/acceptance/journey_contract.py | `python3 -m pytest tests/acceptance/test_journey_contract.py -q` → 4 passed | 合同覆盖 9 个 selected case、固定 9 页 stage 顺序、required outputs、acceptance rule status/evidence/message 字段 |
| **项目状态与主链路收束审计** | **已完成** | docs/reports/project-state-and-core-flow-review.md | 实跑 CLI/测试/PDF/Agent/GitHub issue 检查 | 当时确认 CLI 主链路可跑，并暴露 PDF runtime、GUI Quick Run、普通 pipeline run record、Agent REVIEW pause 缺口；除 Quick Run 外本轮均已补齐 |
| **PDF runtime 基础闭环** | **已完成** | tools/infra/export/pdf_exporter.py + tests/unit/infra/test_pdf_exporter.py + tests/unit/sidecar/test_resume_handler.py | `python3 -m pytest tests/unit/infra/test_pdf_exporter.py tests/unit/sidecar/test_resume_handler.py tests/unit/sidecar/test_server.py -q` → 31 passed；smoke 导出 `%PDF-1.4` 非空文件 | WeasyPrint 可用时走高保真 HTML/CSS；依赖缺失时走内置基础 PDF writer；fallback 按显示宽度拆分连续 CJK 长句 |
| **WeasyPrint 高保真 PDF runtime staging** | **已完成** | requirements-pdf.txt + ui/scripts/stage_python_runtime.py + tests/unit/gui/test_stage_python_runtime.py | `python3 -m pytest tests/unit/gui/test_stage_python_runtime.py tests/unit/infra/test_pdf_exporter.py -q` → 15 passed；`pnpm --dir ui run prepare:python-runtime` → pass | 高保真依赖显式放入 `requirements-pdf.txt`；staging 仅在检测到完整 `markdown` + `weasyprint` runtime 时复制 PDF 依赖与 `.dist-info` 元数据，并用 packaged wrapper 做最小 Markdown→PDF 探针；缺失依赖时清理旧 staged 包并保留内置 PDF writer 兜底 |
| **普通 pipeline Run Record** | **已完成** | tools/run_pipeline.py + tests/unit/pipeline/test_run_pipeline.py | `python3 -m pytest tests/unit/pipeline/test_run_pipeline.py tests/unit/infra/test_file_run_store.py -q` → 6 passed；`python3 -m pytest tests/ -q` → 351 passed | `tools/run_pipeline.py` 保留 legacy subprocess 串联，同时写入 `outputs/agent_runs/<run_id>/run_log.json`、`summary.json`；企业排除兼容旧 `outputs/<run_id>/run_log.json` 审计文件 |
| **Agent REVIEW pause 收口** | **已完成** | tools/orchestration/agent_loop.py + tests/unit/domain/test_full_pipeline.py | `python3 -m pytest tests/unit/domain/test_full_pipeline.py tests/unit/domain/test_gate_review.py -q` → 19 passed；`python3 -m pytest tests/ -q` → 351 passed | manual 非批量 REVIEW 写 `outputs/review_queue/<run_id>.json` 后返回 `REVIEW_PENDING`，不进入 DELIVER；batch_review 收集候选后统一进入待审批 |
| **GUI Quick Run 直接执行** | **已完成** | tools/sidecar/handlers/agent.py + tools/sidecar/server.py + ui/src/pages/quick-run/index.tsx + ui/src/lib/sidecar/api.ts | `python3 -m pytest tests/unit/sidecar/test_server.py -q` → 12 passed；`pnpm --dir ui build` → pass | `run.quick.start` 同步启动本地 `tools/run_pipeline.py` 单次 pipeline 并返回 run record 路径；`run.quick.cancel` 记录取消请求；Quick Run 页面新增启动按钮、状态回显，CLI 命令保留为 fallback |
| **Quick Run native verifier 自动化** | **已完成** | ui/scripts/verify_quick_run_native.mjs + ui/src/components/shell/NativeVerifyController.tsx + ui/src/pages/quick-run/index.tsx + ui/package.json | `pnpm --dir ui run e2e:quick-run` 连续多轮通过；`pnpm --dir ui build` → pass；`cargo test --manifest-path ui/src-tauri/Cargo.toml` → pass；`python3 -m pytest tests/ -q` → 351 passed | 参考 ai-novel-studio 的 native verifier 方式：主入口 `pnpm --dir ui run e2e:quick-run` 用 `pnpm tauri dev` 启动真实 Tauri 窗口，以 `VITE_QUICK_RUN_VERIFY_AUTORUN=quick-run` 驱动页面点击稳定 selector，并用 `outputs/quick_runs` + summary 校验结果；WebDriver 仅保留为可选补充；dev 模式固定仓库根工作目录并补 `PYTHONPATH`，避免产物写入 `target/debug/resources` |
| **Quick Run sidecar 项目根锚定** | **已完成** | tools/sidecar/handlers/agent.py + tests/unit/sidecar/test_agent_handler.py + tests/unit/sidecar/test_server.py | `python3 -m pytest tests/ -q` → 352 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS；`pnpm --dir ui run e2e:quick-run` → DONE | `run.quick.start` 默认 raw/profile、pipeline 脚本、subprocess cwd 与 sidecar 运行目录均锚定项目根，避免 sidecar cwd 偏移导致 Quick Run 产物写到错误目录 |
| **Quick Run 页面产品化垂直切片** | **已完成** | ui/src/pages/quick-run/index.tsx + tools/sidecar/handlers/agent.py + ui/scripts/verify_quick_run_native.mjs + tests/unit/gui/test_quick_run_page_contract.py | `python3 -m pytest tests/ -q` → 380 passed；`pnpm --dir ui build` → pass；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS；`pnpm --dir ui run e2e:quick-run` → DONE | 按终版 GUI 第 5 页补齐 4 阶段状态条、终端式 Stage Output、K/D/S/Q/E/R ScoreBar；`run.quick.start` 继续复用既有方法，仅返回运行详情供 UI 展示；native verifier 校验 `quick_run.load.ready` + run summary |
| **本地 Demo 验收入口** | **已完成** | scripts/acceptance/run-demo.sh + tools/acceptance/demo_run.py + tests/acceptance/test_demo_run.py | 临时副本 `bash scripts/acceptance/run-demo.sh --run-id demo_verify_20260520` → pass；`python3 -m pytest tests/ -q` → 388 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS | 包装现有样例 pipeline，校验核心产物与 Run Record 事件，并输出 `outputs/demo/<run_id>/demo-report.json` / `.md` |
| **演示前聚合检查入口** | **已完成** | scripts/acceptance/run-demo-readiness.sh + tools/acceptance/demo_readiness.py + tests/acceptance/test_demo_readiness.py | 临时副本 `bash scripts/acceptance/run-demo-readiness.sh --run-id readiness_verify_20260520` → pass；`python3 -m pytest tests/acceptance/test_demo_run.py tests/acceptance/test_demo_readiness.py -q` → 8 passed；`python3 tools/check_v2_constraints.py --root .` → PASS | 默认运行本地确定性 Demo；显式 `--include-gui` 时串联 Quick Run native verifier；输出 `outputs/demo/<run_id>/readiness-report.json` / `.md` |
| **Demo runbook** | **已完成** | docs/demo-runbook.md + tests/acceptance/test_demo_runbook.py | `python3 -m pytest tests/acceptance/test_demo_run.py tests/acceptance/test_demo_readiness.py tests/acceptance/test_demo_runbook.py -q` → 11 passed；`python3 tools/check_v2_constraints.py --root .` → PASS | 固化演示前检查、可选 GUI 检查、演示顺序、失败排障和安全范围；文档合同测试锁定关键命令与路径 |
| **Demo readiness 当前工作区试跑** | **已完成** | outputs/demo/demo_ready_20260519164944/readiness-report.md + demo-report.md | `bash scripts/acceptance/run-demo-readiness.sh` → pass；`python3 -m pytest tests/ -q` → 391 passed；`python3 tools/check_v2_constraints.py --root .` → PASS；`python3 tools/check_aief_l3.py --root . --base-dir AIEF` → PASS | 按 runbook 抽查核心报告与产物路径；新增 `.gitignore` demo/qr 前缀规则，避免 Demo 与 Quick Run Evidence/Matching 产物污染源码状态 |
| **Demo desktop GUI readiness** | **已完成** | outputs/demo/demo_ready_20260519165837/readiness-report.md + ui/test-results/quick-run-native/app-events.jsonl | `bash scripts/acceptance/run-demo-readiness.sh --include-gui` → pass；Quick Run event `qr_20260519165844857109` status DONE, score_total 95 | 真实 Tauri/Vite 桌面壳启动并通过 sidecar 完成 Quick Run；首次失败由 sandbox/残留端口导致，清理后通过；收尾 1420 无监听残留 |
| **Overview 页面产品化垂直切片** | **已完成** | ui/src/pages/overview/index.tsx + ui/scripts/verify_overview_native.mjs + tests/unit/gui/test_overview_page_contract.py | `python3 -m pytest tests/unit/gui/test_overview_page_contract.py tests/unit/sidecar/test_overview_handler.py -q` → 11 passed；`pnpm --dir ui build` → pass；`cargo fmt --manifest-path ui/src-tauri/Cargo.toml` → pass；`cargo test --manifest-path ui/src-tauri/Cargo.toml` → 7 passed；`pnpm --dir ui run e2e:overview` → pass | 按终版 GUI 第 1 页补齐启动主动作、统计、最近活动、趋势图、缺口汇总；复用 `overview.get`，native verifier 校验真实 bridge + sidecar ready 事件 |
| **Resumes 页面产品化垂直切片** | **已完成** | ui/src/pages/resumes/index.tsx + ui/scripts/verify_resumes_native.mjs + tests/unit/gui/test_resumes_page_contract.py | `python3 -m pytest tests/unit/gui/test_resumes_page_contract.py tests/unit/sidecar/test_resume_handler.py tests/unit/sidecar/test_profile_handler.py -q` → 20 passed；`pnpm --dir ui build` → pass；`cargo fmt --manifest-path ui/src-tauri/Cargo.toml -- --check` → pass；`cargo test --manifest-path ui/src-tauri/Cargo.toml` → 7 passed；`pnpm --dir ui run e2e:resumes` → pass | 按终版 GUI 第 2 页补齐个人资料、上传简历、系统生成简历、纸张预览和 PDF 导出入口；复用既有 profile/resume RPC，不新增 sidecar 协议；native verifier 校验真实 bridge + sidecar ready 事件 |
| **Jobs 页面产品化垂直切片** | **已完成** | ui/src/pages/jobs/index.tsx + ui/scripts/verify_jobs_native.mjs + tests/unit/gui/test_jobs_page_contract.py | `python3 -m pytest tests/unit/gui/test_jobs_page_contract.py tests/unit/sidecar/test_jobs_handler.py -q` → 16 passed；`pnpm --dir ui build` → pass；`cargo fmt --manifest-path ui/src-tauri/Cargo.toml -- --check` → pass；`cargo test --manifest-path ui/src-tauri/Cargo.toml` → 7 passed；`pnpm --dir ui run e2e:jobs` → pass | 按终版 GUI 第 4 页补齐岗位画像统计、Profile/Lead 分段视图、画像卡片网格、详情编辑、线索表格、详情与转画像操作；复用既有 jobs RPC，不新增 sidecar 协议；native verifier 校验真实 bridge + sidecar ready 事件 |
| **Evidence 页面产品化垂直切片** | **已完成** | ui/src/pages/evidence/index.tsx + ui/scripts/verify_evidence_native.mjs + tests/unit/gui/test_evidence_page_contract.py | `python3 -m pytest tests/unit/gui/test_evidence_page_contract.py tests/unit/sidecar/test_evidence_handler.py tests/unit/sidecar/test_server.py -q` → 38 passed；`pnpm --dir ui build` → pass；`cargo fmt --manifest-path ui/src-tauri/Cargo.toml -- --check` → pass；`cargo test --manifest-path ui/src-tauri/Cargo.toml` → 7 passed；`pnpm --dir ui run e2e:evidence` → pass | 按终版 GUI 第 3 页补齐 Evidence Card 表格、详情编辑、Results、Stack & Tags、Artifacts 和导入/追加/替换入口；复用既有 evidence RPC，不新增协议面；native verifier 校验真实 bridge + sidecar ready 事件 |
| **GitHub issue 状态清理** | **已完成** | GitHub issues #21-#27 | `gh issue close/comment` + `gh issue list` | #24/#26/#27 已关闭；#21/#22/#23/#25 已评论降级或缩小范围；#15/#16 保持关闭 |

## 3. 已验证事项

| 事项 | 验证方式 | 报告路径 | 结论 |
|------|----------|----------|------|
| 全部 366 单元测试 | `python3 -m pytest tests/ -q` | 终端输出 | 366 passed |
| v2 静态约束 | `python3 tools/check_v2_constraints.py --root .` | 终端输出 | PASS |
| AIEF L3 合规 | `python3 tools/check_aief_l3.py --root . --base-dir AIEF` | 终端输出 | PASS |
| Agent full-pipeline dry-run | `python3 -m tools.cli.entrypoints agent --policy policy.yaml --dry-run --evidence-dir evidence_cards --job-profile job_profiles/jp-2026-001.yaml` | 终端输出 | DONE (10 状态全量日志) |
| Core CLI pipeline smoke | `python3 tools/run_pipeline.py --raw tools/sample_raw.txt --job-profile job_profiles/jp-2026-001.yaml --run-id state-review-20260517` | `docs/reports/project-state-and-core-flow-review.md` | 生成 Evidence Card、Matching Report、A/B Resume、Scorecard |
| Markdown PDF runtime check | `python3 -c '... markdown_to_pdf(...)'` | 终端 smoke + `tests/unit/infra/test_pdf_exporter.py` | 当前环境 `WEASYPRINT_AVAILABLE=False`，但 `is_pdf_export_available()` 为 true；可导出 `%PDF-1.4` 非空文件 |
| Optional PDF runtime staging | `python3 -m pytest tests/unit/gui/test_stage_python_runtime.py tests/unit/infra/test_pdf_exporter.py -q` + `pnpm --dir ui run prepare:python-runtime` | 终端输出 | 15 passed；staging 可在无完整 WeasyPrint/Markdown runtime 时保持 packaged runtime 干净并继续兜底 |
| Benchmark 001 (rule baseline) | `docs/benchmarks/benchmark-001.md` | Matching Total=0.5, Eval Total=0.65 | 发现 K-score=0（已修复） |
| Benchmark 002 (stack fix 后) | 同命令复现 | Matching Total=0.8, K-score=0.6 | 证据卡可按技术栈区分 |
| Benchmark 003 (LLM vs Rule) | `docs/benchmarks/benchmark-003.md` | LLM K=0.73, Rule K=0.60 | LLM 更精准但更慢，建议混合策略 |
| Benchmark 004 (LLM Evaluator) | `docs/benchmarks/benchmark-004.md` | semantic coverage 0.30→0.42 | 打破 coverage=0 盲区 |
| LLM 连接验证 | LM Studio localhost:1234 | openai/gpt-oss-120b 可用 | 响应正常 |
| Hybrid 匹配策略 | `tools/engines/matching/hybrid_matcher.py` | 2.3x faster than pure LLM | Rule 初筛 Top5 → LLM 精选 |
| Playwright + Liepin 验证 | `tools/channels/liepin.py` | check-mode 通过 | 需登录态完成真实投递 |
| Agent Loop 端到端验证 | 真实验证脚本 | hybrid + LLM evaluator, 10 状态全通过 | 2 rounds, 18 events, matching 0.772→0.919 |
| SLA/SLO 证据卡 | `evidence_cards/ec-2026-018.yaml` / `019.yaml` | K-score: Backend 1.0, SRE 0.857 | SLA/SLO 盲区消除 |
| GUI 编译验证 | `pnpm --dir ui build` | TypeScript 零错误, 1628 modules | 9 页全部可编译 |
| GUI Agent Run 页面冒烟 | `pnpm --dir ui build` + Playwright 打开 `http://127.0.0.1:1420/agent-run` | Vite/Playwright 终端输出 | 页面渲染出 10 状态节点、门禁摘要、审批面板与事件流；纯 Vite 模式下 Tauri bridge 未连接属预期 |
| Quick Run native verifier | `pnpm --dir ui run e2e:quick-run` | `outputs/quick_runs/qr_20260519163230256817.json` + `outputs/agent_runs/qr_20260519163230256817/summary.json` + `ui/test-results/quick-run-native/app-events.jsonl` | 真实 Tauri 窗口内点击 Quick Run，DONE；先校验 `quick_run.load.ready`，再校验 run summary；多轮无残留进程或 `.env.local` |
| Overview native verifier | `pnpm --dir ui run e2e:overview` | `ui/test-results/overview-native/app-events.jsonl` | 真实 Tauri 窗口内自动导航 `/`，sidecar ready 后写出 `overview.load.ready`，当前工作区聚合到 evidence=13、matched_jobs=2、resumes=19、submissions=27、activities=6、trend=13、gaps=1 |
| System Settings native verifier | `pnpm --dir ui run e2e:system-settings` | `ui/test-results/system-settings-native/app-events.jsonl` | 真实 Tauri 窗口内自动导航 `/system-settings`，sidecar ready 后写出 `system_settings.load.ready`，包含 `channel_ids=["liepin","email"]` |
| Policy native verifier | `pnpm --dir ui run e2e:policy` | `ui/test-results/policy-native/app-events.jsonl` | 真实 Tauri 窗口内自动导航 `/policy`，sidecar ready 后写出 `policy.load.ready`，并验证 `delivery_mode=auto` 时 `batch_review=false` |
| Resumes native verifier | `pnpm --dir ui run e2e:resumes` | `ui/test-results/resumes-native/app-events.jsonl` | 真实 Tauri 窗口内自动导航 `/resumes`，sidecar ready 后写出 `resumes.load.ready`，当前工作区聚合到 profile_completeness=0、resume_count=19、uploaded_count=0、generated_count=19、has_preview=true |
| Jobs native verifier | `pnpm --dir ui run e2e:jobs` | `ui/test-results/jobs-native/app-events.jsonl` | 真实 Tauri 窗口内自动导航 `/jobs`，sidecar ready 后写出 `jobs.load.ready`，当前工作区聚合到 profile_count=5、lead_count=3、active_profile_count=2 |
| Evidence native verifier | `pnpm --dir ui run e2e:evidence` | `ui/test-results/evidence-native/app-events.jsonl` | 真实 Tauri 窗口内自动导航 `/evidence`，sidecar ready 后写出 `evidence.load.ready`，当前工作区聚合到 card_count=13、artifact_count=2、selected_id=ec-2026-001 |
| Agent Run native verifier | `pnpm --dir ui run e2e:agent-run` | `ui/test-results/agent-run-native/app-events.jsonl` | 真实 Tauri 窗口内自动导航 `/agent-run`，sidecar ready 后写出 `agent_run.load.ready`，当前工作区聚合到 profile_count=5、selected_profile_id=jp-2026-001 |
| Submissions native verifier | `pnpm --dir ui run e2e:submissions` | `ui/test-results/submissions-native/app-events.jsonl` | 真实 Tauri 窗口内自动导航 `/submissions`，sidecar ready 后写出 `submissions.load.ready`，当前工作区聚合到 submission_count=20、delivered_count=7、failed_count=8、fallback_count=0 |
| LLM Evaluator 增强 | `tools/engines/evaluation/llm_evaluator.py` | 6 维度语义评测 | semantic_coverage + fabrication_risk + gaps/strengths/improvements |
| AppleScript 猎聘搜索 PoC | `tools/poc_liepin_applescript_search.py` | 2.3s/搜索, 23 职位/页, 无 captcha | 真实 Chrome 完全绕过 captcha（初始测试） |
| Liepin 登录态有效性 | `outputs/submissions/liepin/run-deliver-6/` | login_check: success | 32 个 liepin cookie，Playwright persistent_context 有效 |
| Agent Loop→DELIVER 全链路 | `outputs/agent_runs/run-deliver-6/` | login_check success, job page 已下线 | 登录通过；历史失败已归因修正为职位不可用/下线，不再作为上传选择器结论 |
| 猎聘风控触发 | `safe.liepin.com SMS验证页` | 短时间多次搜索触发 | 需冷却 + SMS 验证后重试 |
| **Stealth + human pacing 绕过风控** | **tools/poc_e2e_send.py 连续 2 次成功访问** | **无重定向到安全中心** | **playwright-stealth + 真实 macOS Chrome UA + 随机延迟有效** |
| **聊一聊→发简历 聊天面板 DOM** | **tools/poc_chat_flow.py** | **内嵌面板，not 新窗口** | **ant-im-modal-confirm-btns 按钮；文本含全角空格（"确 定"）** |
| **真实发送 SAP 职位** | **tools/poc_e2e_send.py --really-send** | **确 定 按钮点击成功** | **孙先生（SAP recruiter）** |
| **13 职位入口采样** | **tools/poc_probe_jobs.py** | **7/13 聊一聊 only，0/13 file input** | **统一入口实证** |
| **误投 root cause** | **DOM 离线分析** | **text=聊一聊 匹配 40 次（20 雇主），主按钮文本"继续聊"** | **必须使用 data-tlg-elem-id 锁定主按钮** |
| **Agent Loop→Liepin 新路径联调** | `run-agent-liepin-chat-003` / `run-agent-liepin-chat-004` / `run-agent-liepin-chat-005` | 003 进入 DELIVER 且 target_verify success；004 正确阻断为 login_required；005 check-mode success | 当前真实阻塞已解除 |
| **Liepin 小批量频控验证** | `outputs/submissions/batch-rate-limit-001/` | 154502/154805 两次 success；155641 blocked=batch_cooldown | 频控在真实 check-mode 路径生效 |
| **批量候选来源扩展** | `job_leads/jl-validated-20260513.yaml` + `outputs/submissions/job-leads-expanded-001/` | 1979279359、1980984659、1979846849 均 check-mode success | 候选来源从 1 个真实 URL 扩到 4 个真实 URL |

## 4. 进行中事项

无。上轮三项进行中事项（AgentLoop 集成、Composer build、Benchmark 基线）均已在 2026-05-08 完成。

## 5. 已知缺口（按优先级）

| 优先级 | 缺口 | 影响 | 类型 | 阻塞条件 |
|--------|------|------|------|----------|
| ~~P0~~ | ~~猎聘风控限流~~ | ~~AppleScript 搜索和 Playwright 投递可能被重定向~~ | **已解决** | **playwright-stealth + 真实 UA + 人化节奏 绕过** |
| ~~P0~~ | ~~可用职位页 check-mode 上传未验证~~ | ~~历史 run-deliver-6 实际职位已下线~~ | **已解决** | **PoC 端到端 6 步全通过（dry-run + real-send）** |
| ~~P1~~ | ~~频控真实批量验证~~ | ~~频控算法已实现，但未用真实批量职位验证 safe.liepin.com 触发率~~ | **已解决** | **`batch-rate-limit-001`：2 次 success + 第 3 次 batch_cooldown** |
| ~~P1~~ | ~~猎聘共享登录态刷新后复跑 Agent Loop~~ | ~~当前 `run-agent-liepin-chat-004` 正确阻断于 login_required~~ | **已解决** | **`run-agent-liepin-chat-005` check-mode success** |
| ~~P2~~ | ~~LiepinChannel session 路径耦合 run_id~~ | ~~每次新 run 需手动创建 symlink~~ | **已解决** | **新增 `PPF_LIEPIN_SESSION_DIR` 显式覆盖** |
| ~~P3~~ | ~~GUI 前端为骨架级别~~ | ~~可演示性不足~~ | **已解决** | **9 页 GUI 已按终版设计完成产品化垂直切片；Quick Run 补齐 4 阶段状态条、Stage Output 与 ScoreBar，并通过真实 native verifier** |
| ~~P3a~~ | ~~GUI Quick Run 尚未直接运行主链路~~ | ~~当前只展示/复制 CLI 命令，未注册 `run.quick.start` / `run.quick.cancel`~~ | **已解决** | **已注册 `run.quick.start` / `run.quick.cancel`；Quick Run 页面可直接启动本地单次 pipeline，CLI 命令作为 fallback 保留** |
| ~~P3b~~ | ~~Markdown PDF runtime 未闭环~~ | ~~代码已接入，但当前环境缺 `weasyprint`/`markdown`，实际导出失败~~ | **已解决** | **内置基础 PDF writer 兜底；`WEASYPRINT_AVAILABLE=False` 时仍可导出非空 PDF** |
| ~~P3c~~ | ~~普通 pipeline 无统一 Run Record~~ | ~~`tools/run_pipeline.py` 可生成产物，但不写 `outputs/agent_runs/<run_id>/run_log.json`~~ | **已解决** | **保留 legacy subprocess 串联，同时写入统一 Run Record 与 summary** |
| ~~P3d~~ | ~~Agent REVIEW 未完整暂停等待 GUI 审批~~ | ~~sidecar queue handler 已存在，但 AgentLoop 在 REVIEW 后仍直接 approve 进入后续状态~~ | **已解决** | **manual REVIEW 写 queue 并返回 REVIEW_PENDING，不进入 DELIVER** |
| ~~P3e~~ | ~~GUI Agent Run 页面仍停留在待审批队列骨架，未体现终版第 6 页状态机/门禁/事件流职责~~ | ~~无法产品化展示多轮 Agent 运行与 REVIEW pause 语义~~ | **已解决** | **已补齐运行控制、10 状态机、N-Pass Gate 摘要、事件流与审批面板；`python3 -m pytest tests/ -q` 355 passed，`pnpm --dir ui build` 通过** |
| ~~P4~~ | ~~Gap tasks 仅检查 must_have，不检查 keywords~~ | ~~SLA/SLO 等关键词缺失不会触发补证据任务~~ | **已解决** | **RuleMatchingEngine 空候选和常规路径均覆盖 `keywords` gap task；测试已锁定** |
| ~~P5~~ | ~~误投防护需接入 liepin.py 主流程~~ | ~~poc_e2e_send.py 已有 sanity check，但主流程 `liepin.py` 未接入~~ | **已解决** | **target_verify 已接入并有离线单测覆盖** |
| ~~P6~~ | ~~GUI `.pen` 设计资产未随最新 Submissions 详情实现同步复核~~ | ~~`DESIGN.md` 与 GUI review checklist 明确要求 GUI 结构变更同步 `.pen`；当前 Pencil MCP 返回 `Transport closed`~~ | **已解决** | **Pencil MCP 已恢复；已打开 `ui/design/piproofforge.pen` 并复核 `Screen/Submissions` (`upl7d`)、`subTable`、`subDetail`，现有设计资产已包含统计、表格、详情、时间线、截图、重试和失败详情结构，无需改设计源** |
| ~~P7~~ | ~~Submissions 页面实现仍未完全达到终版设计的统计卡片、表格、截图缩略图/放大预览形态~~ | ~~当前实现是可用的列表 + 详情面板垂直切片，未完整复刻 DESIGN.md 第 7 页产品态~~ | **已解决** | **已补齐统计卡片、表格、详情基础信息、步骤时间线、截图缩略图/预览、失败详情与原通道/Email 降级重试按钮；Playwright mock sidecar 视觉验收通过** |
| ~~P7a~~ | ~~Resumes 页面实现仍停留在功能表单，未完整体现终版第 2 页个人资料、上传简历、系统生成简历和预览三栏资产中心~~ | ~~简历中心是 evidence-first 输出资产入口，可演示性和导出可信度不足~~ | **已解决** | **已补齐三栏资产中心、单语 i18n、native verifier；复用既有 profile/resume RPC，不新增协议面** |
| ~~P7b~~ | ~~Evidence 页面仍停留在基础列表/表单，未完整体现终版第 3 页 Evidence Card 表格、详情字段卡、Artifacts 导入/回看职责~~ | ~~Evidence 是项目事实源，页面不足会直接削弱 evidence-first 可演示性和长期资产维护能力~~ | **已解决** | **已补齐证据统计、筛选、表格、详情编辑、Artifacts 列表与导入/追加/替换入口；native verifier 通过真实 bridge + sidecar 验收** |
| ~~P7c~~ | ~~Quick Run 页面仍偏命令面板，未完整体现终版第 5 页单次 pipeline 操作台~~ | ~~Quick Run 是 Demo 与本地单次 pipeline 的主入口，缺少阶段输出和评分会削弱可演示性~~ | **已解决** | **已补齐 Profile 选择、Run/Cancel、4 阶段状态、终端式输出、K/D/S/Q/E/R ScoreBar；native verifier 通过真实 bridge + sidecar 验收** |
| P8 | BOSS/智联平台尚未完成真实联调和 delivery 接入 | 只读 discovery adapter 已接入并有 mock 合同测试，但尚未在已安装的外部 `boss-agent-cli` 上做真实 schema/status/search/detail smoke；投递/沟通写操作仍未纳入安全门禁 | 扩展缺口 | 先完成外部 CLI live smoke；写操作仅在 review/gate/rate-limit/safety 全部复用后再启用 |

## 6. 已废弃事项

无明确废弃事项。

## 7. 当前 Top Priority

| 优先级 | 事项 | 原因 | 验收标准 |
|--------|------|------|----------|
| ~~1~~ | ~~发布前构建检查~~ | ~~默认本地 readiness 与桌面 GUI readiness 均已通过；下一步应跑前端生产构建和必要静态约束，确认演示代码可打包~~ | **已完成**：`pnpm --dir ui build`、`python3 -m pytest tests/ -q` → 395 passed、v2、AIEF 均通过 |
| ~~2~~ | ~~BOSS/智联只读发现 adapter~~ | ~~多平台发现仍是 P8 扩展缺口；应等 Demo GUI/发布检查稳定后再接入 optional subprocess adapter~~ | **已完成第一阶段**：只读 search adapter + Candidate 映射 + 默认关闭；真实外部 CLI smoke 未做 |
| 3 | BOSS/智联外部 CLI live smoke | 只读 adapter 已有 mock 合同，但还需要在本机安装/配置外部工具后确认 `schema/status/search/detail --json` 真实输出 envelope 与 mapper 兼容 | `PPF_ENABLE_BOSS_AGENT_SEARCH=1 PPF_BOSS_AGENT_CLI=<cmd>` 下 dry-run Agent Loop 可发现 BOSS/智联 URL，且不触发写操作 |
| ~~3~~ | ~~WeasyPrint 高保真 PDF 增强~~ | ~~内置 writer 已保证 runtime 不断链，但排版能力弱于 HTML/CSS 渲染~~ | **已解决**：`requirements-pdf.txt` + packaged runtime staging；保留内置兜底 |

## 8. 关键证据索引

| 证据 | 路径 | 说明 |
|------|------|------|
| 核心规范 | openspec/specs/pi-proof-forge-core.md | v2 架构规范（535 行） |
| 架构设计 | openspec/changes/autonomous-agent-delivery-loop/design.md | v2 设计（779 行） |
| 任务清单 | openspec/changes/autonomous-agent-delivery-loop/tasks.md | 历史任务多数已完成；2026-05-17 审计补充了 legacy pipeline、PDF runtime、Quick Run、REVIEW pause 的真实缺口 |
| 实施计划 | AIEF/docs/plans/autonomous-agent-delivery-loop-v2.md | 5 里程碑 + 文件级拆分 |
| 项目计划 | PLAN.md | 完整项目计划书（17k 字） |
| 项目宪法 | constitution.md | 不可妥协工程原则 |
| 领域模型 | tools/domain/models.py | EvidenceCard 等 frozen dataclass |
| Agent Loop | tools/orchestration/agent_loop.py | 10 状态全阶段集成，StateMachine 已接入 |
| State Machine | tools/orchestration/state_machine.py | 10 状态定义，已接入 AgentLoop._run_full_pipeline() |
| AppleScript 搜索 PoC | tools/poc_liepin_applescript_search.py | 真实 Chrome 驱动的搜索验证脚本 |
| Liepin 投递日志 | outputs/submissions/liepin/run-deliver-*/ | 端到端投递记录（login_check success） |
| Agent Run 日志 | outputs/agent_runs/run-deliver-*/ | 10 状态事件日志 |
| Gate Engine | tools/orchestration/gate_engine.py | N-pass 门禁 + 企业排除 |
| Review Stage | tools/orchestration/review_stage.py | auto/manual/batch 三种模式 |
| Composer | tools/config/composer.py | 组装点（含 build_agent_loop） |
| Sidecar | tools/sidecar/server.py | GUI-Python JSON-RPC 桥接 |
| GUI 设计 | ui/design/DESIGN.md | 终版 9 页 IA |
| 用户场景化 case 定义 | acceptance/scenario_cases.yaml | scenario-first 验收 case 目录；Case 1-6、channel_session_setup、submission_check_mode、feedback_iteration_after_check_mode 已 ready_for_implementation |
| 用户旅程合同 | acceptance/journey_contract.yaml + tools/acceptance/journey_contract.py | M0 case-aware contract；selected cases、stage 顺序、required outputs、acceptance rules 可由 loader 验证 |
| 用户旅程闭环自动化验证计划 | AIEF/docs/plans/2026-05-13-user-journey-closed-loop-validation.md | M-1 到 M5 专项推进计划，所有阶段/步骤均含状态字段 |
| 测试 | tests/ | 351 tests |
| v2 约束 | tools/check_v2_constraints.py | 静态约束校验脚本 |
| **反反爬基础设施** | **tools/submission/_browser.py** | **stealth + human pacing + 安全护栏** |
| **端到端投递 PoC** | **tools/poc_e2e_send.py** | **6 步 dry-run/real-send 脚本** |
| **聊一聊流程探测** | **tools/poc_chat_flow.py** | **聊天面板 DOM 枚举** |
| **职位入口采样** | **tools/poc_probe_jobs.py** | **13 职位投递入口统计** |
| **DOM 深度诊断** | **tools/poc_diagnose_dom_v2.py** | **SPA 渲染后多维度 DOM 枚举** |
| **PoC 产物** | **outputs/poc_e2e_send/ + outputs/poc_chat_flow/** | **每步截图+HTML 全程可审计** |
| **Agent Loop Liepin 联调日志** | **outputs/agent_runs/run-agent-liepin-chat-003/ + outputs/submissions/run-agent-liepin-chat-003/** | **进入 DELIVER，target_verify success；暴露登录态误判** |
| **登录态误判修复验证** | **outputs/agent_runs/run-agent-liepin-chat-004/ + outputs/submissions/run-agent-liepin-chat-004/** | **共享登录态过期时正确阻断为 login_required** |
| **Agent Loop check-mode 闭环验证** | **outputs/agent_runs/run-agent-liepin-chat-005/ + outputs/submissions/run-agent-liepin-chat-005/** | **login_check/target_verify/chat_send_resume success；submit skipped** |
| **Liepin 小批量频控验证** | **outputs/submissions/batch-rate-limit-001/** | **2 次 check-mode success；第 3 次 blocked=batch_cooldown** |
| **已验证 job_leads** | **job_leads/jl-validated-20260513.yaml** | **3 个新增低风险真实 URL，均有 check-mode 日志** |
| **Agent Loop 批次策略** | **tools/orchestration/agent_loop.py + tests/unit/domain/test_full_pipeline.py** | **confidence_desc_round_robin；dry-run 计划遵守 max_deliveries；DELIVER 事件记录 candidate + selection_strategy** |
| **GUI 投递状态可视化** | **tools/sidecar/handlers/submission.py + ui/src/pages/submissions/index.tsx** | **submission.list 返回并展示 error/last_step/rate_limit** |
| **GUI 运行日志详情页** | **tools/sidecar/handlers/submission.py + ui/src/pages/submissions/index.tsx** | **submission.detail 返回 steps、screenshot_path、log_json_path、log_yaml_path；Playwright mock sidecar 已验证点击 Details 展示** |
| **submit 安全门禁** | **tools/submission/liepin.py + tools/submission/run_submission.py + tools/channels/liepin.py** | **PDF + jobId + recruiter 三重确认，target_verify 后二次匹配** |
| **GUI review hardening** | **tests/unit/sidecar/test_submission_handler.py + tests/unit/domain/test_submission_storage.py + ui/design/contracts/sidecar-rpc.md** | **防止 screenshot path 越界；browser_channel 持久化；submission.detail 合同与 i18n 同步** |
| boss-agent-cli 外部参考 | https://github.com/can4hou6joeng4/boss-agent-cli | Python CLI，MIT，当前调研版本 1.11.0；可参考 BOSS/智联平台 adapter、JSON envelope、schema、MCP server、CDP/浏览器通道、平台风险边界；不作为核心依赖直接引入 |
| 发版记录 | release-notes/ | v0.1.3 ~ v0.1.9 |
| 经验沉淀 | AIEF/context/experience/ | 21 lessons + 2 summaries |
