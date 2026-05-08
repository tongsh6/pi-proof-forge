# Project Ledger / 项目事实台账

> 权威项目状态基线。新会话 AI 和协作者的第一阅读入口。
> 每次重要变更后必须同步更新本文件。若与 tasks.md 冲突，以本文件为准。

## 1. 当前阶段目标

**v2 统一核心引擎架构 + Agent Loop 闭环验证**

- 六边形领域核心（domain/）→ 已完成
- 策略注册表 + 四大引擎（engines/）→ 已完成
- Stage 组合编排 + 状态机（orchestration/）→ 已完成 ✅
- 配置解聚 + Composer（config/）→ 已完成（含 build_agent_loop） ✅
- Result 类型 + 事件溯源（domain/）→ 已完成
- 通道层 + CLI 收口 → 已完成
- **AgentLoop 全阶段集成 → 已完成 ✅（2026-05-08）**
- **全链路集成测试 → 已完成 ✅（6 tests，287 total）**
- **Benchmark 基线 → 已完成 ✅（docs/benchmarks/benchmark-001.md）**
- **当前阻塞：AgentLoop 未集成 Pipeline/GateEngine/ReviewStage/StateMachine**

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
| v2 约束检查 | 已通过 | tools/check_v2_constraints.py | PASS | 无重复 LLM/YAML、无 subprocess、无 if use_llm |
| AIEF L3 检查 | 已通过 | tools/check_aief_l3.py | PASS | 全部必需文件 + lessons + summaries |
| GUI 设计规范 | 已冻结 | ui/design/DESIGN.md + piproofforge.pen | 双真源联动 | 9 页 IA，暗色主题，Tauri + React/TS + Python sidecar |
| GUI 前端骨架 | 已实现 | ui/src/ (29 files) | 9 页面路由 + i18n + RPC transport | 骨架级别，非产品级 |
| **Composer build_agent_loop** | **已完成** | tools/config/composer.py | 集成测试通过 | 组装四大引擎 + GateEngine + ReviewStage + Channels |
| **AgentLoop 全阶段集成** | **已完成** | tools/orchestration/agent_loop.py | 6 integration tests | INIT→DISCOVER→SCORE→GENERATE→EVALUATE→GATE→REVIEW→DELIVER→LEARN→DONE |
| **全链路集成测试** | **已完成** | tests/unit/domain/test_full_pipeline.py | 6 tests passed | 含 dry-run 全状态、max_rounds、max_deliveries、企业排除、事件回放 |
| **Benchmark 基线** | **已完成** | docs/benchmarks/benchmark-001.md | rule-mode 完整评测 | 发现 matching 引擎不搜索 stack 字段 |
| **Matching 引擎 stack 搜索** | **已完成** | tools/domain/models.py + rule_scorer.py + store.py | 2 new tests | K-score 0.0→0.6，证据卡可区分 |
| **Liepin Channel 真实实现** | **已完成** | tools/channels/liepin.py | 集成 tools/submission/liepin.py (464行 Playwright) | 无 Playwright 时优雅降级为模拟模式 |
| **LLM 对比 Benchmark** | **已完成** | docs/benchmarks/benchmark-003.md | LM Studio openai/gpt-oss-120b | LLM K=0.73 vs Rule K=0.60，LLM 缺口更具体，建议混合策略 |
| **LLM Matcher prompt 修复** | **已完成** | tools/engines/matching/llm_matcher.py | 新增 stack 字段到 prompt | LLM 可看到技术栈信息 |

## 3. 已验证事项

| 事项 | 验证方式 | 报告路径 | 结论 |
|------|----------|----------|------|
| 全部 289 单元测试 | `python3 -m pytest tests/ -q` | 终端输出 | 289 passed in 0.31s |
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
| GUI 编译验证 | `cd ui && pnpm install && pnpm run build` | TypeScript 零错误, 1627 modules, 862ms | 9 页全部可编译 |
| LLM Evaluator 增强 | `tools/engines/evaluation/llm_evaluator.py` | 6 维度语义评测 | semantic_coverage + fabrication_risk + gaps/strengths/improvements |

## 4. 进行中事项

无。上轮三项进行中事项（AgentLoop 集成、Composer build、Benchmark 基线）均已在 2026-05-08 完成。

## 5. 已知缺口（按优先级）

| 优先级 | 缺口 | 影响 | 类型 | 阻塞条件 |
|--------|------|------|------|----------|
| P1 | 无 LLM 模式对比数据 | 无法量化 LLM vs Rule 的质量差异 | 验证缺口 | 需 LLM_API_KEY 环境变量 |
| P2 | 无真实投递验证 | Email/Liepin 通道未真实验证 | 验证缺口 | Email 需 SMTP 凭据；Liepin 需 Playwright + 登录态 |
| P3 | GUI 前端为骨架级别 | 可演示性不足 | 实现缺口 | 后端闭环稳定后再投入 |
| P4 | Gap tasks 仅检查 must_have，不检查 keywords | SLA/SLO 等关键词缺失不会触发补证据任务 | 设计缺口 | 低优先级 |

## 6. 已废弃事项

无明确废弃事项。

## 7. 当前 Top Priority

| 优先级 | 事项 | 原因 | 验收标准 |
|--------|------|------|----------|
| 1 | 修复 Matching 引擎搜索 stack 字段 | Benchmark 揭示 K-score=0，所有卡无法区分 | rule_scorer 扩展至 stack 搜索，K-score > 0 |
| 2 | LLM 模式对比 Benchmark | 建立 rule vs LLM 质量基线 | benchmark-002 含两组对比数据 |
| 3 | 真实投递验证 | 验证 Email/Liepin 通道可用性 | 至少一个通道成功发出投递 |

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
| Agent Loop | tools/orchestration/agent_loop.py | 当前为骨架实现 |
| State Machine | tools/orchestration/state_machine.py | 10 状态定义（未被 AgentLoop 使用） |
| Gate Engine | tools/orchestration/gate_engine.py | N-pass 门禁 + 企业排除 |
| Review Stage | tools/orchestration/review_stage.py | auto/manual/batch 三种模式 |
| Composer | tools/config/composer.py | 组装点（缺 build_pipeline/build_agent_loop） |
| Sidecar | tools/sidecar/server.py | GUI-Python JSON-RPC 桥接 |
| GUI 设计 | ui/design/DESIGN.md | 终版 9 页 IA |
| 测试 | tests/ | 281 tests, 51 test files |
| v2 约束 | tools/check_v2_constraints.py | 静态约束校验脚本 |
| 发版记录 | release-notes/ | v0.1.3 ~ v0.1.9 |
| 经验沉淀 | AIEF/context/experience/ | 21 lessons + 2 summaries |
