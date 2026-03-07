# autonomous-agent-delivery-loop v2 实施计划

> 状态：draft
> 依据：`openspec/changes/autonomous-agent-delivery-loop/design.md`
> 范围：仅实现前计划，不进入开发

## 1. 目标

把当前扁平脚本式 `tools/` 渐进迁移到 v2 架构：

- `domain/` 作为零依赖领域核心
- `infra/` 作为唯一基础设施实现层
- `engines/` 通过 `EngineRegistry` 管理策略实现
- `orchestration/` 通过 `Stage` 组合统一 pipeline 与 agent loop
- `config/Composer` 作为唯一组装点
- `Result[T, E]` + 事件回放用于处理可恢复错误与运行恢复

## 2. 实施顺序（推荐）

### Milestone M1 - 建立稳定内核

目标：先把依赖方向和基础抽象锁定，避免后续重复返工。

交付：

1. `tools/domain/`
   - `models.py`
   - `value_objects.py`
   - `protocols.py`
   - `invariants.py`
   - `result.py`
   - `events.py`
   - `run_state.py`
2. `tools/infra/`
   - `llm/client.py`
   - `persistence/yaml_io.py`
   - `logging.py`
3. `tools/config/`
   - `fragments.py`
   - `loader.py`
   - `validator.py`
   - `composer.py`
4. `tools/errors/`
   - `exceptions.py`
   - `handler.py`

验收：

- 重复的 `post_json` / `extract_content` / `parse_simple_yaml` 已有唯一实现位置
- `domain/` 不依赖 `infra/`、`engines/`、`cli/`
- `Composer` 可创建最小空 pipeline
- 核心不可变模型测试通过

### Milestone M2 - 引擎迁移与去分支化

目标：把现有四阶段逻辑迁移为独立引擎，并彻底消除业务层 `if use_llm`。

本里程碑同时纳入 issue #1：企业例外清单（company exclusion list）的 discovery 主过滤能力。

时间线说明：

- M1 后半只落地企业例外清单的配置语义与加载映射（`PolicyConfig + loader + validator`）
- M2 才落地 `DiscoveryEngine` 的主过滤实现
- M3 再补 `GateEngine` 的兜底校验

交付：

1. `tools/engines/registry.py`
2. `tools/engines/evidence/`
3. `tools/engines/matching/`
4. `tools/engines/generation/`
5. `tools/engines/evaluation/`
6. `tools/engines/discovery/`
   - company/legal entity 归一
   - 企业例外清单过滤（`excluded_companies` / `excluded_legal_entities`）
   - `excluded_by_policy` 审计记录

验收：

- 四大引擎都可通过 registry 创建
- 新增一个 fake strategy 只需注册，无需改动既有创建逻辑
- 业务引擎目录内不再出现 `if use_llm`
- Generation 守卫测试可拦截无证据内容
- discovery 已能在 candidate 输出前过滤掉命中企业例外清单的公司

### Milestone M3 - 编排统一化

目标：统一线性 pipeline 和 agent loop 的阶段模型，减少重复编排逻辑。

本里程碑补足 issue #1 的 gate 兜底：即使 candidate 绕过 discovery 过滤，仍不得进入 `DELIVER`。

交付：

1. `tools/orchestration/stage.py`
2. `tools/orchestration/pipeline.py`
3. `tools/orchestration/state_machine.py`
4. `tools/orchestration/gate_engine.py`
5. `tools/orchestration/agent_loop.py`
6. `tools/run_agent.py`

验收：

- `LinearPipeline` 以 `Sequence[Stage]` 组合驱动单次 run
- `AgentLoop` 复用 Stage，不重复实现 extraction/matching/generation/evaluation 阶段逻辑
- `GateEngine` 返回 `Result[GateDecision, GateFailure]`
- `run_agent --dry-run` 可完成至少 1 轮
- `GateEngine` 对命中企业例外清单的 candidate 返回 `excluded_company`，阻止进入 `DELIVER`

### Milestone M4 - 通道、运行存储与恢复

目标：补齐多通道投递、事件日志和恢复能力。

交付：

1. `tools/channels/base.py`
2. `tools/channels/liepin.py`
3. `tools/channels/email.py`
4. `tools/infra/persistence/file_run_store.py`

验收：

- `DeliveryChannel.deliver()` 返回 `Result[DeliveryResult, ChannelFailure]`
- liepin 失败可降级到 email
- `RunStore.load_events(run_id)` 可回放为 `RunState`
- 日志目录满足 `outputs/agent_runs/<run_id>/` 结构要求

### Milestone M5 - CLI 收口与兼容迁移

目标：切换用户入口到底层新架构，同时保持旧命令兼容。

交付：

1. `tools/cli/commands/*`
2. `tools/cli/entrypoints.py`
3. 旧入口转调：
   - `tools/run_pipeline.py`
   - `tools/run_evidence_extraction.py`
   - `tools/run_matching_scoring.py`
   - `tools/run_generation.py`
   - `tools/run_evaluation.py`

验收：

- 旧 CLI 参数语义不破坏
- 旧 CLI 内部不再含核心业务逻辑
- 新增能力优先从 `tools/run_agent.py` 与 `tools/cli/entrypoints.py` 暴露

## 3. 实施依赖关系

```text
M1 -> M2 -> M3 -> M4 -> M5
```

细化依赖：

- `domain/protocols.py` 先于所有引擎实现
- `infra/llm/client.py` 与 `infra/persistence/yaml_io.py` 先于 LLM/YAML 迁移
- `EngineRegistry` 先于四大引擎注册
- `Stage` 先于 `LinearPipeline` 与 `AgentLoop`
- `RunEvent` / `RunState` 先于 `file_run_store.py`
- `Composer` 先于 CLI 收口

## 4. 风险与缓解

### 风险 1：一次改动过大导致回归面过宽

缓解：

- 每个里程碑都保留旧 CLI 兼容层
- 每完成一个里程碑就补对应回归测试

### 风险 2：Result 类型与异常边界不清

缓解：

- 先在 Gate / Channel / Discovery 三处落地 Result
- 仅 `EvidenceValidationError` / `FabricationGuardError` / `PolicyError` 保留为异常

### 风险 3：事件溯源过度设计

缓解：

- 先实现最小事件回放能力，只覆盖 `RunState` 恢复
- 不在首轮引入复杂 CQRS 或多存储后端

### 风险 4：企业例外清单只做单层过滤，导致绕过

缓解：

- discovery 做主过滤，尽早节省候选/评分/投递成本
- gate 做兜底过滤，拦住手工注入、恢复运行、兼容入口绕过等情况

## 5. Definition of Done

满足以下条件才算 v2 架构迁移完成：

1. 领域层零外部依赖
2. 重复 LLM/YAML 实现已归一
3. 业务引擎层不再出现 `if use_llm`
4. pipeline 与 agent loop 共用 Stage 抽象
5. gate/channel/discovery 使用 Result 类型表示可恢复错误
6. run 状态可由事件回放恢复
7. 旧 CLI 兼容层通过回归测试
8. `run_agent --dry-run` 至少完成 1 轮并产出日志
9. 企业例外清单已在 discovery 主过滤 + gate 兜底两层生效

## 6. 建议开发节奏

- 第 1 周：M1
- 第 2 周：M2
- 第 3 周：M3
- 第 4 周：M4 + M5

针对 issue #1 的节奏：

- 第 1 周后半：配置语义与 loader/validator 映射
- 第 2 周：Discovery 主过滤
- 第 3 周：Gate 兜底

如果需要降低风险，建议把 M4 的事件回放能力拆成：

- M4a：先落 `file_run_store.py` 追加写入
- M4b：再补 `RunState.replay(events)`

## 7. 文件级实施拆分

### Slice 1 - 领域模型与公共基础

优先文件：

- `tools/domain/models.py`
- `tools/domain/value_objects.py`
- `tools/domain/protocols.py`
- `tools/domain/result.py`
- `tools/infra/llm/client.py`
- `tools/infra/persistence/yaml_io.py`

完成标志：

- 旧脚本中的重复 `TypedDict` / `post_json` / `parse_simple_yaml` 已有可迁移目标
- 新文件具备最小测试覆盖
- 逐文件顺序、测试优先级与完成判据见 `docs/plans/m1-slice-1-breakdown.md`

### Slice 2 - 四大引擎最小可运行版

优先文件：

- `tools/engines/evidence/rule_extractor.py`
- `tools/engines/matching/rule_scorer.py`
- `tools/engines/generation/template_assembler.py`
- `tools/engines/evaluation/rule_evaluator.py`
- `tools/engines/registry.py`
- `tools/engines/discovery/discovery_engine.py`

完成标志：

- rule 路径可在不接触 CLI 的情况下端到端串起
- 四大引擎都通过 registry 创建
- discovery 已支持企业例外清单过滤，并留下 `excluded_by_policy` 记录

### Slice 3 - 编排最小闭环

优先文件：

- `tools/orchestration/stage.py`
- `tools/orchestration/pipeline.py`
- `tools/config/composer.py`
- `tools/run_agent.py`

完成标志：

- 可通过 `Composer` 组装最小 pipeline
- `run_agent --dry-run` 能跑一轮 rule-only 流程
- 企业例外清单命中时，即使绕过 discovery，gate 仍能阻止进入 `DELIVER`

### Slice 4 - LLM 与通道扩展

优先文件：

- `tools/engines/*/llm_*.py`
- `tools/channels/base.py`
- `tools/channels/email.py`
- `tools/channels/liepin.py`

完成标志：

- LLM 策略通过注册表接入
- 通道错误通过 Result 进入降级逻辑

### Slice 5 - 事件日志与兼容包装

优先文件：

- `tools/domain/events.py`
- `tools/domain/run_state.py`
- `tools/infra/persistence/file_run_store.py`
- 旧 CLI 包装层

完成标志：

- run 状态可回放恢复
- 旧 CLI 对外语义不变，但内部已转调新架构

## 8. 测试矩阵

| 层 | 必测对象 | 重点 |
|---|---|---|
| domain | models / value_objects / result / run_state | 不可变性、比较、回放正确性 |
| infra | llm client / yaml io / file run store | 唯一实现、边界输入、错误处理 |
| engines | evidence / matching / generation / evaluation / discovery | 规则行为、LLM 注入、registry 创建 |
| orchestration | stage / pipeline / state_machine / agent_loop | 组合执行、状态迁移、Result 消费 |
| channels | liepin / email | 重试、降级、artifact 记录 |
| compatibility | legacy CLI wrappers | 参数语义与输出不破坏 |

## 9. 首个实现批次建议

为了最快获得可验证价值，建议第一个开发批次只做以下内容：

1. `domain/` 最小模型与协议
2. `infra/llm/client.py` 与 `infra/persistence/yaml_io.py`
3. 四个 rule 引擎
4. `EngineRegistry`
5. `Stage` + `LinearPipeline`
6. `Composer`
7. `run_agent.py --dry-run` 的 rule-only 版本

这个批次完成后，就能验证 v2 架构骨架是否成立，而不必等到 LLM、通道、事件回放全部完成。

## 10. 明确延期项

以下内容可以在 v2 骨架稳定后再接入，避免首轮范围失控：

- Anthropic / 本地模型 adapter
- 完整 PDF exporter
- 完整事件溯源查询能力（除回放外）
- 多 Run 并发协调
- GUI 对 v2 pipeline 的直接接入

说明：

- issue #1（企业例外清单）不属于延期项；它应在 `PolicyConfig + DiscoveryEngine + GateEngine` 路径中按计划实现。
