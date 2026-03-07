# M1 / Slice 1 逐文件实施清单

> 状态：draft
> 对应里程碑：`docs/plans/autonomous-agent-delivery-loop-v2.md` → M1 / Slice 1
> 范围：仅实现前拆分，不进入开发

## 1. 目标

在不触碰四大业务引擎迁移的前提下，先建立 v2 架构的最小稳定内核：

- 领域模型与协议先落地
- 重复的 LLM / YAML 实现先统一
- Result 类型与不可恢复异常边界先锁定
- Composer 能组装最小空 pipeline

这一步完成后，后续引擎迁移将不再反复修改基础抽象。

## 2. 实施顺序（严格推荐）

```text
1. domain/result.py
2. domain/value_objects.py
3. domain/models.py
4. domain/protocols.py
5. domain/invariants.py
6. domain/events.py
7. domain/run_state.py
8. infra/llm/client.py
9. infra/persistence/yaml_io.py
10. infra/logging.py
11. errors/exceptions.py
12. errors/handler.py
13. config/fragments.py
14. config/validator.py
15. config/loader.py
16. config/composer.py
```

原因：

- `result.py` 是可恢复错误表达的基础，协议会依赖它
- `value_objects.py` 先于 `models.py`，避免模型中出现重复小类型
- `protocols.py` 必须建立在模型和 Result 之上
- `invariants.py` 建立在模型之上，但早于引擎实现
- `events.py` / `run_state.py` 只依赖领域层，可先独立完成
- `infra/*` 依赖领域协议与模型
- `errors/*` 需要先知道领域约束和可恢复/不可恢复边界
- `config/*` 最后收束，因为它会引用多个协议和基础设施对象

## 3. 逐文件拆分

### 3.1 `tools/domain/result.py`

职责：

- 定义 `Ok[T]` / `Err[E]` / `Result[T, E]`
- 提供最小辅助方法或约定（不做复杂 monad 封装）

先写测试：

1. `Ok` / `Err` 可实例化且可比较
2. `Result` 能被类型标注使用
3. `repr` / `dataclass` 行为稳定

完成判据：

- 不引入运行时复杂 helper
- 只提供最小表达能力，避免过度设计

### 3.2 `tools/domain/value_objects.py`

职责：

- 定义 `Score`、`GapTask`、`Candidate`、`GateDecision`、`DeliveryResult`、`GateFailure`、`ChannelFailure`
- 全部为 frozen dataclass

先写测试：

1. 值对象可比较
2. 值对象不可变
3. `Candidate` 聚合字段完整（`merged_sources` 等）

完成判据：

- 不出现 dict 形态的匿名返回值
- 不把大对象职责塞进单个 value object

### 3.3 `tools/domain/models.py`

职责：

- 定义核心模型：`EvidenceCard`、`JobProfile`、`MatchingReport`、`ResumeOutput`、`Scorecard`

先写测试：

1. `EvidenceCard.is_eligible()` 在缺 `results`/`artifacts` 时返回 `False`
2. 所有模型默认不可变
3. `MatchingReport` 和 `Scorecard` 可表达最小必要字段

完成判据：

- 模型字段与 openspec 保持一致
- 不在模型里引入 IO、Path 读取或环境变量

### 3.4 `tools/domain/protocols.py`

职责：

- 定义 `EvidenceExtractor`、`MatchingEngine`、`GenerationEngine`、`EvaluationEngine`
- 定义 `DiscoveryEngine`、`GateEngine`、`DeliveryChannel`、`RunStore`、`Stage`

先写测试：

1. 假实现类可满足 Protocol
2. Gate / Channel 的返回值确认为 `Result[...]`
3. `Stage.execute()` 只接收 context，返回 `StageResult`

完成判据：

- Protocol 不引用 `infra/*` 具体实现
- 所有接口都可以由 fake 实现替代

### 3.5 `tools/domain/invariants.py`

职责：

- 集中定义 evidence-first 与 no-fabrication 约束
- 区分返回布尔值的校验与抛异常的守卫

先写测试：

1. 缺失 `results`/`artifacts` 的 evidence 被判为不合规
2. 无证据生成内容会触发 fabrication guard

完成判据：

- 不把守卫散落到各引擎内部

### 3.6 `tools/domain/events.py`

职责：

- 定义不可变 `RunEvent`
- 统一事件最小字段：`event_id`、`run_id`、`round_index`、`event_type`、`timestamp`、`payload`

先写测试：

1. 事件不可变
2. payload 可承载最小序列化结构

### 3.7 `tools/domain/run_state.py`

职责：

- 定义 `RunState`
- 实现 `RunState.replay(events)` 与 `apply(event)`

先写测试：

1. 空初始状态可创建
2. `round.started` / `gate.passed` / `delivery.completed` 能正确推进状态
3. 多事件回放可恢复最终状态

完成判据：

- `apply()` 为纯函数
- 不从文件系统读取事件

### 3.8 `tools/infra/llm/client.py`

职责：

- 吸收现有 `post_json` / `extract_content`
- 成为唯一 LLM HTTP 出口

先写测试：

1. 能解析标准 OpenAI-compatible 响应内容
2. choices 为空时返回空内容或明确失败
3. timeout / header 处理可控

完成判据：

- 旧脚本中重复实现都可迁移到这里
- 不掺杂业务 prompt 逻辑

### 3.9 `tools/infra/persistence/yaml_io.py`

职责：

- 吸收现有 `parse_simple_yaml` / `unquote` / `dump_yaml`

先写测试：

1. scalar/list 混合结构可解析
2. 引号去除规则与现有 CLI 输出兼容
3. dump 后格式可被旧脚本接受

完成判据：

- 与现有样例 YAML 保持兼容

### 3.10 `tools/infra/logging.py`

职责：

- 提供统一结构化日志输出

先写测试：

1. 日志包含 `run_id` / `round` / `state`
2. 输出结构稳定为 JSON 友好格式

### 3.11 `tools/errors/exceptions.py`

职责：

- 只保留不可恢复异常：`PiProofError`、`EvidenceValidationError`、`FabricationGuardError`、`PolicyError`

先写测试：

1. 每个异常有正确 category
2. 不可恢复异常默认 `recoverable=False`

### 3.12 `tools/errors/handler.py`

职责：

- 定义异常到终止策略的映射
- 不处理 Result 类型本身

先写测试：

1. `PolicyError` 映射为终止
2. `EvidenceValidationError` / `FabricationGuardError` 映射为终止

### 3.13 `tools/config/fragments.py`

职责：

- 定义 `LLMConfig`、`PathConfig`、`PolicyConfig`、`EngineSelection`

先写测试：

1. 默认值明确
2. `EngineSelection` 不再使用 Literal

### 3.14 `tools/config/validator.py`

职责：

- 校验配置切片完整性与范围合法性

先写测试：

1. 缺失关键字段会失败
2. `gate_mode` 非法值会失败
3. 策略名为空会失败

### 3.15 `tools/config/loader.py`

职责：

- 从 policy YAML + CLI 参数加载配置切片

先写测试：

1. YAML 值可映射到各配置切片
2. CLI 覆盖优先级明确

### 3.16 `tools/config/composer.py`

职责：

- 作为唯一组装点，返回最小 pipeline / 依赖骨架

先写测试：

1. 可创建最小空 pipeline
2. 不直接读取环境变量
3. 未提供必需配置时构建失败

完成判据：

- Composer 只做组装，不承载业务逻辑

## 4. M1 / Slice 1 验证清单

- [ ] `domain/` 不依赖 `infra/`、`engines/`、`cli/`
- [ ] `Result[T, E]` 已在协议层可用
- [ ] 不可恢复异常边界已确定
- [ ] `post_json` / `extract_content` 唯一实现落到 `infra/llm/client.py`
- [ ] `parse_simple_yaml` / `unquote` / `dump_yaml` 唯一实现落到 `infra/persistence/yaml_io.py`
- [ ] `Composer` 能构造最小空 pipeline

## 5. 本批次不做

- 不迁移任何四大引擎业务逻辑
- 不实现 EngineRegistry
- 不落地 Stage / Pipeline / AgentLoop
- 不改旧 CLI 包装层
- 不接入通道、RunStore 文件实现
- 不在本批次落地企业例外清单过滤（issue #1）

## 6. 下一步衔接

M1 / Slice 1 完成后，立即进入：

1. `tools/engines/registry.py`
2. 四个 rule 引擎
3. 最小 `Stage` + `LinearPipeline`

issue #1 衔接：

- 企业例外清单在 M1 只锁定配置语义与边界，不进入首批 6 文件
- 真正落地发生在后续的 `PolicyConfig`、`DiscoveryEngine` 与 `GateEngine` 阶段

这样可以最快验证 v2 架构骨架是否成立。

## 7. 首个开发批次入口

- 若要先以最小范围启动 TDD，请先执行 `docs/plans/m1-first-batch-tdd-checklist.md`
- 该文档只覆盖 6 个最小内核文件，不进入引擎、编排、CLI
