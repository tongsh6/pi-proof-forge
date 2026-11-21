# 架构概览

## 目标
- 从证据到输出的流程可复现、可追溯。
- 可解释匹配与评分。
- 事实保真生成与来源可追踪。
- 模块化设计，便于开源扩展。

## 当前架构目标（v2）

- 采用六边形领域核心：`domain/` 为零外部依赖核心。
- 基础设施唯一实现：`infra/` 集中 LLM、YAML、日志、RunStore。
- 引擎通过 `EngineRegistry` 创建，消除业务层 `if use_llm` 分支。
- 编排层通过 `Stage` 组合统一 pipeline 与 agent loop。
- 配置通过 `LLMConfig / PathConfig / PolicyConfig / EngineSelection` 切片传递，由 `Composer` 统一组装。
- 可恢复错误通过 `Result[T, E]` 表达，不可恢复错误才使用异常。
- Run 状态通过不可变事件回放重建，支持恢复与审计。

## MVP 不做
- 端到端自动填表。
- 多 Agent 辩论。

## 系统组件
- Domain Core
  - 不可变领域模型、值对象、协议接口、不变式、Result 类型、RunEvent/RunState
- Infrastructure
  - LLM client、YAML IO、结构化日志、文件存储、RunStore
- Evidence Extraction
  - 输入：原始材料
  - 输出：验证后的 evidence cards
- Engine Registry
  - 管理 rule/llm/template 等策略实现
- Indexing & Retrieval
  - 关键词/标签检索（可选 BM25）
  - 可选 embeddings/rerank
- Matching Engine
  - 评分维度：K/D/S/Q/E/R
  - 输出：match report + gap tasks
- Document Assembly
  - 模板优先拼装
  - 受控改写（不新增事实）
- Evaluation
  - Scorecard 指标
  - 缺口任务生成
- Tracking（可选）
  - 版本化输出与结果
- Desktop GUI
  - 形态：Tauri + React/TypeScript + Python sidecar
  - 职责：承载终版 9 页信息架构、运行状态、证据管理、结果预览、投递跟踪、策略配置与系统设置
- Sidecar Bridge
  - 职责：承载 JSON-RPC 2.0 over stdio 协议、将 RPC 方法路由到 v2 内部 service、管理事件流推送、统一错误码映射
  - 子组件：rpc_server / method_handlers / event_bus / lifecycle / error_mapper

## 分层与依赖方向

```text
GUI (Tauri) --JSON-RPC--> sidecar -> orchestration -> engines -> domain <- infra
cli ----------------------------------------^
channels -----------------------------------^
config/composer 负责统一组装
```

约束：

- `domain/` 不依赖 `infra/`、`engines/`、`cli/`
- `channels/` 实现 `domain/protocols.py` 中定义的 `DeliveryChannel`，由 `orchestration/` 调用，不直接承载编排逻辑
- `infra/` 可以依赖 `domain/`，不得承载业务规则
- `engines/` 实现 `domain/protocols.py` 中定义的接口
- `orchestration/` 只负责 Stage 调度、状态流转和 Result 消费

## LLM 结构化请求边界

- `LLMClient.post_json` 统一传递调用方声明的输出结构。请求使用 `response_format={"type":"json_object"}` 且传入 `response_schema` 时，完整 schema 必须进入模型实际收到的请求；不能在某个 provider 下静默丢弃。
- 现有 LM Studio 路径使用原生 `json_schema`。其他 JSON-object 路径保留已支持的协议格式，把同一份 schema 序列化为可信 system 输出约束；不按业务字段、模型名称或样例添加别名、补值或专门规则，也不假定端点支持原生 schema。
- 调用方显式给出的其他 `response_format` 保持原意；未传 schema 时保持现有行为。构造请求不得修改调用方的 payload、messages 或 schema，重复调用不得累加格式约束。原始资料仍是 user 数据，不能被提升为 system 指令。
- 客户端只负责结构合同的传递和现有 provider 协议适配。业务调用方继续校验 JSON、字段、引用及语义，保持既有有限修复策略；schema 可见不等于模型输出已通过校验，客户端不得改写错误输出以使其合格。
- 回归以实际序列化的 `Request.data` 为依据，同时保留原生 schema、无 schema、显式格式及错误输出被业务校验拒绝的对照；应用验收仍须经过真实 RPC 与配置的模型调用。

## LLM 输入预算边界（L2，限定工程范围已完成）

- `LLMClient` 是 context/schema/provider 组装与序列化的唯一所有者，标准库 `Request` 承载实际请求；`post_json` 组合准备与原 transport 发送。契约执行器与 matching 分批消费同份已准备对象，发送不再重建。
- `max_input_chars` 按完整 `Request.data` 解码后的逻辑 JSON 字符计量（`ensure_ascii=False`），包括全部注入与内层转义，保留现有上限；不等于 token、UTF-8/wire 字节。初次和每次修复均先准备、检查，再进入发送及调度计数；超限不调用 HTTP，本地构造失败为 `invalid_request`，不按 0 放行或重发原输入。
- matching 保留完整事实与原顺序，以实际准备请求准入批次；最终接受的 Request 同时决定预算、缓存身份与首次发送。原缓存命中仍须业务校验且不发送；无旧 key 双轨、新 DTO、持久字段或平行预算账本。
- 当前统一执行器的真实生产消费者是语义匹配；其他直接客户端调用尚不能宣称已有契约预算。有限修复、输出预算和本地 transport 额度/超时/重定向约束保留，部署能力配置特例另片治理。详见 [LLM 任务契约](../../../docs/reports/llm-task-contract-design-20261110.md#输入预算执行切片-l2限定工程范围已完成)。

## 数据流（高层）
1. Raw materials → evidence extraction → evidence cards
2. JD input → job profile
3. Evidence cards + job profile → matching report
4. Selected cards → template assembly → controlled rewrite → output document
5. Output → scorecard → evidence gap tasks
6. Desktop GUI 读取、驱动并展示 pipeline 与 agent loop 产物
7. GUI 通过 JSON-RPC 调用 sidecar，sidecar 将请求路由到 v2 内部 service 并将事件流推送回 GUI

## 数据存储（MVP）
- Evidence cards：YAML/Markdown + Git 版本管理
- Inputs/outputs：版本化文件
- Tracking：CSV/SQLite

## 可插拔接口
- LLM provider
- Embedding provider
- Exporter（PDF/DOCX）
- Desktop GUI bridge（Tauri host 与 Python sidecar 调用层；具体实现：Sidecar Bridge，JSON-RPC 2.0 over stdio）
- Delivery channel
- Matching / generation / evaluation strategy
- Run store backend（当前仅文件实现）

## 未决问题
- Fact-attribution 的约束与校验策略
- 受控改写的 diff 校验方法
- 最小可用 exporter 选型
- 事件回放是否需要进一步演进为完整 CQRS/Event Sourcing
