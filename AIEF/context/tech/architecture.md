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
