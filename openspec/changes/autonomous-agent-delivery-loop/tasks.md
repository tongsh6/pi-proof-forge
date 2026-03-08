# Tasks: autonomous-agent-delivery-loop

> 架构方案：统一核心引擎 v2（六边形领域核心 + 策略注册表 + 管道组合化）
> 设计依据：`design.md` Section 0 / 1 / 8 / 9 / 13
> 迁移策略：自下而上建新架构，旧 CLI 同期保持可用，Phase E 收口

---

## Phase A - 领域核心与基础设施地基

> 目标：建立 `domain/` 零依赖核心、`infra/` 唯一实现层、`config/` 配置切片，消除重复实现
> TDD 约束：本阶段每项任务均须先写失败测试，再写实现；测试失败不得进入下一任务

- [ ] A1 新增 `tools/domain/models.py`
  - 定义 frozen dataclass：`EvidenceCard`、`JobProfile`、`MatchingReport`、`ResumeOutput`、`Scorecard`
  - `EvidenceCard.is_eligible()` 强制体现 evidence-first 约束（缺 `results/artifacts` 不进入候选池）
- [ ] A2 新增 `tools/domain/value_objects.py`
  - 定义 `Score`、`GapTask`、`Candidate`、`ScoreBreakdown`、`GateDecision`、`DeliveryResult`
- 新增 ReviewCandidate（job_lead_id / company / position / matching_score / evaluation_score / round_index / resume_version）和 ReviewDecision（job_lead_id / action: approve|reject|skip|skip_all / decided_by / decided_at / note）
  - 所有值对象不可变、可比较、可序列化
- [ ] A3 新增 `tools/domain/protocols.py`
  - 定义 `EvidenceExtractor`、`MatchingEngine`、`GenerationEngine`、`EvaluationEngine`
  - 定义 `DiscoveryEngine`、`GateEngine`、`DeliveryChannel`、`RunStore`、`Stage`、`ReviewStage`
  - 规则：接口定义只能出现在 `domain/`，不得散落在 `engines/` 或 `infra/`
- [ ] A4 新增 `tools/domain/invariants.py`
  - 实现 evidence-first 守卫、事实保真守卫
  - 明确哪些约束返回 `False`，哪些约束抛不可恢复异常
- [ ] A5 新增 `tools/domain/result.py`
  - 定义 `Ok[T]` / `Err[E]` / `Result[T, E]`
  - 约定：`gate_fail`、`channel_error`、`discovery_empty` 等可恢复场景用 Result，不抛异常
- [ ] A6 新增 `tools/domain/events.py` + `tools/domain/run_state.py`
  - 定义不可变 `RunEvent`
  - `RunState.replay(events)` 通过事件回放重建当前状态
  - 支持断点续跑和审计追溯
- [ ] A7 新增 `tools/infra/llm/client.py`
  - 统一 LLM HTTP 客户端（`post_json` + `extract_content` 唯一实现）
  - 支持 OpenAI-compatible 接口，超时可配置
  - 后续可扩展 adapter，但 `client.py` 必须是唯一 HTTP 出口
- [ ] A8 新增 `tools/infra/persistence/yaml_io.py`
  - 统一 YAML 读写（`parse_simple_yaml` + `unquote` + `dump_yaml` 唯一实现）
  - 不引入外部 YAML 依赖
- [ ] A9 新增 `tools/infra/logging.py`
  - 结构化日志（JSON 格式，含 `run_id` / `round` / `state` 字段）
- [ ] A10 新增 `tools/config/fragments.py`
  - 定义 `LLMConfig`、`PathConfig`、`PolicyConfig`、`EngineSelection`
  - PolicyConfig 必须包含 delivery_mode（auto|manual）和 batch_review（bool，仅 manual 时生效）字段
  - 禁止保留上帝对象 `Config`
  - `PolicyConfig` 必须包含企业例外清单语义（如 `excluded_companies`、`excluded_legal_entities`）
- [ ] A10a 同步 GUI 配置承载边界文档
  - GUI 必须拆为 `Policy / 策略配置` 与 `System Settings / 系统设置` 两个正式页面
  - `Policy` 对应 `Gate Policy + Exclusion List`
  - `System Settings` 对应 `Channels + LLM Config`
  - 首版 bridge 可以继续使用聚合 settings payload，但前端信息架构不得回退为单个 `Settings`
- [ ] A11 新增 `tools/config/loader.py` + `tools/config/validator.py`
  - `loader.py`：从 policy YAML + CLI 参数合并构造配置切片
  - `validator.py`：配置合规校验（必填字段、范围约束、策略名合法性）
  - 例外清单校验：匹配模式只允许 `exact` / `contains`，空值或重复值必须显式失败
  - 必须明确把 YAML `filters.excluded_companies` / `filters.excluded_legal_entities` 映射到 `PolicyConfig.excluded_companies` / `PolicyConfig.excluded_legal_entities`
- [ ] A12 新增 `tools/config/composer.py`
  - `Composer` 作为唯一组装点，负责把配置切片组装成 pipeline / agent loop
  - 业务层禁止直接读取环境变量
- [ ] A13 新增 `tools/errors/exceptions.py`
  - 只定义不可恢复异常：`PiProofError`、`EvidenceValidationError`、`FabricationGuardError`、`PolicyError`
  - 移除把 `gate_fail` / `channel_error` 设计为异常的方案
- [ ] A14 新增 `tools/errors/handler.py`
  - 定义错误路由：终止 run / 进入 LEARN / 通道降级
  - 规则：异常只处理不可恢复场景，Result 由编排层显式消费
- [ ] A15 将 `run_matching_scoring.py`、`run_generation.py`、`run_evaluation.py`、`extract_evidence_llm.py` 中的重复 LLM/YAML 逻辑迁移到 `infra/`
  - 保持各文件 CLI 行为不变，作为兼容期过渡
  - 必须补充兼容性回归测试，验证旧 CLI 参数语义与输出格式不变

---

## Phase B - 引擎层与策略注册表

> 目标：引擎全部通过 `EngineRegistry` 创建，彻底消除 `if use_llm` 分支
> TDD 约束：每个引擎先写红灯测试，再实现最小通过版本，最后重构

- [ ] B1 新增 `tools/engines/registry.py`
  - 实现通用 `EngineRegistry[T]`
  - 支持 register/create/list 三个最小能力
  - 未注册策略必须在启动或构建阶段失败，禁止隐式回退

### B-Evidence（证据引擎）
- [ ] B2 新增 `tools/engines/evidence/rule_extractor.py`
  - 迁移 `extract_evidence.py` 规则逻辑
  - 仅处理领域对象，不依赖文件路径或 CLI
- [ ] B3 新增 `tools/engines/evidence/llm_extractor.py`
  - 注入 `LLMClient`，不在内部读取环境变量
  - 通过 registry 注册为 `evidence_mode=llm`
- [ ] B4 新增 `tools/engines/evidence/validator.py`
  - 强制校验 `results/artifacts`，违反抛 `EvidenceValidationError`
  - 验证 `raw_source` 引用存在且可追溯
- [ ] B5 新增 `tools/engines/evidence/store.py`
  - 证据卡读取、写入、按 ID 检索
  - 路径通过 `PathConfig` 注入，不硬编码

### B-Matching（匹配评分引擎）
- [ ] B6 新增 `tools/engines/matching/rule_scorer.py`
  - `RuleMatchingEngine`：K/D/S/Q/E/R 六维度规则评分
  - 迁移 `build_rule_report` 核心逻辑
- [ ] B7 新增 `tools/engines/matching/llm_matcher.py`
  - `LLMMatchingEngine`：注入 `LLMClient` + prompt 路径
  - 构造器注入，不含 `if use_llm` 分支
- [ ] B8 新增 `tools/engines/matching/report_builder.py`
  - 构造 `MatchingReport`
  - 强制生成 `gap_tasks`，不得静默忽略缺口

### B-Generation（简历生成引擎）
- [ ] B9 新增 `tools/engines/generation/template_assembler.py`
  - 迁移 `build_template_resume` 核心逻辑
  - 无对应 EvidenceCard 的内容禁止生成，违反抛 `FabricationGuardError`
  - 必须先写红灯测试，验证无证据内容会触发守卫
- [ ] B10 新增 `tools/engines/generation/llm_rewriter.py`
  - 受控改写语气，不引入新事实
  - 必须把 `jd_context` 和 `company_context` 注入 prompt
- [ ] B11 新增 `tools/engines/generation/exporter.py`
  - Markdown 导出（基准实现）
  - PDF 导出接口（占位，后续实现）

### B-Evaluation（质量评测引擎）
- [ ] B12 新增 `tools/engines/evaluation/rule_evaluator.py`
  - `RuleEvaluationEngine`：coverage/quant/clarity/length/citation 五维度
  - 迁移 `evaluate_rule` 核心逻辑
- [ ] B13 新增 `tools/engines/evaluation/llm_evaluator.py`
  - 先执行规则评测，再用 LLM 补充解释层
  - 规则分数不可被 LLM 修改
- [ ] B14 新增 `tools/engines/evaluation/scorecard_builder.py`
  - 构造 `Scorecard`，每项质量分必须可追溯到具体检查点

### B-Discovery（候选发现引擎）
- [ ] B15 新增 `tools/engines/discovery/discovery_engine.py`
  - 三级 fallback：`job_leads/*.yaml` → `jd_inputs/*.txt` → `evidence_cards/*.yaml`
  - Candidate confidence：`0.5 * source_quality + 0.3 * keyword_match + 0.2 * recency_signal`
  - 同一 `company + direction` 聚合为一个 candidate，保留最高置信度 URL，记录 `merged_sources`
  - 公司主体归一后，按 `excluded_companies` / `excluded_legal_entities` 执行企业例外清单过滤
  - 被过滤 candidate 不进入 scoring / generation / delivery，但必须记录 `excluded_by_policy` 原因用于审计

### B-Registry Wiring
- [ ] B16 完成四大引擎 + discovery 的 registry 注册
  - `rule` / `llm` / `template` 等策略都通过注册表创建
  - 增加测试：新增一个虚拟策略无需修改既有代码即可接入

---

## Phase C - 编排层（Stage 组合 + 状态机 + Result 流）

> 目标：`run_agent --dry-run` 可完成至少 1 轮并写入 run_log；pipeline 与 agent_loop 共用 Stage
> TDD 约束：状态迁移、门禁计数与预算控制必须先由纯单元测试锁定行为

- [ ] C1 新增 `tools/orchestration/stage.py`
  - 定义 `Stage` Protocol、`StageResult`、`RunContext`
  - `StageResult` 只承载本阶段结果，不做全局状态管理
- [ ] C2 新增 `tools/orchestration/pipeline.py`
  - `LinearPipeline` 由 `Sequence[Stage]` 组合而成
  - 线性流水线：extraction → matching → generation → evaluation
- [ ] C3 新增 `tools/orchestration/state_machine.py`
  - 实现 Section 2 的 10 状态迁移规则（含 REVIEW）
  - 纯函数，可独立单元测试
- [ ] C4 新增 `tools/orchestration/gate_engine.py`
  - `GateEngine.evaluate()` 返回 `Result[GateDecision, GateFailure]`
  - readiness 判定必须绑定当前 `run_id + round_index`
  - 对命中企业例外清单的 candidate 做兜底校验，返回 `excluded_company` 原因，禁止进入 `DELIVER`
- [ ] C4a 新增 `tools/orchestration/review_stage.py`
  - ReviewStage 实现 Stage Protocol
  - auto 模式：REVIEW 为 pass-through，直接返回 success，不暂停
  - manual + batch_review=false：逐轮审批，GATE 通过后暂停，发出 agent.review.pending 事件，等待用户通过 RPC 提交 ReviewDecision
  - manual + batch_review=true：批量审批，所有轮次跑完后一次性展示 TopN 候选
  - 测试须覆盖三种模式的行为差异
- [ ] C5 新增 `tools/orchestration/agent_loop.py`
  - 驱动完整 INIT→DISCOVER→SCORE→GENERATE→EVALUATE→GATE→REVIEW→DELIVER→LEARN→DONE 循环
  - 复用 pipeline 的 Stage，不重复实现阶段逻辑
  - 幂等键：`run_id + candidate_id + channel + resume_version`
- [ ] C6 新增 `tools/run_agent.py`
  - 支持：`--policy`、`--run-id`、`--dry-run`
  - 内部调用 `Composer.build_agent_loop()`，不含业务逻辑
- [ ] C7 落地 Result 流消费逻辑
  - `gate_fail` 进入 LEARN，不抛异常
  - `channel_error` 触发降级，不抛异常
  - `FabricationGuardError` / `EvidenceValidationError` 终止 run
- [ ] C8 落地事件回放与断点续跑
  - `RunState.replay(events)` 可重建当前状态
  - 为后续 resume/retry 提供基础能力

---

## Phase D - 通道、发现与运行存储

> TDD 约束：通道失败重试、降级策略、事件追加写入与 discovery 冲突合并需先有测试覆盖

- [ ] D1 新增 `tools/channels/base.py`
  - `DeliveryChannel` Protocol 定义（`deliver()` 返回 `Result[DeliveryResult, ChannelFailure]`）
- [ ] D2 新增 `tools/channels/liepin.py`
  - 纯 Python 实现，不依赖 subprocess
  - 将 `tools/submission/run_submission.py` 的核心逻辑迁移为通道内实现
- [ ] D3 新增 `tools/channels/email.py`
  - `smtplib` 实现，凭据仅从环境变量读取（`SMTP_USER` / `SMTP_PASS`）
  - 附件优先级：`resume.pdf > resume.md`
  - Email 失败可重试 1 次，仍失败返回 `ChannelFailure(retryable=False)`
- [ ] D4 实现通道顺序与降级策略
  - liepin 失败后降级 email
  - strict / simulate 两种 gate_mode 下行为分别测试
- [ ] D5 新增 `tools/infra/persistence/file_run_store.py`
  - 输出 `outputs/agent_runs/<run_id>/run_log.json`
  - 事件追加写入，不回写历史
  - 轮次快照：`rounds/<n>/`
- [ ] D6 实现 `RunStore.load_events(run_id)`
  - 支持状态回放、断点续跑、审计追溯

---

## Phase E - CLI 收口、兼容与质量门禁

> TDD 约束：兼容回归、Exit Criteria 对应测试与 CI 校验必须先补齐，未通过不得收口

- [ ] E1 新增 `tools/cli/`（薄 CLI 层）
  - `commands/extract.py / match.py / generate.py / evaluate.py / pipeline.py / agent.py`
  - 每个 command：仅解析参数 → 构造 `Composer` → 调用对应编排或引擎
  - `entrypoints.py`：统一注册入口
- [ ] E2 旧 CLI 入口（`tools/run_pipeline.py` 等）内部转调 `Composer` + 新架构
  - CLI 参数语义保持不破坏
  - 删除旧文件前必须通过 end-to-end 回归测试
- [ ] E3 测试分层（按 `design.md` Section 12）
  - Domain 单测（约 70%）：不可变模型、状态迁移、预算控制、Result 行为、事件回放
  - 引擎单测：各引擎独立测试（不依赖 IO）
  - 契约测试（约 20%）：Protocol 输出契约、registry 创建契约
  - 兼容期旧 CLI 回归测试：参数语义与输出格式不变
  - End-to-end smoke（约 10%）：`run_agent --dry-run` 至少 1 轮写入 run_log
- [ ] E4 覆盖以下必测场景
  - `gate_mode=strict` 与 `gate_mode=simulate` 行为差异
  - readiness 按 `run_id + round_index` 绑定判定（多轮/并行不串线）
  - generation 输入含 `jd_context/company_context` 且日志可追溯
  - `EvidenceValidationError`：results/artifacts 缺失时拒绝进入候选池
  - `FabricationGuardError`：无证据内容被拦截
  - 新增一个虚拟 strategy 只需注册即可接入
  - `RunState.replay(events)` 能恢复到最新状态
  - delivery_mode=auto 时 REVIEW pass-through，不暂停不阻塞
  - delivery_mode=manual + batch_review=false 时逐轮审批行为正确
  - delivery_mode=manual + batch_review=true 时批量审批行为正确
  - ReviewCandidate / ReviewDecision 值对象不可变且可序列化
  - candidate 命中企业例外清单后在 discovery 阶段被过滤，并记录 `excluded_by_policy`
  - 若 candidate 绕过 discovery 过滤，`GateEngine` 仍能以 `excluded_company` 原因阻止进入 `DELIVER`
- [ ] E5 更新 `tools/README.md` 与根 `README.md`
  - 新增 v2 架构说明与 `run_agent` 使用示例
  - 说明 `domain/`、`infra/`、`engines/`、`orchestration/` 的职责
- [ ] E6 AIEF L3 检查通过（`python3 tools/check_aief_l3.py --root . --base-dir AIEF`）
- [ ] E7 新增 CI/静态校验任务
  - 校验不再存在重复 `post_json` / `extract_content` / `parse_simple_yaml` 实现
  - 校验业务层不再出现 `subprocess` 串联
  - 校验 `if use_llm` 不再出现在业务引擎内
  - 校验 Exit Criteria 中的可自动化条目均有对应测试或脚本

---

## Exit Criteria

- [ ] 单命令可触发完整 Agent 循环（`python3 tools/run_agent.py --policy ...`）
- [ ] N-pass 门禁生效且有日志可追溯（strict/simulate 行为符合预期）
- [ ] 至少一个通道可在 dry-run / simulate 条件下完成端到端投递链路并产出可追溯 artifact
- [ ] 达到 `max_rounds` 或 `max_deliveries` 时可安全停止
- [ ] 旧入口脚本保持兼容（无破坏性参数变化）
- [ ] 4 处 LLM 客户端重复已消除，统一使用 `infra/llm/client.py`，并由静态检查脚本验证
- [ ] 3 处 YAML 解析重复已消除，统一使用 `infra/persistence/yaml_io.py`，并由静态检查脚本验证
- [ ] 所有业务层 subprocess 串联已消除，改为纯 Python API 调用，并由静态检查脚本验证
- [ ] 所有业务引擎内不再出现 `if use_llm` 分支，并由静态检查脚本验证
- [ ] 生成产物中的结论均可追溯到具体 EvidenceCard，守卫测试通过
- [ ] Domain 单测 + 引擎单测全部通过
- [ ] Result 类型已用于可恢复错误（gate/channel/discovery）
- [ ] RunState 支持事件回放恢复
- [ ] 企业例外清单已在 discovery 主过滤 + gate 兜底两层生效
- [ ] auto/manual 双模式可通过 delivery_mode 配置切换，且 auto 下 REVIEW 为 pass-through
- [ ] manual 模式下 ReviewStage 可正确暂停并等待用户审批
- [ ] AIEF L3 检查通过
