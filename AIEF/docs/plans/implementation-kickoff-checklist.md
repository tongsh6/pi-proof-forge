# 实现启动清单

> 状态：active
> 用途：正式开始 v2 重构实现前，给开发者/AI 一个可直接执行的启动顺序。
> 约束：本清单只定义“开工前如何准备”和“第一批如何启动 TDD”，不替代 OpenSpec。

## 1. 启动目标

在不偏离 v2 最终架构的前提下，用最小范围启动实现，确保：

- 先读对文档，再写代码
- 先写测试，再写实现
- 先锁边界，再迁移业务逻辑
- 先最小骨架，再逐层放大范围

## 2. 开工前必须完成的阅读顺序

按以下顺序阅读，不建议跳步：

1. `constitution.md`
2. `openspec/specs/pi-proof-forge-core.md`
3. `openspec/changes/autonomous-agent-delivery-loop/design.md`
4. `openspec/changes/autonomous-agent-delivery-loop/tasks.md`
5. `AIEF/docs/plans/final-doc-baseline.md`
6. `AIEF/docs/plans/m1-slice-1-breakdown.md`
7. `AIEF/docs/plans/m1-first-batch-tdd-checklist.md`
8. 若任务涉及 GUI：`AIEF/context/tech/GUI_ARCHITECTURE.md`
9. 若任务涉及 GUI：`ui/design/contracts/sidecar-rpc.md`
10. 若任务涉及 GUI：`AIEF/docs/plans/gui-review-checklist.md`
11. 若任务涉及 GUI：`AIEF/docs/plans/gui-first-batch-kickoff.md`

读完后应能明确回答：

- v2 最终分层是什么
- 哪些错误用 `Result[T, E]`，哪些错误仍用异常
- 首个开发批次只做哪 6 个文件，或若为 GUI 任务则只做哪一批脚手架文件
- 哪些内容当前明确“不做”
- 若涉及 GUI，GUI 架构真源是什么、RPC contract 真源是什么，以及哪些设计/代码/验收检查项必须重复执行

## 3. 开工前必须确认的口径

开始写任何代码前，先确认以下口径不能再变：

- 分层：`domain/` + `infra/` + `engines/` + `orchestration/` + `config/` + `channels/` + `cli/`
- 依赖方向：`cli -> orchestration -> engines -> domain <- infra`
- 策略接入：使用 `EngineRegistry`
- 配置组装：使用 `Composer`
- evidence extraction 推荐入口：`tools/run_evidence_extraction.py`
- 业务层禁止 `if use_llm`
- 领域层禁止依赖基础设施实现

如果其中任一条需要改变，必须先回到 OpenSpec 改 spec，而不是直接改代码。

若当前任务涉及 GUI，还必须额外确认：

- `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen` 必须同步维护
- `AIEF/context/tech/GUI_ARCHITECTURE.md` 是 GUI 架构真源，开工前必须显式阅读并确认当前技术路线
- `ui/design/contracts/sidecar-rpc.md` 是 GUI bridge contract 真源，开工前必须显式阅读并确认字段级协议
- GUI 实现不得只依据文档理解，必须对照 `.pen` 设计资产验收
- GUI 变更必须纳入 design review、code review、实现验收三次重复检查
- GUI 配置页必须按 `Policy / 策略配置` 与 `System Settings / 系统设置` 两个正式页面实现，不得回退为单个 `Settings`

## 4. 首个实现批次的范围锁定

首个开发批次只允许进入以下 6 个生产文件：

1. `tools/domain/result.py`
2. `tools/domain/value_objects.py`
3. `tools/domain/models.py`
4. `tools/domain/protocols.py`
5. `tools/infra/llm/client.py`
6. `tools/infra/persistence/yaml_io.py`

首个批次不得进入：

- `tools/engines/`
- `tools/orchestration/`
- `tools/config/`
- `tools/channels/`
- 旧 CLI 包装层

说明：

- issue #1（企业例外清单）不在首批 6 文件里落地；它会在后续 `PolicyConfig + DiscoveryEngine + GateEngine` 阶段接入。
- 若当前任务为 GUI 首批实施，本节后端 6 文件范围不适用，改按 `AIEF/docs/plans/gui-first-batch-kickoff.md` 执行。

## 5. 开工前先创建的测试目录

建议先建好最小测试骨架，再逐个红灯：

```text
tests/
  unit/
    domain/
      test_result.py
      test_value_objects.py
      test_models.py
      test_protocols.py
    infra/
      test_llm_client.py
      test_yaml_io.py
```

说明：

- 第一批不需要 integration / e2e
- 第一批只需要 unit tests
- 测试文件名应与目标生产文件一一对应

## 6. 第一批的推荐 TDD 顺序

### Step 1 - `test_result.py` -> `tools/domain/result.py`

进入条件：

- 已完成最小阅读集

退出条件：

- `Ok` / `Err` 的比较行为已锁定
- 没有引入额外 helper 污染 API

### Step 2 - `test_value_objects.py` -> `tools/domain/value_objects.py`

进入条件：

- `Result` 已稳定

退出条件：

- 值对象全部 frozen
- 不再依赖匿名 dict 返回结构

### Step 3 - `test_models.py` -> `tools/domain/models.py`

进入条件：

- `value_objects.py` 已稳定

退出条件：

- `EvidenceCard.is_eligible()` 行为已锁定
- 模型字段与 openspec 对齐

### Step 4 - `test_protocols.py` -> `tools/domain/protocols.py`

进入条件：

- 核心模型与 Result 已稳定

退出条件：

- fake 实现能满足 Protocol
- `GateEngine` / `DeliveryChannel` 的 Result 语义已锁定

### Step 5 - `test_llm_client.py` -> `tools/infra/llm/client.py`

进入条件：

- 已明确它只是唯一 HTTP 出口，不承载业务 prompt

退出条件：

- `post_json` / `extract_content` 的统一落点已经建立

### Step 6 - `test_yaml_io.py` -> `tools/infra/persistence/yaml_io.py`

进入条件：

- 已确认与现有样例 YAML 保持兼容

退出条件：

- `parse_simple_yaml` / `unquote` / `dump_yaml` 的统一落点已经建立

## 7. 每一步都要做的自检

每完成一个文件，都要自检：

- [ ] 有没有引入超出本批次范围的依赖
- [ ] 有没有把业务逻辑提前塞进基础抽象
- [ ] 有没有违背 frozen / zero-dependency / no-`if use_llm` 约束
- [ ] 测试是不是先失败后通过，而不是实现后补测

## 8. 必须暂停并回看文档的触发条件

出现以下任一情况，必须停下来回看 spec / plan：

- 想在首批里加入 `EngineRegistry`
- 想直接改旧 CLI
- 想在 `domain/` 引入 `Path`、HTTP、环境变量读取
- 想把异常和 `Result` 混着用但说不清边界
- 想新增字段但 OpenSpec 里没有定义

## 9. 首批完成后的直接下一步

首批 6 文件稳定后，再进入：

1. `tools/domain/invariants.py`
2. `tools/errors/exceptions.py`
3. `tools/errors/handler.py`
4. `tools/config/fragments.py`
5. `tools/config/validator.py`
6. `tools/config/loader.py`
7. `tools/config/composer.py`
8. 在 `PolicyConfig` 中加入企业例外清单语义

然后才进入：

9. `tools/engines/registry.py`
10. 四个 rule 引擎（含 DiscoveryEngine 的企业例外清单主过滤）
11. `Stage` + `LinearPipeline`（含 GateEngine 的 exclusion 兜底）

## 10. 一句话启动建议

如果现在就要开工，先做这两件事：

1. 建 `tests/unit/domain/` 和 `tests/unit/infra/` 的 6 个测试文件
2. 从 `test_result.py` 开始红灯，而不是先写任何生产代码
