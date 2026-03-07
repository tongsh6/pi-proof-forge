# PiProofForge 核心 Pipeline 规范

**状态**: active  
**版本**: v1.0  
**创建日期**: 2026-03-02  
**所有者**: pi-proof-forge team

---

## 概述

PiProofForge 是一个 evidence-first 框架，将原始工作材料（日志、PR、报告、截图等）转为结构化证据（Evidence Cards），再通过可解释匹配生成事实保真的目标文档（简历等）。

---

## 核心实体规范

### Evidence Card

```yaml
schema: evidence_card_v1
required_fields:
  - id          # 唯一标识，格式：ec-YYYY-MM-DD-NNN
  - title       # 简短描述
  - raw_source  # 原始材料路径或引用
  - results     # 可量化的成果（必填，否则不进入候选池）
  - artifacts   # 关联产出物（必填，否则不进入候选池）
optional_fields:
  - tags        # 技能标签
  - period      # 时间范围
  - context     # 背景说明
```

**约束**：`results` 或 `artifacts` 任意一项缺失，该 Evidence Card 不进入匹配候选池。

### Job Profile

```yaml
schema: job_profile_v1
required_fields:
  - id          # 格式：jp-YYYY-NNN
  - title       # 岗位名称
  - keywords    # 关键词列表
  - level       # 级别信号（junior/mid/senior/staff）
optional_fields:
  - tone        # 语气偏好
  - must_have   # 硬性要求
  - nice_to_have # 加分项
```

### Matching Report

```yaml
schema: matching_report_v1
required_fields:
  - job_profile_id    # 关联岗位
  - evidence_cards    # 入选证据卡列表（含分项得分）
  - gap_tasks         # 缺口任务列表
  - score_breakdown   # 各维度得分（必须可解释）
```

---

## Pipeline 阶段规范

### 阶段 1：证据提炼（Evidence Extraction）

**输入**: 原始材料文件（txt/md/pdf）  
**输出**: Evidence Cards（YAML 格式）  
**工具**: `tools/run_evidence_extraction.py`（推荐入口） / `tools/extract_evidence.py`（底层规则脚本）  
**约束**:
- 不得推断或补充原材料中没有的信息
- 每个 Evidence Card 必须有明确的 `raw_source` 引用

### 阶段 2：匹配评分（Matching & Scoring）

**输入**: Evidence Cards + Job Profile  
**输出**: Matching Report  
**工具**: pipeline 内部逻辑  
**约束**:
- 所有评分维度必须有对应证据支撑
- 缺口任务必须明确列出（不得静默忽略）

### 阶段 3：文档生成（Generation）

**输入**: Matching Report + 选定的 Evidence Cards  
**输出**: 目标文档（markdown/pdf）  
**约束**:
- 严禁生成无证据支撑的内容
- 语气调整不改变事实

### 阶段 4：质量评估（Evaluation）

**输入**: 生成文档 + 原始证据  
**输出**: 质量评分报告  
**约束**:
- 每项质量分必须可追溯到具体检查点

### Agent Loop 扩展阶段（用于 Autonomous Agent）

以下阶段属于 Agent 编排扩展，不改变核心 pipeline 的 evidence-first 约束：

- `DISCOVER`：从 `job_leads` / `jd_inputs` / `evidence_cards` 推导候选方向与 JD
- `GATE`：联合判定 matching / evaluation / channel readiness
- `DELIVER`：通过通道执行投递
- `LEARN`：根据本轮失败原因调整下一轮输入与策略

约束：
- 扩展阶段不得绕过 Evidence Card 校验与事实保真约束
- 所有投递与门禁结论必须写入可追溯 run log
- policy 必须支持企业例外清单（company exclusion list），用于排除不应进入投递链路的目标企业
- 企业例外清单应在 `DISCOVER` 阶段主过滤，在 `GATE` 阶段做兜底校验

---

## CLI 接口规范

```bash
# 证据提炼（推荐入口）
python3 tools/run_evidence_extraction.py --input <raw_file>

# 完整 pipeline
python3 tools/run_pipeline.py \
  --raw tools/sample_raw.txt \
  --job-profile job_profiles/jp-2026-001.yaml

# Agent loop（统一核心引擎入口）
python3 tools/run_agent.py --policy profiles/agent_policy.example.yaml --dry-run
```

说明：
- `tools/run_evidence_extraction.py` 是面向工作流和文档约定的推荐入口；`tools/extract_evidence.py` 保留为底层规则实现/兼容脚本。
- `tools/run_pipeline.py` 属于兼容入口，在迁移期内部转调 `tools/config/composer.py` 组装出的新 pipeline / orchestration 层。
- 新增能力优先通过 `tools/run_agent.py` 与 `tools/cli/entrypoints.py` 暴露。

---

## 变更流程

1. 使用 `/opsx:propose` 提交变更提案
2. 通过 brainstorming skill 细化设计
3. 通过 writing-plans skill 生成实现计划
4. TDD 实现（test-driven-development skill）
5. code review（requesting-code-review skill）
6. 使用 `/opsx:archive` 归档已实施变更

---

## 统一核心引擎架构规范

> 本节由架构审核确定（v2，2026-03-06 审核修订），适用于所有新增模块与重构变更。
> v2 修订基于六边形领域核心、策略注册表、管道组合化、配置解聚、Result 类型、事件溯源六项架构改进。

### 核心原则

1. **零 subprocess**：所有阶段通过纯 Python API 调用，禁止 subprocess 串联。
2. **DRY**：LLM 客户端、YAML 解析、配置管理、错误处理各有唯一实现，不得在各阶段重复。
3. **OCP**：规则/LLM 实现通过策略注册表（EngineRegistry）动态注入，新增策略只需注册，不改已有代码。禁止在业务逻辑中出现 `if use_llm` 分支。
4. **可测试**：领域逻辑不依赖 IO 与第三方服务，可独立单元测试。
5. **依赖倒置（DIP）**：所有模块向领域层"内指"，领域层零外部依赖。Protocol 定义在领域层，实现在外层。
6. **组合优于继承**：Pipeline 由 Stage 对象组合而成，agent_loop 复用 pipeline 的 Stage，而非继承。
7. **接口隔离（ISP）**：各组件只接收自己需要的配置切片，禁止传递上帝 Config 对象。

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
    result.py               # Result[T, E] 类型（Ok/Err，用于可恢复错误）
    events.py               # RunEvent 不可变事件定义
    run_state.py            # RunState 从事件回放重建
  infra/                    # 基础设施层（向内依赖 domain）
    llm/
      client.py             # LLMClient 统一实现（唯一 HTTP 调用点）
      openai_adapter.py     # OpenAI-compatible 适配器
    persistence/
      yaml_io.py            # 统一 YAML 读写（唯一实现）
      file_store.py         # 文件存储（证据/报告/产物）
      file_run_store.py     # RunStore 文件实现（事件追加写入 + 轮次快照）
    logging.py              # 结构化日志
  engines/                  # 引擎层（向内依赖 domain，可依赖 infra）
    registry.py             # EngineRegistry[T] 通用注册表
    evidence/
      rule_extractor.py     # RuleEvidenceExtractor
      llm_extractor.py      # LLMEvidenceExtractor（注入 LLMClient）
      validator.py           # 证据合规校验（强制 results/artifacts）
      store.py               # 证据存储与检索
    matching/
      rule_scorer.py        # RuleMatchingEngine（K/D/S/Q/E/R）
      llm_matcher.py        # LLMMatchingEngine（注入 LLMClient）
      report_builder.py
    generation/
      template_assembler.py # TemplateAssembler（evidence-first，无证据不生成）
      llm_rewriter.py       # LLMRewriter（受控改写，不引入新事实）
      exporter.py           # 格式导出（md/pdf）
    evaluation/
      rule_evaluator.py     # RuleEvaluationEngine（coverage/quant/clarity/length/citation）
      llm_evaluator.py      # LLMEvaluationEngine（先规则后解释，规则分数不可被 LLM 修改）
      scorecard_builder.py
    discovery/
      discovery_engine.py   # 候选发现（三级回退）
  orchestration/            # 编排层（Stage 组合模式）
    stage.py                # Stage Protocol + StageResult + RunContext
    pipeline.py             # LinearPipeline（Stage 序列组合）
    agent_loop.py           # AgentLoop（复用 pipeline 的 Stage，驱动状态机循环）
    gate_engine.py          # GateStage（独立于编排的 N-pass 门禁）
    state_machine.py        # StateMachine 纯函数（9 状态迁移）
  config/                   # 配置层
    fragments.py            # LLMConfig, PathConfig, PolicyConfig, EngineSelection（独立切片）
    composer.py             # Composer（唯一了解全部配置的组装点）
    loader.py               # 从 policy YAML + CLI 参数加载配置
    validator.py            # 配置合规校验
  errors/                   # 异常与错误处理
    exceptions.py           # PiProofError 及不可恢复子类
    handler.py              # 错误路由（终止/LEARN/降级）
  channels/                 # 投递通道层
    base.py                 # DeliveryChannel Protocol
    liepin.py               # 猎聘通道（纯 Python）
    email.py                # Email 通道（smtplib）
  cli/                      # 薄 CLI 层，仅解析参数 → 构造 Composer → 调用编排
    commands/
      extract.py / match.py / generate.py / evaluate.py
      pipeline.py / agent.py
    entrypoints.py          # 统一 CLI 注册入口
```

### 核心引擎接口规范（Protocol 定义在 domain/protocols.py）

```python
# domain/protocols.py — 所有接口定义在领域层

class EvidenceExtractor(Protocol):
    def extract(self, raw_material: RawMaterial) -> EvidenceCard: ...

class MatchingEngine(Protocol):
    def score(self, evidence_cards: Sequence[EvidenceCard], profile: JobProfile) -> MatchingReport: ...

class GenerationEngine(Protocol):
    def generate(self, report: MatchingReport, cards: Sequence[EvidenceCard],
                 version: str, config: GenerationConfig) -> ResumeOutput: ...

class EvaluationEngine(Protocol):
    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard: ...

class DiscoveryEngine(Protocol):
    def discover(self, request: DiscoveryRequest) -> list[Candidate]: ...
    # candidate 必须在输出前完成 company/legal_entity 归一、冲突合并与企业例外清单过滤

class GateEngine(Protocol):
    def evaluate(self, request: GateRequest) -> Result[GateDecision, GateFailure]: ...
    # 若 candidate 命中企业例外清单，即使绕过 discovery 过滤，也必须返回 fail 并阻止进入 DELIVER

class DeliveryChannel(Protocol):
    channel_id: str
    def deliver(self, request: DeliveryRequest) -> Result[DeliveryResult, ChannelFailure]: ...

class RunStore(Protocol):
    def append_event(self, event: RunEvent) -> None: ...
    def save_round(self, snapshot: RoundSnapshot) -> None: ...
    def finalize(self, summary: FinalSummary) -> None: ...
    def load_events(self, run_id: str) -> Sequence[RunEvent]: ...
    def get_run_dir(self) -> Path: ...
```

### 策略注册表规范（OCP 实现）

```python
# engines/registry.py — 新增策略只需注册，不改已有代码
T = TypeVar("T")

class EngineRegistry(Generic[T]):
    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., T]] = {}

    def register(self, name: str, factory: Callable[..., T]) -> None:
        self._factories[name] = factory

    def create(self, name: str, **kwargs: Any) -> T:
        if name not in self._factories:
            raise ValueError(f"Unknown engine: {name}. Available: {list(self._factories)}")
        return self._factories[name](**kwargs)

# 各引擎自注册示例
evidence_registry = EngineRegistry[EvidenceExtractor]()
evidence_registry.register("rule", lambda: RuleEvidenceExtractor())
evidence_registry.register("llm", lambda llm_client, prompt_path:
    LLMEvidenceExtractor(llm_client, prompt_path))
# 扩展新策略：只需一行注册
# evidence_registry.register("anthropic", lambda client: AnthropicExtractor(client))
```

### 管道组合规范（Stage 模式）

```python
# orchestration/stage.py
@dataclass(frozen=True)
class StageResult:
    success: bool
    data: Any
    errors: tuple[PiProofError, ...] = ()

class Stage(Protocol):
    name: str
    def execute(self, context: RunContext) -> StageResult: ...

# orchestration/pipeline.py — 线性管道：Stage 的组合
class LinearPipeline:
    def __init__(self, stages: Sequence[Stage]):
        self.stages = stages

    def run(self, context: RunContext) -> PipelineResult:
        for stage in self.stages:
            result = stage.execute(context)
            if not result.success:
                return PipelineResult(failed_at=stage.name, error=result.errors)
            context = context.with_update(stage.name, result.data)
        return PipelineResult(success=True, context=context)

# orchestration/agent_loop.py — 循环编排：复用 Stage，不重写业务逻辑
class AgentLoop:
    def __init__(self, pipeline: LinearPipeline, gate: Stage,
                 discovery: Stage, learn: Stage, policy: PolicyConfig):
        self.pipeline = pipeline  # 组合，不继承
        self.gate = gate
        # ...
```

### 领域模型规范（不可变值对象）

```python
# domain/models.py — frozen=True 保证不可变

@dataclass(frozen=True)
class EvidenceCard:
    id: str
    title: str
    raw_source: str
    results: tuple[str, ...]
    artifacts: tuple[str, ...]
    tags: tuple[str, ...] = ()
    period: str = ""
    context: str = ""

    def is_eligible(self) -> bool:
        """evidence-first 守卫：results/artifacts 缺失不进入候选池"""
        return bool(self.results) and bool(self.artifacts)

@dataclass(frozen=True)
class JobProfile:
    id: str
    title: str
    keywords: tuple[str, ...]
    level: str
    must_have: tuple[str, ...] = ()
    nice_to_have: tuple[str, ...] = ()

@dataclass(frozen=True)
class MatchingReport:
    job_profile_id: str
    evidence_cards: tuple[str, ...]     # card IDs
    score_breakdown: ScoreBreakdown
    gap_tasks: tuple[GapTask, ...]
```

### 错误处理规范（异常 + Result 双轨）

不可恢复错误使用异常，可恢复错误使用 `Result[T, E]` 类型：

```python
# domain/result.py — 可恢复错误的显式表达
@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

@dataclass(frozen=True)
class Err(Generic[E]):
    error: E

Result = Ok[T] | Err[E]

# 异常 vs Result 的边界
# | 场景                   | 处理方式                                |
# |------------------------|----------------------------------------|
# | gate_fail              | Result[GateDecision, GateFailure]      |
# | channel_error          | Result[DeliveryResult, ChannelFailure] |
# | discovery_empty        | Result[list[Candidate], DiscoveryEmpty]|
# | FabricationGuardError  | 异常 — 不可恢复，终止                    |
# | EvidenceValidationError| 异常 — 不可恢复，终止                    |
# | PolicyError            | 异常 — 配置错误，终止                    |

# errors/exceptions.py — 仅保留不可恢复异常
class PiProofError(Exception):
    """所有不可恢复业务异常的基类"""
    category: ErrorCategory
    recoverable: bool = False

class EvidenceValidationError(PiProofError):
    """证据不合规（缺 results/artifacts）"""
    category = ErrorCategory.EVIDENCE

class FabricationGuardError(PiProofError):
    """生成阶段检测到无证据内容"""
    category = ErrorCategory.GENERATION

class PolicyError(PiProofError):
    """配置错误"""
    category = ErrorCategory.POLICY
```

### 配置解聚规范（ISP）

各组件只接收自己需要的配置切片，禁止传递上帝 Config：

```python
# config/fragments.py — 独立配置切片
@dataclass(frozen=True)
class LLMConfig:
    model: str
    base_url: str
    api_key: str
    timeout: int = 120

@dataclass(frozen=True)
class PathConfig:
    evidence_dir: Path
    output_dir: Path
    profile_dir: Path

@dataclass(frozen=True)
class PolicyConfig:
    max_rounds: int
    max_deliveries: int
    gate_mode: str           # strict | simulate
    n_pass_required: int
    excluded_companies: tuple[CompanyExclusionRule, ...] = ()
    excluded_legal_entities: tuple[str, ...] = ()

@dataclass(frozen=True)
class CompanyExclusionRule:
    match: str               # exact | contains
    value: str

@dataclass(frozen=True)
class EngineSelection:
    evidence_mode: str       # 由 EngineRegistry 校验，不用 Literal
    matching_mode: str
    generation_mode: str
    evaluation_mode: str

# config/composer.py — 唯一了解全部配置的组装点
class Composer:
    """组装所有组件。CLI 层构造 Composer，其他层不直接接触配置。"""
    def __init__(self, llm: LLMConfig, paths: PathConfig,
                 policy: PolicyConfig, engines: EngineSelection): ...

    def build_pipeline(self) -> LinearPipeline: ...
    def build_agent_loop(self) -> AgentLoop: ...

    @staticmethod
    def from_yaml(policy_path: str) -> "Composer": ...
```

企业例外清单规范：

- `excluded_companies` 用于展示名/常用名/别名过滤，支持 `exact` 与 `contains`
- `excluded_legal_entities` 用于主体级排除，优先级高于展示名匹配
- 命中例外清单的 candidate 不得进入 scoring / generation / delivery
- 被过滤 candidate 必须在 `run_log` 或 `rounds/<n>/candidates.json` 中记录 `excluded_by_policy` 原因

### 事件溯源规范（RunStore 增强）

```python
# domain/events.py — 不可变事件
@dataclass(frozen=True)
class RunEvent:
    event_id: str
    run_id: str
    round_index: int
    timestamp: datetime
    event_type: str
    payload: Mapping[str, Any]

# domain/run_state.py — 从事件回放重建状态（支持断点续跑）
@dataclass(frozen=True)
class RunState:
    run_id: str
    current_state: AgentState
    round_index: int
    pass_count: int
    delivered_count: int

    @staticmethod
    def replay(events: Sequence[RunEvent]) -> "RunState":
        state = RunState.initial(events[0].run_id)
        for event in events:
            state = state.apply(event)
        return state

    def apply(self, event: RunEvent) -> "RunState":
        """纯函数：旧状态 + 事件 → 新状态"""
        ...
```

---

## 参考文档

- 业务域：`AIEF/context/business/DOMAIN.md`
- 架构：`AIEF/context/tech/architecture.md`
- Evidence Card Schema：`AIEF/context/tech/SCHEMA_EVIDENCE_CARD.md`
- Job Profile Schema：`AIEF/context/tech/SCHEMA_JOB_PROFILE.md`
- 生成规范：`AIEF/context/tech/GENERATION.md`
- 评估规范：`AIEF/context/tech/EVALUATION.md`
