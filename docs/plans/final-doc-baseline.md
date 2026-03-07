# 最终文档基线（实施依据）

> 状态：active
> 用途：进入实现前，明确 PiProofForge v2 重构应以哪些文档为准，以及各文档的优先级与职责边界。

## 1. 结论

当前仓库文档已收口到可实施状态。

进入实现时，建议把以下文档视为**最终文档基线**：

1. OpenSpec 规范与变更文档：定义最终目标与约束
2. 实施计划文档：定义阶段顺序、文件拆分与 TDD 起点
3. AIEF 技术/索引文档：提供项目内导航与稳定术语
4. README / tools README：面向使用者的入口说明，不作为架构裁决来源

## 2. 优先级顺序（冲突时如何裁决）

当文档之间出现冲突时，按以下优先级裁决：

```text
constitution.md
  > openspec/specs/pi-proof-forge-core.md
  > openspec/changes/autonomous-agent-delivery-loop/design.md
  > openspec/changes/autonomous-agent-delivery-loop/tasks.md
  > docs/plans/*.md
  > AIEF/context/tech/*.md
  > README.md / tools/README.md
```

裁决规则：

- **原则冲突**：以 `constitution.md` 为准
- **最终架构冲突**：以 `openspec/specs/pi-proof-forge-core.md` 为准
- **设计细节冲突**：以 `openspec/changes/autonomous-agent-delivery-loop/design.md` 为准
- **任务顺序冲突**：以 `openspec/changes/autonomous-agent-delivery-loop/tasks.md` 为准
- **实施粒度冲突**：以 `docs/plans/*.md` 为准
- **导航/说明冲突**：README 和 AIEF 文档需回收对齐，不得反向覆盖 OpenSpec

## 3. 核心文档集合

### A. 原则层（不可违背）

- `constitution.md`
  - 作用：定义不可妥协原则
  - 关键约束：evidence-first、事实保真、先 spec 再实现、TDD、YAGNI + DRY

### B. 规范层（定义最终重构目标）

- `openspec/specs/pi-proof-forge-core.md`
  - 作用：v2 最终目标架构的正式规范
  - 回答的问题：
    - 目标分层是什么
    - 依赖方向是什么
    - Protocol 放在哪里
    - `EngineRegistry` / `Composer` / `Result[T, E]` / 事件回放如何定义

- `openspec/changes/autonomous-agent-delivery-loop/design.md`
  - 作用：解释为什么选 v2 方案，以及各设计决策的来源
  - 回答的问题：
    - 为什么从 `tools/core/...` 迁到 `domain/infra/engines/orchestration`
    - 哪些问题要被解决
    - 迁移策略和分阶段设计是什么

- `openspec/changes/autonomous-agent-delivery-loop/tasks.md`
  - 作用：定义实施阶段与验收标准
  - 回答的问题：
    - 先做什么，后做什么
    - 每个阶段的交付物是什么
    - Exit Criteria 是什么

### C. 计划层（指导如何开始做）

- `docs/plans/autonomous-agent-delivery-loop-v2.md`
  - 作用：总体实施计划，里程碑与风险控制

- `docs/plans/m1-slice-1-breakdown.md`
  - 作用：M1 / Slice 1 的逐文件拆分

- `docs/plans/m1-first-batch-tdd-checklist.md`
  - 作用：首个开发批次的最小 TDD 用例清单

### D. 项目导航层（帮助定位，不裁决架构）

- `AIEF/context/tech/architecture.md`
  - 作用：AIEF 侧的架构概览和术语同步

- `AIEF/context/tech/REPO_SNAPSHOT.md`
  - 作用：仓库结构和入口命令快照

- `AIEF/context/INDEX.md`
  - 作用：上下文索引入口

- `AIEF/AGENTS.md`
  - 作用：项目级 AI 协作入口和推荐命令口径

### E. 使用说明层（面向人类/调用者）

- `README.md`
- `tools/README.md`

说明：

- 这两份文档用于说明“怎么用”，不负责定义“最终架构怎么裁决”。

## 4. 进入实现时的最小阅读集

如果要正式开始写代码，最少先读这 6 份：

1. `constitution.md`
2. `openspec/specs/pi-proof-forge-core.md`
3. `openspec/changes/autonomous-agent-delivery-loop/design.md`
4. `openspec/changes/autonomous-agent-delivery-loop/tasks.md`
5. `docs/plans/m1-slice-1-breakdown.md`
6. `docs/plans/m1-first-batch-tdd-checklist.md`

原因：

- 这 6 份已经足够覆盖原则、终态、迁移顺序、首批实现范围和 TDD 起点。

## 5. 当前已稳定的关键口径

以下口径已完成统一，可直接作为实现依据：

- 分层：`domain/` + `infra/` + `engines/` + `orchestration/` + `config/` + `channels/` + `cli/`
- 依赖方向：`cli -> orchestration -> engines -> domain <- infra`
- 策略选择：`EngineRegistry`，不再使用业务层 `if use_llm`
- 配置组装：`Composer`，不再使用上帝 `Config`
- 可恢复错误：使用 `Result[T, E]`
- 不可恢复错误：使用 `PiProofError` 子类
- 状态恢复：`RunState.replay(events)`
- evidence extraction 入口：`tools/run_evidence_extraction.py` 为推荐入口；`tools/extract_evidence.py` 为底层规则/兼容脚本

## 6. 当前仍应注意的边界

- `README.md` 和 `tools/README.md` 负责入口说明，不应新增与 OpenSpec 冲突的架构描述
- AIEF 文档负责导航与术语同步，不应成为最终架构裁决来源
- 任何未来文档若再次引入 `tools/core/...`、`Literal["rule", "llm"]`、业务层 `if use_llm`，都应视为回退漂移

## 7. 实施前检查清单

- [ ] 先读最小阅读集
- [ ] 先按 `docs/plans/m1-first-batch-tdd-checklist.md` 启动 TDD
- [ ] 任何新文档都沿用 v2 稳定口径
- [ ] 发现文档冲突时按优先级裁决，不以 README 反向覆盖 OpenSpec
