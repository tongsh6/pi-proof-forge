# M1 首个开发批次 TDD 用例清单

> 状态：draft
> 对应范围：`docs/plans/m1-slice-1-breakdown.md` 中的最小先行批次
> 目标：只锁定领域边界与重复实现归一，不进入引擎、编排、CLI

## 1. 批次范围

首个开发批次只覆盖 6 个文件：

1. `tools/domain/result.py`
2. `tools/domain/value_objects.py`
3. `tools/domain/models.py`
4. `tools/domain/protocols.py`
5. `tools/infra/llm/client.py`
6. `tools/infra/persistence/yaml_io.py`

选择理由：

- 这是后续所有引擎与编排都会依赖的最小公共内核。
- 先把 `Result`、领域值对象、核心模型、协议、LLM 客户端、YAML IO 定型，能最大限度减少后续返工。
- 这 6 个文件都可在不接触旧 CLI 的前提下独立 TDD。

## 2. 开发顺序

```text
T1 result.py
T2 value_objects.py
T3 models.py
T4 protocols.py
T5 infra/llm/client.py
T6 infra/persistence/yaml_io.py
```

## 3. TDD 用例清单

### T1 - `tools/domain/result.py`

先写失败测试：

1. `Ok(value=1)` 与 `Ok(value=1)` 相等
2. `Err(error="x")` 与 `Err(error="x")` 相等
3. `Ok` 与 `Err` 不相等
4. `repr(Ok(...))` / `repr(Err(...))` 稳定且可读

通过标准：

- 使用 frozen dataclass
- 不提供 map/bind/unwrap 等复杂 helper

不做：

- 不引入完整 monad 工具集

### T2 - `tools/domain/value_objects.py`

先写失败测试：

1. `Score` 可比较且不可变
2. `GapTask` 可表示 description / priority / source
3. `Candidate` 至少包含 `candidate_id`、`direction`、`company`、`job_url`、`confidence`、`source`、`merged_sources`
4. `GateFailure` / `ChannelFailure` 可作为 `Err` 的 error 类型使用
5. `DeliveryResult` 不再用匿名 dict 表达

通过标准：

- 全部值对象为 frozen dataclass
- 不把行为逻辑塞进值对象，只承载状态

### T3 - `tools/domain/models.py`

先写失败测试：

1. `EvidenceCard.is_eligible()` 在 `results=()` 时返回 `False`
2. `EvidenceCard.is_eligible()` 在 `artifacts=()` 时返回 `False`
3. `EvidenceCard.is_eligible()` 在两者都存在时返回 `True`
4. `JobProfile` 最小字段可实例化
5. `MatchingReport` 能表达 `job_profile_id`、`evidence_cards`、`score_breakdown`、`gap_tasks`
6. `ResumeOutput` / `Scorecard` 具备最小必要字段

通过标准：

- 所有模型均为 frozen dataclass
- 字段命名与 openspec 保持一致
- 模型不依赖 `Path`、环境变量、外部客户端

### T4 - `tools/domain/protocols.py`

先写失败测试：

1. fake extractor 能满足 `EvidenceExtractor`
2. fake matcher 能满足 `MatchingEngine`
3. fake generator 能满足 `GenerationEngine`
4. fake evaluator 能满足 `EvaluationEngine`
5. `GateEngine.evaluate()` 的返回类型语义为 `Result[GateDecision, GateFailure]`
6. `DeliveryChannel.deliver()` 的返回类型语义为 `Result[DeliveryResult, ChannelFailure]`
7. `RunStore` 具备 `append_event` / `load_events` 最小契约

通过标准：

- Protocol 只引用 `domain/*` 中的类型
- 不引用 `infra/*` 具体实现

### T5 - `tools/infra/llm/client.py`

先写失败测试：

1. 给定标准 chat completion 响应，能提取 `choices[0].message.content`
2. `choices=[]` 时返回空字符串或显式空结果
3. 缺失 `message.content` 时返回空字符串或显式空结果
4. `base_url.rstrip("/") + "/chat/completions"` 规则稳定
5. 能构造包含 `Authorization` 与 `Content-Type` 的请求头

通过标准：

- 成为唯一 `post_json` / `extract_content` 实现位置
- 不掺杂任何 evidence/matching/generation/evaluation 业务 prompt

不做：

- 不在本批次支持多 provider adapter
- 不处理重试、熔断、复杂 observability

### T6 - `tools/infra/persistence/yaml_io.py`

先写失败测试：

1. 可解析标量字段
2. 可解析 list 字段
3. 支持空行与注释跳过
4. `unquote()` 可处理单引号与双引号
5. `dump_yaml()` 生成内容可覆盖旧 `extract_evidence.py` 的最小输出格式需求
6. 解析后再 dump 的关键字段保持稳定

通过标准：

- 成为唯一 `parse_simple_yaml` / `unquote` / `dump_yaml` 实现位置
- 与现有样例 YAML 兼容

## 4. 批次完成条件

- [ ] 上述 6 个文件全部有先失败后通过的测试
- [ ] `Result`、值对象、模型、协议之间的依赖方向稳定
- [ ] LLM/YAML 重复实现已经有明确迁移落点
- [ ] 本批次未引入引擎、编排、CLI 层耦合

## 5. 批次完成后立刻进入的下一批

下一批建议顺序：

1. `tools/domain/invariants.py`
2. `tools/errors/exceptions.py`
3. `tools/errors/handler.py`
4. `tools/config/fragments.py`
5. `tools/config/validator.py`
6. `tools/config/loader.py`
7. `tools/config/composer.py`

issue #1 衔接：

- 在首批 6 文件完成后、进入 config 阶段时，把企业例外清单语义补进 `PolicyConfig`
- 同一阶段完成 `loader.py` / `validator.py` 对 YAML `filters.*` 到 `PolicyConfig.excluded_*` 的映射与校验
- 再下一阶段在 `DiscoveryEngine` 落地主过滤，在 `GateEngine` 落地兜底校验

这样可以在进入业务引擎之前，把守卫、异常边界和组装点一并锁住。
