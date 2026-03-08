# Backend → UI 架构桥接计划

> 状态：draft
> 用途：定义从当前 `tools/` CLI 脚本架构到支撑终版 9 页 GUI 的分层改造路径，衔接 v2 后端架构计划与 GUI 前端计划。
> 依据：Oracle 架构匹配度分析（2026-03-07）、`autonomous-agent-delivery-loop-v2.md`、`gui-first-batch-kickoff.md`、`ui/design/DESIGN.md`、`ui/design/contracts/sidecar-rpc.md`
> 裁决关系：若本文件与 `autonomous-agent-delivery-loop-v2.md` 冲突，以该文件为准（后端架构权威）；若与 `ui/design/DESIGN.md` 冲突，以该文件为准（UI 规范权威）。

## 1. 问题陈述

当前后端代码（`tools/`）为 CLI 脚本架构，与终版 UI 设计存在 **结构性差距**。

核心矛盾：
- UI 需要 **JSON-RPC sidecar 服务** — 后端只有 **argparse + subprocess**
- UI 需要 **20 个 RPC 方法 + 8 类事件流** — 后端只有 **6 个独立 CLI 脚本**
- UI 需要 **实时进度推送** — 后端只有 **同步阻塞执行**
- UI 需要 **CRUD + 分页 + 筛选** — 后端只有 **YAML 文件直读**
- UI 需要 **9 状态机 + 门禁系统** — 后端只有 **4 步线性 pipeline**

本计划定义如何分层解决这些差距，使 v2 后端架构（M1-M5）与 GUI 前端计划能正确对接。

## 2. 逐页匹配度基线

| 页面 | 匹配度 | 可复用能力 | 关键缺失 | 解锁所需 v2 里程碑 |
|------|--------|-----------|----------|-------------------|
| Overview | 10% | 数据源存在 | 聚合统计、活动流、趋势 | M2 + Sidecar L2 |
| Resumes | 20% | `run_generation.py` | PersonalProfile、上传管理、PDF 导出 | M2 + Sidecar L2 |
| Evidence | 30% | `extract_evidence*.py` | CRUD 管理、分页筛选、Artifacts | M1 + Sidecar L1 |
| Jobs | 15% | `job_profiles/` YAML | Job Leads、Lead→Profile 转化 | M2 + Sidecar L2 |
| Quick Run | 40% | `run_pipeline.py` 4 阶段 | 实时进度、日志流、评分可视化 | M3 + Sidecar L3 |
| Agent Run | 5% | 底层引擎存在 | 9 状态机、门禁、多轮循环、事件流 | M3 + M4 + Sidecar L3 |
| Submissions | 25% | `submission/liepin.py` | 追踪管理、时间线、截图、重试 | M4 + Sidecar L3 |
| Policy | 0% | 无 | 门禁策略 CRUD、排除列表 | M1 (config) + Sidecar L1 |
| System Settings | 0% | 环境变量 | 通道/LLM 配置、凭证、连通性 | M1 (config) + Sidecar L1 |

## 3. 桥接层定义

v2 后端架构与 GUI 之间需要一个 **Sidecar Bridge Layer**，职责是：
- 承载 JSON-RPC 2.0 over stdio 协议
- 将 RPC 方法路由到 v2 内部 service
- 管理事件流推送
- 统一错误码映射

```text
┌─────────────────────────────────────────────────────┐
│  GUI (React + Tauri)                                │
│  - Zustand stores                                   │
│  - typed RPC client                                 │
└──────────────────────┬──────────────────────────────┘
                       │ JSON-RPC 2.0 over stdio
┌──────────────────────▼──────────────────────────────┐
│  Sidecar Bridge Layer  (新增)                        │
│  - rpc_server.py        JSON-RPC 路由与 envelope     │
│  - method_handlers/     每个 RPC 方法的 handler       │
│  - event_bus.py         事件发布与 notification 推送   │
│  - lifecycle.py         handshake / ping / shutdown  │
│  - error_mapper.py      domain error → RPC error code│
└──────────────────────┬──────────────────────────────┘
                       │ 调用 v2 内部 service
┌──────────────────────▼──────────────────────────────┐
│  v2 Backend (现有 + 改造)                            │
│  domain/ → infra/ → engines/ → orchestration/        │
│  config/ → channels/ → cli/                          │
└─────────────────────────────────────────────────────┘
```

### Sidecar Bridge 目录结构

```text
tools/
  sidecar/                      ← 新增
    __init__.py
    server.py                   # JSON-RPC 主循环 (stdio read/write)
    router.py                   # method → handler 路由
    lifecycle.py                # system.handshake / ping / shutdown
    event_bus.py                # 事件发布 + notification 序列化
    error_mapper.py             # domain/infra error → RPC error code
    handlers/
      __init__.py
      evidence.py               # evidence.list / get / import
      jobs.py                   # jobs.listProfiles / listLeads / convertLead
      run.py                    # run.quick.* / run.agent.*
      resume.py                 # resume.list / exportPdf
      submission.py             # submission.list / retry
      settings.py               # settings.get / update
```

## 4. UI 页面 → v2 组件依赖映射

### Evidence 页面
```
UI: evidence.list / evidence.get / evidence.import
 ↓
Sidecar: handlers/evidence.py
 ↓
v2: domain/models.py (EvidenceCard)
    infra/persistence/yaml_io.py (CRUD)
    infra/persistence/file_storage.py (Artifacts) ← 新增
    engines/evidence/ (import 时提炼)
```

### Quick Run 页面
```
UI: run.quick.start / run.quick.cancel + quick.run.updated/log events
 ↓
Sidecar: handlers/run.py + event_bus.py
 ↓
v2: orchestration/pipeline.py (LinearPipeline)
    orchestration/stage.py (4 个 Stage)
    engines/evidence/ + matching/ + generation/ + evaluation/
    domain/events.py (RunEvent 用于进度推送)
```

### Agent Run 页面
```
UI: run.agent.start / stop / get + agent.run.updated/log/event events
 ↓
Sidecar: handlers/run.py + event_bus.py
 ↓
v2: orchestration/state_machine.py (9 状态)
    orchestration/agent_loop.py (多轮循环)
    orchestration/gate_engine.py (门禁检查)
    domain/run_state.py (RunState)
    domain/events.py (RunEvent 流)
```

### Jobs 页面
```
UI: jobs.listProfiles / jobs.listLeads / jobs.convertLead
 ↓
Sidecar: handlers/jobs.py
 ↓
v2: domain/models.py (JobProfile, JobLead) ← JobLead 为新增实体
    infra/persistence/yaml_io.py (CRUD)
    engines/discovery/ (Lead 来源)
```

### Resumes 页面
```
UI: resume.list / resume.exportPdf
 ↓
Sidecar: handlers/resume.py
 ↓
v2: domain/models.py (PersonalProfile, Resume) ← PersonalProfile 为新增实体
    infra/persistence/yaml_io.py (CRUD)
    engines/generation/ (生成)
    infra/export/ (PDF 导出) ← 新增
```

### Submissions 页面
```
UI: submission.list / submission.retry + submission.updated events
 ↓
Sidecar: handlers/submission.py + event_bus.py
 ↓
v2: domain/models.py (SubmissionRecord, SubmissionTimeline) ← 扩展
    channels/liepin.py + email.py
    infra/persistence/file_storage.py (截图)
    infra/persistence/file_run_store.py (步骤记录)
```

### Policy + System Settings 页面
```
UI: settings.get / settings.update
 ↓
Sidecar: handlers/settings.py
 ↓
v2: config/fragments.py (PolicyConfig, ChannelConfig, LLMConfig)
    config/loader.py + validator.py
    infra/credential_store.py (OS keychain) ← 新增
```

### Overview 页面
```
UI: 聚合统计 + 活动流 + 趋势 + 缺口
 ↓
Sidecar: handlers/overview.py ← 新增（非 RPC contract 中定义，需补充）
 ↓
v2: 各 domain service 的聚合查询
    infra/persistence/ (计数 + 时间序列)
    domain/models.py (活动流记录) ← 新增
```

## 5. 缺失实体清单

以下领域实体在 v2 plan 的 `domain/models.py` 中尚未定义，但 UI 必需：

| 实体 | UI 页面 | 说明 | 建议归属 |
|------|---------|------|---------|
| `PersonalProfile` | Resumes | 姓名/手机/邮箱/城市/当前职位 | `domain/models.py` |
| `JobLead` | Jobs | 来源/URL/公司/职位/状态/收藏 | `domain/models.py` |
| `UploadedResume` | Resumes | 文件名/语言/上传时间/来源渠道 | `domain/models.py` |
| `ActivityLog` | Overview | 类型/时间/描述/关联资源 | `domain/models.py` |
| `MatchTrendPoint` | Overview | 日期/分数/job_profile_id | `domain/value_objects.py` |
| `GapItem` | Overview | 类型/描述/严重度/关联证据 | `domain/value_objects.py` |
| `SubmissionStep` | Submissions | 步骤名/状态/时间/截图 ID | `domain/value_objects.py` |
| `ScreenshotRef` | Submissions | resource_id/文件名/mime/大小 | `domain/value_objects.py` |

### 缺失基础设施组件

| 组件 | 说明 | 建议位置 |
|------|------|---------|
| `file_storage.py` | Artifacts + 截图的受控存储/读取/删除 | `infra/persistence/` |
| `credential_store.py` | OS keychain 读写 (api_key 等) | `infra/` |
| `pdf_exporter.py` | 简历 PDF 导出 | `infra/export/` |
| `stats_aggregator.py` | Overview 页面聚合查询 | `infra/` 或 service 层 |

## 6. Sidecar 分级实施计划

为避免一次性改造量过大，将 Sidecar Bridge 分 3 级递进实施：

### Sidecar L1 — 最小可用 (与 v2 M1 并行)

目标：GUI 前端可以连接 sidecar、读取静态数据。

实现范围：
- `server.py` + `router.py` — JSON-RPC 主循环与路由
- `lifecycle.py` — `system.handshake` / `system.ping` / `system.shutdown`
- `handlers/evidence.py` — `evidence.list` / `evidence.get`（只读，直接读 YAML）
- `handlers/settings.py` — `settings.get`（读取配置文件）
- `error_mapper.py` — 基础错误码映射

解锁 UI 能力：
- Evidence 页面：只读列表 + 详情查看
- Policy / System Settings：只读查看
- 全局 sidecar 连接状态

### Sidecar L2 — CRUD 与管理 (与 v2 M2 并行)

目标：GUI 前端可以管理数据、执行导入导出。

新增范围：
- `handlers/evidence.py` — `evidence.import`
- `handlers/jobs.py` — `jobs.listProfiles` / `jobs.listLeads` / `jobs.convertLead`
- `handlers/resume.py` — `resume.list` / `resume.exportPdf`
- `handlers/submission.py` — `submission.list`
- `handlers/settings.py` — `settings.update`
- `event_bus.py` — 基础事件推送框架
- 分页/筛选/排序支持

解锁 UI 能力：
- Evidence 页面：完整 CRUD + Artifacts
- Jobs 页面：Profiles + Leads 管理
- Resumes 页面：列表 + 导出
- Submissions 页面：只读列表
- Overview 页面：静态统计
- Policy / System Settings：读写

### Sidecar L3 — 运行时与事件流 (与 v2 M3-M4 并行)

目标：GUI 前端可以执行 pipeline/agent run 并接收实时事件。

新增范围：
- `handlers/run.py` — `run.quick.*` / `run.agent.*`
- `handlers/submission.py` — `submission.retry`
- `event_bus.py` — 完整事件流推送
  - `quick.run.updated` / `quick.run.log`
  - `agent.run.updated` / `agent.run.log` / `agent.run.event`
  - `submission.updated`
  - `sidecar.state.changed`

解锁 UI 能力：
- Quick Run 页面：实时执行 + 进度 + 日志
- Agent Run 页面：状态机 + 门禁 + 事件流
- Submissions 页面：重试 + 实时状态更新
- Overview 页面：活动流 + 趋势

## 7. v2 Milestone → UI 解锁时间线

```text
时间线    v2 后端                   Sidecar Bridge          GUI 前端
─────────────────────────────────────────────────────────────────────
Week 1-2  M1: domain + infra        L1: server + 只读       首批骨架
          - models.py               - handshake/ping        - AppShell + SideNav
          - yaml_io.py              - evidence.list/get     - 9 页路由占位
          - llm/client.py           - settings.get          - RPC bridge stub
          - config/                 - error_mapper          - i18n + tokens

Week 3-4  M2: engines + registry    L2: CRUD + 管理         共享组件 + 首批页面
          - 4 大引擎                - evidence.import       - DataTable / FormField
          - EngineRegistry          - jobs.*                - Evidence 主态
          - DiscoveryEngine         - resume.*              - Jobs 主态
                                    - settings.update       - Overview 主态
                                    - 分页/筛选              - Policy / Settings

Week 5-6  M3: orchestration         L3: 运行时 + 事件流     运行时页面
          - Stage + Pipeline        - run.quick.*           - Quick Run 主态
          - StateMachine            - run.agent.*           - Agent Run 主态
          - GateEngine              - event_bus 完整         - 实时进度集成
          - AgentLoop               - submission.retry

Week 7-8  M4: channels + RunStore   L3 补齐                 三态 + 验收
          - liepin + email          - submission.updated    - Loading/Empty/Error
          - file_run_store          - 截图读取               - 断连态
          - 事件回放                                        - 终验 vs .pen

Week 9    M5: CLI 收口              —                       全量验收
          - 旧 CLI 兼容包装
```

## 8. Overview 页面 RPC 补充建议

当前 `sidecar-rpc.md` 未显式定义 Overview 页面的 RPC 方法。UI 需要以下数据：

- `metrics`: { evidence_count, matched_jobs_count, resume_count, submission_count }
- `recent_activities[]`: 最近操作记录
- `match_trend[]`: 匹配分数趋势
- `gaps[]`: 缺口待办

建议方案（二选一）：

**方案 A — 新增 `overview.get` 方法**（推荐）

```json
{
  "method": "overview.get",
  "params": { "meta": { "correlation_id": "..." } },
  "result": {
    "metrics": { "evidence": 12, "matched_jobs": 8, "resumes": 5, "submissions": 23 },
    "recent_activities": [],
    "match_trend": [],
    "gaps": []
  }
}
```

优点：一次请求获取所有 Overview 数据，减少前端拼接复杂度。
代价：需要在 `sidecar-rpc.md` 中补充该方法的 contract。

**方案 B — 前端聚合现有方法**

前端分别调用 `evidence.list`、`jobs.listProfiles`、`resume.list`、`submission.list` 获取 count，自行拼接。

优点：无需新增 RPC 方法。
代价：Overview 需要 4+ 次 RPC 调用，且活动流/趋势/缺口无法用现有方法覆盖。

**结论**：方案 B 无法覆盖 `recent_activities` / `match_trend` / `gaps`，**必须走方案 A**。需要在 `sidecar-rpc.md` 中补充 `overview.get` 方法定义。

## 9. 风险与缓解

### 风险 1：Sidecar 与 v2 后端开发节奏不同步

缓解：
- Sidecar L1 只依赖 YAML 文件直读，不依赖 v2 的 `domain/` 完成度
- L1 阶段 handler 可直接用现有 `parse_simple_yaml` 临时实现
- v2 M1 完成后再将 handler 切换到正式 service 层

### 风险 2：事件流实现复杂度超预期

缓解：
- L1-L2 不实现事件流，仅 L3 引入
- 事件流先实现轮询兼容模式（`run.agent.get` 带 event_cursor），再补推送模式
- 推送模式可在 v2 M3 `domain/events.py` 稳定后再接入

### 风险 3：Overview 聚合查询性能

缓解：
- 首版 Overview 可接受全量扫描（数据量小：<100 张证据卡）
- 后续优化可引入 SQLite 缓存或增量统计

### 风险 4：PersonalProfile / JobLead 等新实体影响 v2 plan

缓解：
- 新实体先以最小字段集加入 `domain/models.py`
- 不破坏现有 EvidenceCard / JobProfile / MatchingReport 的定义
- `autonomous-agent-delivery-loop-v2.md` 中的 M1 Slice 1 `models.py` 范围需同步扩展

## 10. 对现有计划文档的修改建议

### 需要更新的文档

| 文档 | 修改内容 |
|------|---------|
| `autonomous-agent-delivery-loop-v2.md` | M1 `domain/models.py` 补充 PersonalProfile / JobLead / UploadedResume / ActivityLog；M1 `infra/` 补充 file_storage / credential_store |
| `ui/design/contracts/sidecar-rpc.md` | 补充缺失的 RPC 方法（详见下方缺失方法清单） |
| `AIEF/context/tech/architecture.md` | 补充 Sidecar Bridge Layer 在系统组件中的位置 |
| `gui-first-batch-kickoff.md` | 后续批次切分建议中添加对 Sidecar L1-L3 的依赖说明 |
| `m1-slice-1-breakdown.md` | `models.py` 的实体清单需扩展 |

### sidecar-rpc.md 缺失方法清单

对比 `DESIGN.md` 中的 UI 操作与 `sidecar-rpc.md` 已定义的 20 个方法，以下方法在 UI 中有明确操作入口，但 RPC contract 尚未定义：

| 缺失方法 | UI 操作入口 | 页面 | 优先级 |
|----------|-----------|------|--------|
| `evidence.create` | "New Card / 新增" 按钮 | Evidence | P0 |
| `evidence.update` | 详情面板 编辑图标 | Evidence | P0 |
| `evidence.delete` | 详情面板 删除图标 | Evidence | P0 |
| `overview.get` | Overview 页面整体数据 | Overview | P0 |
| `resume.upload` | "Upload Resume / 上传简历" 按钮 | Resumes | P1 |
| `resume.getPreview` | 预览面板渲染 | Resumes | P1 |
| `jobs.createProfile` | "New Profile / 新建" 按钮 | Jobs | P1 |
| `jobs.updateProfile` | Profile 编辑 | Jobs | P1 |
| `jobs.deleteProfile` | Profile 删除 | Jobs | P2 |
| `profile.get` | 个人资料读取 | Resumes | P1 |
| `profile.update` | "Edit Info / 编辑资料" | Resumes | P1 |

说明：
- P0 方法必须在 Sidecar L1-L2 阶段补齐 contract 并冻结
- P1 方法必须在 Sidecar L2 阶段补齐
- 补充时必须同步更新 `sidecar-rpc.md` 与 `DESIGN.md` 协议摘要（按双文件联动规则）

### 不需要更新的文档

| 文档 | 原因 |
|------|------|
| `ui/design/DESIGN.md` | UI 设计规范已冻结，后端适配 UI 而非反过来 |
| `ui/design/piproofforge.pen` | 设计稿已冻结 |
| `constitution.md` | 项目原则不受影响 |

## 11. 实施优先级总结

```text
立即可做（无依赖）：
  ├── Sidecar L1: server.py + lifecycle.py + evidence 只读 handler
  └── v2 M1: domain/models.py (含新实体) + infra/yaml_io.py

M1 完成后：
  ├── Sidecar L2: CRUD handlers + 分页筛选
  └── v2 M2: 引擎迁移

M2 完成后：
  ├── Sidecar L3: run handlers + event_bus
  └── v2 M3: orchestration + state_machine

M3 完成后：
  ├── Sidecar L3 补齐: submission.retry + 截图
  └── v2 M4: channels + RunStore
```
