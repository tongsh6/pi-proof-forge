# Project Ledger / 项目事实台账

> 权威项目状态基线。新会话 AI 和协作者的第一阅读入口。
> 每次重要变更后必须同步更新本文件。若与 tasks.md 冲突，以本文件为准。

## 1. 当前阶段目标

**v2 统一核心引擎架构 + Agent Loop 闭环验证 + 猎聘真实投递**

- 六边形领域核心（domain/）→ 已完成
- 策略注册表 + 四大引擎（engines/）→ 已完成
- Stage 组合编排 + 状态机（orchestration/）→ 已完成 ✅
- 配置解聚 + Composer（config/）→ 已完成（含 build_agent_loop） ✅
- Result 类型 + 事件溯源（domain/）→ 已完成
- 通道层 + CLI 收口 → 已完成
- **AgentLoop 全阶段集成 → 已完成 ✅（2026-05-08）**
- **全链路集成测试 → 已恢复 ✅（327 tests，2026-05-13）**
- **Benchmark 基线 → 已完成 ✅（4 份，docs/benchmarks/）**
- **AppleScript 猎聘搜索 → 已完成 ✅（2026-05-09）**
- **Agent Loop → Liepin 投递链路 → 已验证登录，已修正下线职位误报上传失败（2026-05-09）**
- **猎聘真实投递闭环验证 → ✅ 已完成（2026-05-11）**
- **当前阻塞：无硬阻塞。Agent Loop → Liepin check-mode、小批量频控、批量候选来源扩展、多候选批次策略、GUI 投递状态/详情可视化、真实 submit 前安全门禁均已闭环（2026-05-13）**

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
| 旧 CLI 兼容层 | 已验证 | run_pipeline.py 等转调新架构 | test_legacy_entrypoint_redirect.py | 参数语义不破坏 |
| 企业例外清单 | 已验证 | discovery filter + gate guard | test_exclusions.py + test_gate.py | 双层防护 |
| Sidecar Bridge | 已验证 | tools/sidecar/ | 12 test files | JSON-RPC router + 9 handlers + REVIEW RPC |
| v2 约束检查 | 已通过 | tools/check_v2_constraints.py | PASS | 无重复 LLM/YAML、业务层无 subprocess、无 if use_llm；AppleScript 系统调用已收口到 infra/browser |
| AIEF L3 检查 | 已通过 | tools/check_aief_l3.py | PASS | 全部必需文件 + lessons + summaries |
| GUI 设计规范 | 已冻结 | ui/design/DESIGN.md + piproofforge.pen | 双真源联动 | 9 页 IA，暗色主题，Tauri + React/TS + Python sidecar |
| GUI 前端骨架 | 已实现 | ui/src/ (29 files) | 9 页面路由 + i18n + RPC transport | 骨架级别，非产品级 |
| **Composer build_agent_loop** | **已完成** | tools/config/composer.py | 集成测试通过 | 组装四大引擎 + GateEngine + ReviewStage + Channels |
| **AgentLoop 全阶段集成** | **已完成** | tools/orchestration/agent_loop.py | 6 integration tests | INIT→DISCOVER→SCORE→GENERATE→EVALUATE→GATE→REVIEW→DELIVER→LEARN→DONE |
| **全链路集成测试** | **已完成** | tests/unit/domain/test_full_pipeline.py | 7 tests passed | 含 dry-run 全状态、max_rounds、max_deliveries、企业排除、事件回放、多候选批次策略 |
| **Benchmark 基线** | **已完成** | docs/benchmarks/benchmark-001.md | rule-mode 完整评测 | 发现 matching 引擎不搜索 stack 字段 |
| **Matching 引擎 stack 搜索** | **已完成** | tools/domain/models.py + rule_scorer.py + store.py | 2 new tests | K-score 0.0→0.6，证据卡可区分 |
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
| **多候选 Agent Loop 批次策略** | **已测试** | tools/orchestration/agent_loop.py | test_full_pipeline.py + test_agent_loop.py | 按 confidence desc + candidate_id 稳定排序；每轮排除已选候选；dry-run 也遵守 max_deliveries 计划上限 |
| **GUI 投递状态可视化** | **已验证** | tools/sidecar/handlers/submission.py + ui/src/pages/submissions/index.tsx | test_submission_handler.py + `pnpm --dir ui build` | 展示 mode、job_url、error、last_step、rate_limit 状态和详情 |
| **GUI 运行日志详情页** | **已验证** | tools/sidecar/handlers/submission.py + tools/sidecar/server.py + ui/src/pages/submissions/index.tsx | test_submission_handler.py + test_server.py + Playwright mock sidecar | `submission.detail` 返回完整 steps、截图路径、JSON/YAML 日志路径；Submissions 页面可点击查看 |
| **真实 submit 前安全门禁** | **已测试** | tools/submission/liepin.py + tools/submission/run_submission.py + tools/channels/liepin.py | test_liepin_chat_send_resume.py + test_run_submission_cli.py + test_channels.py | submit 必须 PDF、显式 jobId、显式 recruiter，且与 target_verify 二次匹配 |

## 3. 已验证事项

| 事项 | 验证方式 | 报告路径 | 结论 |
|------|----------|----------|------|
| 全部 327 单元测试 | `python3 -m pytest tests/ -q` | 终端输出 | 327 passed |
| v2 静态约束 | `python3 tools/check_v2_constraints.py --root .` | 终端输出 | PASS |
| AIEF L3 合规 | `python3 tools/check_aief_l3.py --root . --base-dir AIEF` | 终端输出 | PASS |
| Agent full-pipeline dry-run | `python3 -m tools.cli.entrypoints agent --policy policy.yaml --dry-run --evidence-dir evidence_cards --job-profile job_profiles/jp-2026-001.yaml` | 终端输出 | DONE (10 状态全量日志) |
| Benchmark 001 (rule baseline) | `docs/benchmarks/benchmark-001.md` | Matching Total=0.5, Eval Total=0.65 | 发现 K-score=0（已修复） |
| Benchmark 002 (stack fix 后) | 同命令复现 | Matching Total=0.8, K-score=0.6 | 证据卡可按技术栈区分 |
| Benchmark 003 (LLM vs Rule) | `docs/benchmarks/benchmark-003.md` | LLM K=0.73, Rule K=0.60 | LLM 更精准但更慢，建议混合策略 |
| Benchmark 004 (LLM Evaluator) | `docs/benchmarks/benchmark-004.md` | semantic coverage 0.30→0.42 | 打破 coverage=0 盲区 |
| LLM 连接验证 | LM Studio localhost:1234 | openai/gpt-oss-120b 可用 | 响应正常 |
| Hybrid 匹配策略 | `tools/engines/matching/hybrid_matcher.py` | 2.3x faster than pure LLM | Rule 初筛 Top5 → LLM 精选 |
| Playwright + Liepin 验证 | `tools/channels/liepin.py` | check-mode 通过 | 需登录态完成真实投递 |
| Agent Loop 端到端验证 | 真实验证脚本 | hybrid + LLM evaluator, 10 状态全通过 | 2 rounds, 18 events, matching 0.772→0.919 |
| SLA/SLO 证据卡 | `evidence_cards/ec-2026-018.yaml` / `019.yaml` | K-score: Backend 1.0, SRE 0.857 | SLA/SLO 盲区消除 |
| GUI 编译验证 | `cd ui && npm run build` | TypeScript 零错误, 1627 modules, 1.14s | 9 页全部可编译 |
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
| P3 | GUI 前端为骨架级别 | 可演示性不足 | 实现缺口 | 后端闭环稳定后再投入 |
| P4 | Gap tasks 仅检查 must_have，不检查 keywords | SLA/SLO 等关键词缺失不会触发补证据任务 | 设计缺口 | 低优先级 |
| ~~P5~~ | ~~误投防护需接入 liepin.py 主流程~~ | ~~poc_e2e_send.py 已有 sanity check，但主流程 `liepin.py` 未接入~~ | **已解决** | **target_verify 已接入并有离线单测覆盖** |

## 6. 已废弃事项

无明确废弃事项。

## 7. 当前 Top Priority

| 优先级 | 事项 | 原因 | 验收标准 |
|--------|------|------|----------|
| 1 | submit 安全门禁真实 dry-run 演练 | 代码级门禁已测试，但未用真实页面跑 submit_safety blocked 路径 | 使用 PDF + 错误 recruiter/jobId 运行 submit，确认阻断在 submit_safety 且未点击最终确认 |
| 2 | Agent Loop 批次策略真实 check-mode 演练 | 代码级批次策略已测试，但未用真实 job_leads 跑多候选 check-mode 端到端批次 | 多候选 DISCOVER/GATE/DELIVER 顺序与 submission 日志可对账，且通道频控仍生效 |
| 3 | GUI 详情页接入真实 sidecar 桌面壳验证 | 浏览器 mock 已验证详情页，仍需在 Tauri 桌面壳确认真实 sidecar bridge | 桌面壳中 Submissions 可加载真实 `submission.detail`，无 bridge/布局错误 |

## 8. 关键证据索引

| 证据 | 路径 | 说明 |
|------|------|------|
| 核心规范 | openspec/specs/pi-proof-forge-core.md | v2 架构规范（535 行） |
| 架构设计 | openspec/changes/autonomous-agent-delivery-loop/design.md | v2 设计（779 行） |
| 任务清单 | openspec/changes/autonomous-agent-delivery-loop/tasks.md | 全 [x]（注意：组件级完成 ≠ 集成级完成） |
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
| 测试 | tests/ | 327 tests |
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
| 发版记录 | release-notes/ | v0.1.3 ~ v0.1.9 |
| 经验沉淀 | AIEF/context/experience/ | 21 lessons + 2 summaries |
