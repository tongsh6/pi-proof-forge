# Design: autonomous-agent-delivery-loop

## 0. 架构审核发现（2026-03-06 v2 审核）

> 本节记录第二次架构审核的诊断结果，作为 v2 架构修订的依据。

### 已确认的 7 大架构问题

| # | 问题 | 严重度 | 证据 |
|---|------|--------|------|
| P1 | **DRY 严重违反** | Critical | `post_json` 4处重复、`parse_simple_yaml` 3处重复、`extract_content` 4处重复 |
| P2 | **OCP 违反** | Critical | `if use_llm` 分支在 3 个文件散落（matching L323, generation L280, evaluation L286） |
| P3 | **subprocess 串联** | High | `run_pipeline.py` 通过 `subprocess.run` 串联，错误传播靠 returncode |
| P4 | **零测试覆盖** | High | 整个 `tools/` 无测试文件，领域逻辑与 IO/CLI 耦合 |
| P5 | **配置散落** | Medium | `os.getenv("LLM_API_KEY")` 分散 4 个文件，无集中管理 |
| P6 | **领域模型缺失** | Medium | TypedDict 代替领域对象，无验证、无不可变性 |
| P7 | **硬编码路径** | Medium | `Path("evidence_cards")` 硬编码在 `run_generation.py` L275 |

### v1 设计的 5 个待优化点

1. **`core/shared/` 职责过宽**：混合基础设施（LLM client）和通用工具（YAML IO），违反 SRP。
2. **EngineConfig `Literal` 类型**：`Literal["rule", "llm"]` 硬编码策略类型，新增策略需改 schema。
3. **orchestration/ 承担过多**：pipeline + agent_loop + gate_engine + discovery_engine 全在一个包。
4. **domain/ 位置不当**：领域模型放在 `core/domain/` 而非顶层，暗示领域依赖基础设施。
5. **Config 上帝对象**：单个 `Config` dataclass 包含 `llm + paths + policy + engine`，职责过多。

### 6 项改进方案（均已纳入 v2 设计）

| # | 方案 | 原则 | 优先级 |
|---|------|------|--------|
| R1 | 六边形领域核心 — domain/ 提升为顶层零依赖包 | DIP、Clean Architecture | P0 必须做 |
| R2 | 策略注册表 — EngineRegistry 替代 Literal 枚举 | OCP、策略模式 | P0 必须做 |
| R3 | 管道组合化 — Stage Protocol 统一 pipeline/agent_loop | SRP、组合优于继承 | P1 推荐做 |
| R4 | 配置解聚 — Config 拆为独立切片 + Composer 组装 | ISP、最小知识 | P1 推荐做 |
| R5 | Result 类型 — 可恢复错误用 Ok/Err，不用异常 | 函数式错误处理 | P2 锦上添花 |
| R6 | 事件溯源 — RunState 从事件回放重建 | 不可变性、可追溯 | P2 锦上添花 |

---

## 1. Selected Approach
采用"统一核心引擎 v2"方案（2026-03-06 架构审核后修订）：

在 v1 方案的基础上，融合 6 项架构改进：

- 彻底消除 subprocess 串联，所有阶段重构为纯 Python API。
- **六边形领域核心**（R1）：`tools/domain/` 提升为顶层包，零外部依赖，所有模块向内依赖。
- **策略注册表**（R2）：EngineRegistry 动态注入策略，新增策略只需注册，不改已有代码。
- **管道组合化**（R3）：Stage Protocol 统一 pipeline 和 agent_loop 的阶段抽象。
- **配置解聚**（R4）：Config 拆为 LLMConfig/PathConfig/PolicyConfig/EngineSelection 独立切片。
- **Result 类型**（R5）：可恢复错误（gate_fail/channel_error）用 Result[T, E]，不用异常。
- **事件溯源**（R6）：RunState 从不可变事件回放重建，支持断点续跑。

选择理由：
- **彻底解决 DRY 违规**：LLM 客户端、YAML 解析各有唯一实现，集中在 `infra/` 层。
- **消除 OCP 违反**：策略注册表替代 `if use_llm` 分支和 `Literal` 枚举。
- **依赖倒置**：Protocol 定义在 `domain/`，实现在 `engines/` 和 `infra/`，领域层零外部依赖。
- **可测试**：纯 Python API，领域逻辑不依赖 IO，可独立单元测试。
- **可扩展**：新增 LLM provider / 投递通道 / 导出格式，只需实现 Protocol 并注册，不改现有代码。

架构审核依据：见 `openspec/specs/pi-proof-forge-core.md` → "统一核心引擎架构规范（v2）"

## 2. State Machine

### States
1. `INIT`: 读取 policy、初始化 run 目录。
2. `DISCOVER`: 获取候选方向/公司/JD（优先 `job_leads`，无则从已有资料自动推导，再回退手工输入）。
3. `SCORE`: 执行 matching scoring，得到匹配分与 gaps。
4. `GENERATE`: 生成目标简历版本。
5. `EVALUATE`: 运行评测得到 scorecard。
6. `GATE`: 联合判定 N-pass 门禁。
7. `REVIEW`: 人工审批（仅 `delivery_mode=manual` 时激活；`auto` 模式下为 pass-through）。
8. `DELIVER`: 通过通道执行投递（Liepin/Email）。
9. `LEARN`: 记录本轮结果与失败原因，决定下一轮。
10. `DONE`: 达到成功条件或预算上限后结束。

### Transition Rules

**通用规则：**
- `INIT -> DISCOVER`：policy 有效。
- `DISCOVER -> SCORE`：存在候选项。
- `LEARN -> DISCOVER`：`current_round < max_rounds` 且 `delivered < max_deliveries`。
- `LEARN -> DONE`：达到预算上限或无可用候选。

**Auto 模式 (`delivery_mode=auto`)：**
- `GATE -> REVIEW`：pass-through（REVIEW 不暂停，直接输出）。
- `REVIEW -> DELIVER`：立即执行。
- `GATE -> LEARN`：本轮未通过。

**Manual 逐轮模式 (`delivery_mode=manual`, `batch_review=false`)：**
- `GATE(pass) -> REVIEW`：进入 REVIEW 状态，暂停等待用户审批。
- `REVIEW -> DELIVER`：用户 approve 当前 candidate。
- `REVIEW -> LEARN`：用户 reject 当前 candidate（标记 `skipped`）。
- `GATE -> LEARN`：本轮未通过门禁（不进入 REVIEW）。

**Manual 批量模式 (`delivery_mode=manual`, `batch_review=true`)：**
- `GATE(pass) -> LEARN`：candidate 缓存到 `review_buffer`，不立即进入 REVIEW。
- `LEARN -> REVIEW`：所有轮次结束后（达到 `max_rounds` 或无可用候选），若 `review_buffer` 非空则进入批量 REVIEW。
- `REVIEW -> DELIVER`：用户从 TopN 中选择 K 个 approve，逐个执行 DELIVER。
- `REVIEW -> DONE`：用户 skip_all 或 `review_buffer` 为空。
- `GATE -> LEARN`：本轮未通过门禁，正常进入 LEARN。

## 3. Policy Schema (YAML)

```yaml
run:
  max_rounds: 5
  max_deliveries: 3
  dry_run: false
  delivery_mode: "auto"     # auto | manual
  batch_review: false        # 仅 delivery_mode=manual 时生效
                             # false: 逐轮审批（每轮 GATE 通过后暂停等待用户）
                             # true:  批量审批（所有轮次跑完后一次性展示 TopN 供用户选择）

target:
  directions: ["后端平台", "基础架构"]
  cities: ["上海"]
  companies: []

quality:
  min_matching_score: 75
  min_evaluation_score: 78
  n_pass_required: 2
  gate_mode: "strict" # strict|simulate

channels:
  order: ["liepin", "email"]
  liepin:
    enabled: true
    submit: false
  email:
    enabled: true
    smtp_host: "smtp.example.com"
    smtp_port: 587
    username_env: "SMTP_USER"
    password_env: "SMTP_PASS"
    from: "bot@example.com"
    to: ["target@example.com"]
```

`gate_mode` 说明：
- `strict`: 必须通过 matching + evaluation + channel readiness 才计为 pass。
- `simulate`: 在 `dry_run=true` 或 submit 未开启时，readiness 仅记录不阻断，避免循环被硬性卡死。

`delivery_mode` 说明：
- `auto`：GATE 通过后自动进入 DELIVER，REVIEW 为 pass-through（行为与未引入 REVIEW 前一致）。
- `manual`：GATE 通过后进入 REVIEW 状态，系统暂停等待用户审批。用户可 approve（进入 DELIVER）或 reject（进入 LEARN 标记 skipped）。

`batch_review` 说明（仅 `delivery_mode=manual` 时生效）：
- `false`（逐轮审批）：每轮 GATE 通过后立即暂停进入 REVIEW，用户审批当前 candidate。
- `true`（批量审批）：GATE 通过的 candidate 缓存到 `review_buffer`，所有轮次结束后一次性展示 TopN 供用户批量选择。
### 2.1 Company Exclusion List（企业例外清单）

为避免在不希望投递的企业上浪费候选配额、评分成本和投递预算，policy 必须支持企业例外清单。

最小配置语义：

```yaml
filters:
  excluded_companies:
    - match: exact
      value: "示例科技有限公司"
    - match: contains
      value: "外包"
  excluded_legal_entities:
    - "某某人力资源有限公司"
```

规则：
- `excluded_companies` 用于展示名/常用名/别名过滤，支持 `exact` 与 `contains` 两种匹配模式。
- `excluded_legal_entities` 用于主体级排除，优先级高于展示名匹配。
- 若同一 candidate 同时命中方向规则与企业例外清单，必须以排除规则为准。
- 企业例外清单属于 policy 资产，不允许散落在 discovery/gate/channel 实现中硬编码。
- YAML 中的 `filters.excluded_companies` / `filters.excluded_legal_entities` 在加载阶段由 `config/loader.py` 映射到 `PolicyConfig.excluded_companies` / `PolicyConfig.excluded_legal_entities`。
- `config/validator.py` 负责校验匹配模式、空值、重复值与非法配置；业务引擎只消费已经规范化后的 `PolicyConfig`。

## 3.1 Discovery Fallback from Existing Materials
当 `job_leads` 不存在或为空时，`DISCOVER` 按以下顺序自动推导候选：

1. `jd_inputs/*.txt`：提取方向关键词、公司名、JD URL。
2. `job_profiles/*.yaml`：提取目标方向、关键词、城市约束。
3. `evidence_cards/*.yaml`：提取高频技术域与业务域信号，用于方向重排。

输出统一候选结构：`direction`, `company`, `job_url`, `confidence`, `source`。

### Discovery Filtering Order

`DISCOVER` 产出 candidate 时，必须按以下顺序处理：

1. 候选抽取（来自 `job_leads` / `jd_inputs` / `job_profiles` / `evidence_cards`）
2. 公司主体归一（company / legal entity / aliases）
3. 冲突合并（同一 `company + direction` 聚合）
4. **企业例外清单过滤**
5. 输出剩余 candidate 到后续 scoring / generation / delivery

设计意图：
- 例外清单应尽可能早执行，避免把已知不投递的企业送入后续链路。
- candidate 一旦被例外清单过滤，必须在 `run_log` 或 `candidates.json` 中留下 `excluded_by_policy` 原因，便于审计。

### Discovery Extraction Rules
- `direction`：优先 `job_profiles.keywords/must_have`，其次 `jd_inputs` 关键词，最后 `evidence_cards.stack` 高频词。
- `company`：从 `jd_inputs` 的 URL 域名、公司名模式和已知公司词典抽取；冲突时保留置信度更高项。
- `job_url`：仅接受 `http/https`，且命中招聘域名白名单或职位路径特征。
- `confidence`：`0.5 * source_quality + 0.3 * keyword_match + 0.2 * recency_signal`，范围 `[0,1]`。
- 冲突合并：同一 `company + direction` 聚合为一个 candidate，保留最高置信度 URL，并记录 `merged_sources`。
- 企业例外命中：若命中 `excluded_companies` / `excluded_legal_entities`，candidate 不得进入后续 scoring / delivery。

## 3.2 GUI Configuration Entry Points

为避免把“运行策略”与“系统运行环境”混在同一个 GUI 页面中，终版桌面信息架构要求将配置入口拆为两个正式页面：

- `Policy / 策略配置`
  - 承载 `Gate Policy`、`Exclusion List`
  - 面向“是否投、怎么过门禁、哪些企业排除”的业务规则
- `System Settings / 系统设置`
  - 承载 `Channels`、`LLM Config`
  - 面向“系统怎么连接、用哪个模型/通道、凭证是否可用”的运行环境

说明：
- 该拆分是 GUI 信息架构与实现验收边界，不强制要求底层配置切片重新合并或改名。
- sidecar/CLI 层仍可继续使用 `PolicyConfig`、`LLMConfig`、通道配置等独立切片。
- 若 GUI bridge 在首版仍使用聚合配置读取/保存接口，也必须在前端层保持 `Policy` 与 `System Settings` 两个明确入口，不得回退为单个 `Settings` 页面。

## 4. N-pass Gate Strategy
联合门禁规则（每轮）

1. Matching gate: `score_total >= min_matching_score`
   - 来源：`engines/matching/rule_scorer.py` 或已注册的 matching strategy 返回的 `MatchingReport`。
2. Evaluation gate: `scorecard_total >= min_evaluation_score`
   - 来源：`engines/evaluation/rule_evaluator.py` 或已注册的 evaluation strategy 返回的 `Scorecard`。
3. Channel readiness gate（当通道含 liepin 时启用）
   - 来源：`GateEngine` 基于当前 `run_id + round_index` 的通道产物与日志快照进行判定。
4. Company exclusion guard
   - 来源：当前 candidate 的 company / legal_entity 与 policy 中的 exclusion list 匹配结果。

readiness 执行条件：
- 若 `gate_mode=strict` 且通道启用真实 submit，则必须通过 readiness。
- 若 `gate_mode=simulate` 或仅 dry-run/check mode，则 readiness 作为观测指标写入日志，不参与 pass 计数。

company exclusion 执行条件：
- company exclusion 主要在 `DISCOVER` 阶段执行，`GATE` 仅作为兜底校验。
- 任何命中 exclusion list 的 candidate 不允许进入 `DELIVER`。
- 若因手工注入 candidate、恢复运行或兼容入口绕过了 discovery 过滤，`GateEngine` 必须返回 fail 并记录 `excluded_company` 原因。

readiness 绑定规则：
- 门禁必须基于“当前 `run_id + round_index` 的 submission 产物”判断，禁止使用“最新一次 run”作为判定来源。
- `GateEngine` 必须显式接收 `run_id` 和当前轮次的 submission artifact path，并把绑定关系写入 `run_log`。
- `GateEngine` 必须显式接收当前 candidate 的公司归一结果与 exclusion 匹配结果，避免依赖隐式全局状态。

只有当本轮三门全部通过，记为 `pass_round += 1`。
当 `pass_round >= n_pass_required` 才允许进入 `REVIEW`（manual 模式）或 `DELIVER`（auto 模式）。

## 4.1 REVIEW Stage（人工审批阶段）

REVIEW 是介于 GATE 与 DELIVER 之间的可选状态，由 `delivery_mode` 配置驱动。

### 行为规范

**Auto 模式 (`delivery_mode=auto`)：**
- REVIEW 为透明 pass-through，不暂停，直接输出当前 candidate 到 DELIVER。
- 行为与未引入 REVIEW 状态前完全一致，不影响现有 auto 流程。

**Manual 逐轮模式 (`delivery_mode=manual`, `batch_review=false`)：**
- 每轮 GATE 通过后进入 REVIEW，发布 `agent.review.pending` 事件，暂停 Agent Loop 等待用户操作。
- 展示当前轮次的单个 candidate（含匹配分数、评测分数、缺口清单、简历版本、通道信息）。
- 用户 approve → 进入 DELIVER，发布 `agent.review.resolved`（action=approve）。
- 用户 reject/skip → 进入 LEARN，发布 `agent.review.resolved`（action=reject/skip）。

**Manual 批量模式 (`delivery_mode=manual`, `batch_review=true`)：**
- GATE 通过的 candidate 在当轮不暂停，缓存到 `review_buffer`，直接进入 LEARN 继续下一轮。
- 所有轮次结束后（达到 `max_rounds` 或无可用候选），若 `review_buffer` 非空，进入批量 REVIEW。
- 展示所有缓存的 candidate（TopN），按匹配分降序排列，发布 `agent.review.pending` 事件。
- 用户可勾选多个 approve → 按选择顺序逐个执行 DELIVER。
- 用户 skip_all → 直接进入 DONE，发布 `agent.review.resolved`（action=skip_all）。
- 若 `review_buffer` 为空（所有轮次都未通过 GATE），跳过 REVIEW 直接进入 DONE。

### ReviewCandidate 数据结构

```python
@dataclass(frozen=True)
class ReviewCandidate:
    job_lead_id: str
    company: str
    position: str
    matching_score: float
    evaluation_score: float
    round_index: int              # 来自哪一轮
    resume_version: str
    job_url: str = ""
    score_breakdown: ScoreBreakdown | None = None
    gap_tasks: tuple[GapTask, ...] = ()
    gate_decision: GateDecision | None = None
```

### ReviewDecision 数据结构

```python
@dataclass(frozen=True)
class ReviewDecision:
    job_lead_id: str
    action: str                   # approve | reject | skip | skip_all
    decided_by: str
    decided_at: datetime
    note: str = ""
```

### REVIEW 相关事件类型

| 事件类型 | 触发时机 | payload 关键字段 |
|----------|----------|-----------------|
| `agent.review.pending` | 进入 REVIEW 状态 | `candidates[]`, `batch_mode` |
| `agent.review.resolved` | 用户提交审批结果 | `decisions[]`, `skipped_count` |

### REVIEW 与 GUI 的交互协议

新增 RPC 方法：

| 方法 | 方向 | 用途 |
|------|------|------|
| `run.agent.getPendingReview` | UI → sidecar | 获取当前待审批候选列表（含分数、缺口、简历版本） |
| `run.agent.submitReview` | UI → sidecar | 提交审批决策（每个 candidate 的 approve/reject/skip；批量模式支持 skip_all） |

新增事件：

| 事件 | 用途 |
|------|------|
| `agent.review.pending` | 通知 UI 进入审批等待状态，切换到审批面板 |
| `agent.review.resolved` | 审批完成，继续执行 |

### REVIEW 的 GUI 承载位置

- REVIEW 状态的 UI 内嵌在 Agent Run 页面，不新建独立页面。
- 进入 REVIEW 时，Agent Run 左栏从“N-Pass Gate / 多轮门禁”切换为“Pending Review / 待审批候选”面板。
- 审批面板展示：候选公司/职位、匹配分、评测分、缺口数、投递通道、勾选框。
- 底部操作：「Approve Selected / 批准选中」 + 「Skip All / 全部跳过」。
- 右栏保持事件流不变，展示 `agent.review.pending` / `agent.review.resolved` 事件。

## 5. Channel Abstraction

定义统一接口：

- `Channel.deliver(context) -> DeliveryResult`
- `DeliveryResult`: `status`, `channel`, `external_ref`, `detail`, `artifacts`

实现：
- `LiepinChannel`: 将 `tools/submission/run_submission.py` 的核心逻辑迁移到 `tools/channels/liepin.py`，对外提供纯 Python API；旧脚本仅在兼容期由 CLI 层转调。
- `EmailChannel`: 标准库 `smtplib` 发送邮件（简历附件 + run metadata）。

Email 通道规范：
- 凭据来源：仅环境变量（例如 `SMTP_USER`、`SMTP_PASS`），禁止硬编码。
- 附件优先级：`resume.pdf` > `resume.md`；若无 PDF，回退 Markdown 并记录 `attachment_fallback=true`。
- 最小消息体：主题（方向+公司）、正文（candidate 摘要+得分+run_id）、附件（简历与关键日志引用）。
- 失败策略：同一轮 Email 失败可重试 1 次，仍失败则标记 `channel_error` 并交由通道降级策略处理。

## 6. Data and Logging
- 运行目录：`outputs/agent_runs/<run_id>/`
- 输出：
  - `run_log.json`（状态迁移、分数、门禁结果、投递结果）
  - `rounds/<n>/`（matching/evaluation/submission 引用路径）
  - `rounds/<n>/candidates.json`（候选提取字段、confidence、冲突合并明细）

## 7. Risks and Mitigation
1. **策略过严导致无投递**：提供 policy 默认阈值与 dry-run 验证模式。
2. **通道失败**：通道隔离，单通道失败不阻断其他通道。
3. **输入线索不足**：`DISCOVER` 支持 `job_leads -> 资料自动推导 -> 手工 JD` 三级回退。

## 8. Target Architecture (Unified Core Engine v2)

> v2 修订：融合六边形领域核心、策略注册表、管道组合化、配置解聚、Result 类型、事件溯源。

### 架构分层（六边形领域核心）

依赖方向：`cli → orchestration → engines → domain ← infra`

```
┌─────────────────────────────────────────────┐
│  cli/           入口层（唯一读取 env/argv）    │
├─────────────────────────────────────────────┤
│  orchestration/ 编排层（Stage 组合调度）       │
├─────────────────────────────────────────────┤
│  engines/       引擎层（Protocol 实现）        │
│  channels/      投递通道层                    │
├─────────────────────────────────────────────┤
│  domain/        领域核心（零外部依赖）  ← 核心  │
├─────────────────────────────────────────────┤
│  infra/         基础设施层（向内依赖 domain）   │
└─────────────────────────────────────────────┘
```

### 目标目录结构

```
tools/
  domain/                    # 领域核心（零外部依赖，frozen dataclass）
    models.py               # EvidenceCard, JobProfile, MatchingReport, ResumeOutput, Scorecard
    protocols.py            # 所有 Protocol 定义（引擎接口、存储接口）
    value_objects.py        # Score, GapTask, Candidate, ScoreBreakdown 等值对象
    invariants.py           # evidence-first 守卫、事实保真校验
    result.py               # Result[T, E] 类型（Ok/Err，可恢复错误）
    events.py               # RunEvent 不可变事件定义
    run_state.py            # RunState 从事件回放重建（纯函数）
  infra/                    # 基础设施层（向内依赖 domain）
    llm/
      client.py             # LLMClient 统一实现（唯一 HTTP 调用点，原 4 处重复 → 唯一来源）
      openai_adapter.py     # OpenAI-compatible 适配器
    persistence/
      yaml_io.py            # 统一 YAML 读写（原 3 处重复 → 唯一来源）
      file_store.py         # 文件存储（证据/报告/产物）
      file_run_store.py     # RunStore 文件实现（事件追加 + 轮次快照）
    logging.py              # 结构化日志
  engines/                  # 引擎层（向内依赖 domain，可依赖 infra）
    registry.py             # EngineRegistry[T] 通用注册表（OCP 实现）
    evidence/
      rule_extractor.py     # RuleEvidenceExtractor
      llm_extractor.py      # LLMEvidenceExtractor（注入 LLMClient）
      validator.py          # 证据合规校验
      store.py              # 证据存储与检索
    matching/
      rule_scorer.py        # RuleMatchingEngine（K/D/S/Q/E/R）
      llm_matcher.py        # LLMMatchingEngine
      report_builder.py
    generation/
      template_assembler.py # TemplateAssembler（evidence-first）
      llm_rewriter.py       # LLMRewriter（受控改写）
      exporter.py           # 格式导出（md/pdf）
    evaluation/
      rule_evaluator.py     # RuleEvaluationEngine
      llm_evaluator.py      # LLMEvaluationEngine
      scorecard_builder.py
    discovery/
      discovery_engine.py   # 候选发现（三级回退）
  orchestration/            # 编排层（Stage 组合模式）
    stage.py                # Stage Protocol + StageResult + RunContext
    pipeline.py             # LinearPipeline（Stage 序列组合）
    agent_loop.py           # AgentLoop（复用 pipeline 的 Stage）
    gate_engine.py          # GateStage（独立于编排的 N-pass 门禁）
    review_stage.py          # ReviewStage（auto pass-through / manual 逐轮审批 / batch 批量审批）
    state_machine.py        # StateMachine 纯函数（10 状态迁移（含 REVIEW））
  config/                   # 配置层
    fragments.py            # LLMConfig, PathConfig, PolicyConfig, EngineSelection
    composer.py             # Composer（唯一组装点）
    loader.py               # 从 policy YAML + CLI 参数加载配置
    validator.py            # 配置合规校验
  errors/                   # 异常（仅不可恢复）
    exceptions.py           # PiProofError 及子类
    handler.py              # 错误路由（终止/LEARN/降级）
  channels/                 # 投递通道层
    base.py                 # DeliveryChannel Protocol
    liepin.py               # 猎聘通道（纯 Python）
    email.py                # Email 通道（smtplib）
  cli/                      # 薄 CLI 层
    commands/
      extract.py / match.py / generate.py / evaluate.py
      pipeline.py / agent.py
    entrypoints.py
```

### 核心分层原则

1. **`domain/`（领域核心层）** — R1 六边形领域核心
   - 零外部依赖，仅使用 Python 标准库。
   - 所有 Protocol 接口定义在此。
   - frozen dataclass 保证不可变性。
   - 包含 `Result[T, E]` 类型、不可变事件、业务不变式。

2. **`infra/`（基础设施层）** — 向内依赖 domain
   - LLM 客户端、YAML IO 各有全局唯一实现。
   - 不含任何业务逻辑。
   - RunStore 文件实现在此层。

3. **`engines/`（引擎层）** — R2 策略注册表
   - 每个引擎通过 EngineRegistry 注册，新增策略只需注册一行。
   - Rule 版与 LLM 版为两个独立实现类，不在方法体内出现 `if use_llm`。
   - 不依赖文件路径、subprocess、环境变量。

4. **`orchestration/`（编排层）** — R3 管道组合化
   - `LinearPipeline`：Stage 序列组合，驱动单次 run。
   - `AgentLoop`：复用 pipeline 的 Stage，驱动多轮循环。
   - `GateStage`：独立 Stage，不嵌入编排逻辑。

5. **`config/`（配置层）** — R4 配置解聚
   - 独立配置切片（LLMConfig / PathConfig / PolicyConfig / EngineSelection）。
   - `Composer`：唯一了解全部配置的组装点。

6. **`channels/`（投递通道层）**
   - 实现 `DeliveryChannel` Protocol，返回 `Result[DeliveryResult, ChannelFailure]`。
   - 通道失败不影响其他通道。

7. **`cli/`（入口层）**
   - 唯一负责读取 sys.argv 和环境变量。
   - 构造 `Composer`，调用编排层。

设计原则：
- 领域逻辑必须可纯单元测试，不与 IO / subprocess / 环境变量耦合。
- 新增 LLM provider 只需实现适配器并注册到 EngineRegistry，不改现有引擎。
- 新增投递通道只需实现 `DeliveryChannel` Protocol 并注册，不改编排层。
- 可恢复错误（gate_fail/channel_error）通过 Result 类型表达，不使用异常。
- 旧 CLI 入口在 Phase E 收口前保持可用，内部调用新引擎。

## 9. Core Engine Interfaces (v2)

> 所有接口定义在 `domain/protocols.py`（领域层），实现在 `engines/` 和 `infra/` 层。
> 接口通过 `typing.Protocol` 定义，实现类无需继承，只需结构匹配。
> v2 变更：GateEngine/DeliveryChannel 返回 `Result[T, E]`，新增 Stage Protocol，EngineConfig 去 Literal。

### 9.1 DiscoveryEngine
```python
class DiscoveryEngine(Protocol):
    def discover(self, request: DiscoveryRequest) -> list[Candidate]: ...

# DiscoveryRequest: target（方向/城市/公司过滤）, limits（最大候选数）, previous_feedback（上轮失败原因）
# Candidate: frozen dataclass — candidate_id, direction, company, job_url, confidence, source, merged_sources
```

### 9.2 MatchingEngine
```python
class MatchingEngine(Protocol):
    def score(self, evidence_cards: Sequence[EvidenceCard], profile: JobProfile) -> MatchingReport: ...

# 实现通过 EngineRegistry 注册：
# matching_registry.register("rule", lambda: RuleMatchingEngine())
# matching_registry.register("llm", lambda llm_client, prompt_path: LLMMatchingEngine(llm_client, prompt_path))
```

### 9.3 GenerationEngine
```python
class GenerationEngine(Protocol):
    def generate(self, report: MatchingReport, cards: Sequence[EvidenceCard],
                 version: str, config: GenerationConfig) -> ResumeOutput: ...

# GenerationConfig 必须包含：
#   jd_context: JDContext（target_direction, job_url, must_have_keywords）
#   company_context: CompanyContext（company_name, industry, company_signals）
# 无对应证据的内容禁止生成，违反时抛 FabricationGuardError
```

### 9.4 EvaluationEngine
```python
class EvaluationEngine(Protocol):
    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard: ...

# LLMEvaluationEngine：先执行规则评测，再用 LLM 补充解释层。规则分数不可被 LLM 修改。
```

### 9.5 GateEngine（返回 Result，不抛异常）
```python
class GateEngine(Protocol):
    def evaluate(self, request: GateRequest) -> Result[GateDecision, GateFailure]: ...

# GateRequest: scoring_result, evaluation_result, channel_readiness, mode(strict|simulate),
#              run_id, round_index（绑定判定源，禁止使用"最新一次 run"）
# GateDecision: frozen dataclass — pass_round, reasons, gate_snapshot
# GateFailure: frozen dataclass — reason, scores, round_index
# gate_fail 是预期的业务结果，不是异常 → 使用 Result 类型
```

### 9.6 DeliveryChannel（返回 Result，支持降级）
```python
class DeliveryChannel(Protocol):
    channel_id: str
    def deliver(self, request: DeliveryRequest) -> Result[DeliveryResult, ChannelFailure]: ...

# DeliveryRequest: candidate, resume_path, profile, metadata
# DeliveryResult: frozen dataclass — status, channel, external_ref, detail, artifact_paths
# ChannelFailure: frozen dataclass — channel, reason, retryable
# channel_error 是可降级的业务结果 → 使用 Result 类型
```

### 9.7 Stage Protocol（管道组合化）
```python
class Stage(Protocol):
    name: str
    def execute(self, context: RunContext) -> StageResult: ...

@dataclass(frozen=True)
class StageResult:
    success: bool
    data: Any
    errors: tuple[PiProofError, ...] = ()

# LinearPipeline 接受 Sequence[Stage]，AgentLoop 复用 Stage
```

### 9.7a ReviewStage Protocol（审批阶段）
```python
class ReviewStage(Stage):
    """REVIEW 阶段实现。auto 模式下为 pass-through，manual 模式下暂停等待用户审批。"""
    name: str = "REVIEW"

    def execute(self, context: RunContext) -> StageResult:
        """
        auto: 直接返回 StageResult(success=True)，所有候选进入 DELIVER
        manual + batch_review=False: 暂停，发出 agent.review.pending 事件，等待用户逐轮审批
        manual + batch_review=True: 暂停，等待所有轮次完成后批量审批
        """
        ...

@dataclass(frozen=True)
class ReviewCandidate:
    """等待审批的投递候选"""
    job_lead_id: str
    company: str
    position: str
    matching_score: float
    evaluation_score: float
    round_index: int
    resume_version: str
    job_url: str = ""
    score_breakdown: ScoreBreakdown | None = None
    gap_tasks: tuple[GapTask, ...] = ()
    gate_decision: GateDecision | None = None

@dataclass(frozen=True)
class ReviewDecision:
    """用户审批决策"""
    job_lead_id: str
    action: str           # approve | reject | skip | skip_all
    decided_by: str
    decided_at: datetime
    note: str = ""
```

### 9.8 Composer（替代 ConfigLoader）
```python
class Composer:
    """唯一了解全部配置的组装点。CLI 层构造 Composer，其他层不直接接触配置。"""
    def __init__(self, llm: LLMConfig, paths: PathConfig,
                 policy: PolicyConfig, engines: EngineSelection): ...

    def build_pipeline(self) -> LinearPipeline: ...
    def build_agent_loop(self) -> AgentLoop: ...

    @staticmethod
    def from_yaml(policy_path: str) -> "Composer": ...
```

### 9.9 EngineSelection（去 Literal，由注册表校验）
```python
@dataclass(frozen=True)
class EngineSelection:
    evidence_mode: str       # 由 EngineRegistry 在运行时校验
    matching_mode: str
    generation_mode: str
    evaluation_mode: str
    # 不再使用 Literal["rule", "llm"]，支持任意注册的策略名
```

### 9.10 RunStore（增强：支持事件回放）
```python
class RunStore(Protocol):
    def append_event(self, event: RunEvent) -> None: ...
    def save_round(self, snapshot: RoundSnapshot) -> None: ...
    def finalize(self, summary: FinalSummary) -> None: ...
    def load_events(self, run_id: str) -> Sequence[RunEvent]: ...
    def get_run_dir(self) -> Path: ...
```

## 10. Canonical Run Model

### 10.1 State
- `run_id`, `round_index`, `pass_round_count`, `delivered_count`, `current_state`, `budget_remaining`

### 10.2 Event
统一事件模型（追加写入，不回写历史）：

```json
{
  "event_id": "evt-...",
  "run_id": "...",
  "round": 2,
  "state": "GATE",
  "type": "gate.evaluated",
  "ts": "2026-03-05T15:30:00+08:00",
  "payload": {
    "matching_score": 81,
    "evaluation_score": 79,
    "readiness": "pass",
    "gate_mode": "strict",
    "pass_round_count": 2
  }
}
```

### 10.3 Idempotency
- 幂等键：`run_id + candidate_id + channel + resume_version`
- 同一幂等键已成功投递时，不重复投递，仅记录 `delivery.skipped_duplicate`。

## 11. Error Taxonomy and Boundaries
- `policy_error`: policy 缺失/非法值。
- `discovery_empty`: 无候选。
- `stage_execution_error`: 某阶段引擎或编排执行失败。
- `gate_fail`: 分数/门禁未过。
- `channel_error`: 通道投递失败。

边界规则：
- `policy_error`、`stage_execution_error`（关键阶段）可直接终止 run。
- `gate_fail` 进入 `LEARN` 并尝试下一轮。
- `channel_error` 可按通道降级继续（例如 liepin 失败后 email）。

## 12. Testing and Verification Strategy
测试分层：
1. Domain unit tests（约 70%）
   - 状态迁移、预算控制、N-pass 计数、gate_mode 行为。
2. Core contract tests（约 20%）
   - core 引擎输出契约（MatchingReport / Scorecard / DeliveryResult / RunEvent）。
   - 兼容期补充旧 CLI 回归测试，验证参数语义不变。
3. End-to-end smoke（约 10%）
   - 单次 run 的 dry-run 流程贯通。

必须覆盖场景：
- `gate_mode=strict` 与 `gate_mode=simulate` 的行为差异。
- readiness 按 `run_id` 绑定判定（多轮/并行场景下不串线）。
- generation 输入包含 `jd_context/company_context` 且可在日志中追溯。
- FabricationGuardError 与 EvidenceValidationError 的守卫行为可被测试拦截。
- `delivery_mode=auto` 时 REVIEW 为 pass-through，不暂停不等待。
- `delivery_mode=manual` + `batch_review=false` 时逐轮审批：GATE 通过后暂停，待用户 approve/reject/skip 后继续。
- `delivery_mode=manual` + `batch_review=true` 时批量审批：所有轮次跑完后一次性展示 TopN 候选供审批。
- ReviewCandidate / ReviewDecision 值对象不可变且可序列化。

质量门禁：
- 新增 domain 测试全部通过。
- `run_agent --dry-run` 可完成至少 1 轮并写入 run_log。
- AIEF L3 检查通过。

## 13. Incremental Migration and Compatibility
迁移策略采用"自下而上 + 兼容包装"方式构建 v2 架构，旧 CLI 同期保持可用，最终收口：

### 阶段划分

**Phase A（建领域与基础设施地基）**
- 建立 `tools/domain/`（models / protocols / value_objects / invariants / result / events / run_state）
- 建立 `tools/infra/llm/`、`tools/infra/persistence/`、`tools/infra/logging.py`
- 建立 `tools/config/`（fragments / composer / loader / validator）
- 建立 `tools/errors/`（exceptions / handler）
- 目标：确立六边形依赖方向；消除 4 处 LLM 客户端重复、3 处 YAML 解析重复
- 在 value_objects.py 中新增 ReviewCandidate、ReviewDecision 值对象

**Phase B（造引擎与策略注册表）**
- 实现 `tools/engines/registry.py`（EngineRegistry）
- 实现 `tools/engines/evidence/`（RuleExtractor + LLMExtractor + Validator + Store）
- 实现 `tools/engines/matching/`（RuleScorer + LLMScorer + ReportBuilder）
- 实现 `tools/engines/generation/`（TemplateAssembler + LLMRewriter + Exporter）
- 实现 `tools/engines/evaluation/`（RuleEvaluator + LLMEvaluator + ScorecardBuilder）
- 实现 `tools/engines/discovery/`（DiscoveryEngine）
- 目标：所有策略通过注册表创建；各引擎完整单元测试覆盖，不依赖 IO

**Phase C（组编排与状态流）**
- 实现 `tools/orchestration/stage.py`（Stage Protocol + StageResult + RunContext）
- 实现 `tools/orchestration/pipeline.py`（LinearPipeline，Stage 序列组合）
- 实现 `tools/orchestration/agent_loop.py`（复用 Stage 的状态机循环）
- 实现 `tools/orchestration/gate_engine.py`（GateEngine，返回 Result）
- 实现 tools/orchestration/review_stage.py（ReviewStage，auto pass-through / manual 逐轮 / batch 批量三种行为）
- 落地 `domain/events.py` + `domain/run_state.py` 的事件回放能力
- 目标：`run_agent --dry-run` 可完成至少 1 轮；auto/manual 双模式可切换；状态可由事件回放重建

**Phase D（通道与发现）**
- 实现 `tools/channels/base.py`（DeliveryChannel Protocol）
- 实现 `tools/channels/liepin.py`（纯 Python，不依赖 subprocess）
- 实现 `tools/channels/email.py`（smtplib，凭据仅从环境变量读取）
- 完成 `tools/engines/discovery/discovery_engine.py`（job_leads → jd_inputs → evidence_cards 三级回退）
- 完成通道 Result 化与降级策略（liepin 失败后降级 email）

**Phase E（收口）**
- 实现 `tools/cli/`（薄 CLI 层，调用新 core）
- 旧 CLI（`run_pipeline.py` 等）内部转调 `Composer` + 新编排层，保持参数兼容
- RunStore 文件实现 + 幂等键实现
- 全量测试（domain 单测 / 引擎单测 / end-to-end dry-run）
- auto/manual/batch 三种审批模式的 ReviewStage 行为测试
- 更新 README 与 tools/README.md
- AIEF L3 检查通过后移除旧实现
- 所有新增能力遵循 TDD：先写失败测试，再写生产代码；测试失败阻断合并/收口

### 兼容约束
- `tools/run_pipeline.py`、`tools/run_generation.py`、`tools/submission/run_submission.py` 的 CLI 参数语义在 Phase E 完成前保持不破坏。
- 新增能力通过 `tools/run_agent.py` 启用，不强制改变现有用户入口。
- 旧脚本移除前必须通过 end-to-end 回归测试。

### 实施计划入口
- 详细实施顺序、文件级拆分与测试矩阵见 `AIEF/docs/plans/autonomous-agent-delivery-loop-v2.md`
