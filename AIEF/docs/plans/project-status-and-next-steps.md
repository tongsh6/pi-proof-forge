# 项目现状与下一步建议

> 生成日期：2026-03-08  
> 更新日期：2026-03-13  
> 基准：main 已完成 Sidecar L2 + 相关 bugfixes

---

## 1. 项目概况

- **定位**：Evidence-first 框架，将原始工作材料转为结构化证据，经可解释匹配生成事实保真的目标文档（简历等）。
- **产品形态**：桌面应用（Tauri + React + Python sidecar），CLI 与 GUI 并存。
- **规范体系**：OpenSpec 核心规范、AIEF 工作流与标准、GitFlow 发布流程、constitution 原则约束。

---

## 2. 仓库与版本状态

| 项目 | 状态 |
|------|------|
| **当前版本** | v0.1.8（已发布，含企业排除策略全链路） |
| **main / develop** | 同步，无待合并 feature |
| **release 分支** | release/v0.1.0 … v0.1.8 保留 |
| **质量门禁** | AIEF L3 通过，125 个单元测试通过 |
| **未提交改动** | 无 |

---

## 3. 规范与设计（已就绪）

- **核心规范**：`openspec/specs/pi-proof-forge-core.md` — 四阶段 pipeline、Agent Loop 扩展（DISCOVER/GATE/REVIEW/DELIVER/LEARN）、企业例外清单、auto/manual 双模式语义。
- **变更**：仅 **autonomous-agent-delivery-loop** 处于“设计完成、实现未收口”：
  - `design.md`：10 状态机、delivery_mode/batch_review、REVIEW 阶段与 RPC 合约。
  - `tasks.md`：Phase A～E 任务列表（多数未勾选）。
- **GUI 设计**：`ui/design/DESIGN.md`、`piproofforge.pen` — 各页面布局与 Policy 的 delivery_mode/batch_review 字段、Agent Run 的 REVIEW 审批面板已定义。
- **工作流文档**：evidence-extraction、matching-scoring、generation、evaluation、submission 阶段与脚本映射完整；submission 中明确“auto/manual 双模式设计完成，实现待落地”。

---

## 4. 实现现状（按模块）

### 4.1 已闭环能力

| 能力 | 实现位置 | 说明 |
|------|----------|------|
| **企业排除策略** | tools/policy、discovery、sidecar、UI | 规则加载、DISCOVER 过滤、GATE 兜底、策略页/系统设置编辑、持久化与 API；v0.1.8 已发布。 |
| **门禁快照** | sidecar settings、Policy 页 | 只读展示 n_pass_required、threshold、max_rounds、gate_mode。 |
| **证据提炼 / 匹配 / 生成 / 评测** | run_evidence_extraction、run_matching_scoring、run_pipeline、run_generation、run_evaluation | 现有 CLI 与 pipeline 可用；部分复用 domain 与 infra。 |
| **Sidecar** | tools/sidecar | 生命周期、router、settings/evidence/overview/jobs 等 handler；JSON-RPC over stdio。 |
| **Sidecar L2** | tools/sidecar/handlers | evidence CRUD、jobs CRUD + leads、profile、resume、submission 完整实现；所有 handler 已注册并通过测试；GUI 已完成真实数据对接。
| **Markdown→PDF 导出** | tools/infra/export/pdf_exporter.py | 使用 weasyprint 实现 Markdown 简历到 PDF 的真实转换，支持中文。
| **桌面 UI** | ui/src/pages | 9 个页面：overview、evidence、jobs、quick-run、agent-run、submissions、resumes、policy、system-settings；Policy 与系统设置已接 live 数据。

### 4.2 部分就绪（v2 地基）

| 模块 | 现状 | 缺口 |
|------|------|------|
| **domain/** | models.py（EvidenceCard 等）、value_objects.py（Score/Candidate/GateDecision 等）、protocols.py、result.py 存在 | 无 ReviewCandidate/ReviewDecision；invariants、events、run_state 未建或未接齐。 |
| **infra/** | llm/client.py、persistence/yaml_io.py 存在 | 无 config/（loader、validator、composer）；无 engines/registry；logging 等未统一。 |
| **policy/** | exclusions、gate、audit 已用 | 未接 PolicyConfig.delivery_mode/batch_review；配置仍来自 sidecar 与 YAML 分散读取。 |

### 4.3 未实现（设计已有）

| 能力 | 设计来源 | 实现缺口 |
|------|----------|----------|
| **run_agent.py** | core spec、design.md、tasks C6 | 仓库中不存在；无统一 Agent 循环入口。 |
| **REVIEW 阶段与 RPC** | design.md、DESIGN.md | 无 getPendingReview/submitReview；无 REVIEW 状态分支。 |
| **delivery_mode / batch_review** | design.md、DESIGN.md、tasks A10 | ✅ 已实现：sidecar settings 支持读写，Policy 页有完整控件。 |
| **Agent Run 审批 UI** | DESIGN.md | ✅ 已实现：前端页面 + 后端 handlers（run.agent.getPendingReview, submitReview, createReviewCandidates） |
| **orchestration/** | tasks Phase C | 无 agent_loop、Stage 组合、pipeline 与 agent 统一编排。 |
| **config/Composer** | tasks A12、core spec | 无 config 目录；无统一组装点。 |
| **EngineRegistry + 引擎层** | tasks Phase B | 无 engines/registry；run_* 仍直接调现有脚本逻辑，存在 if use_llm 等。 |
| **通道层 channels/** | tasks Phase D | 投递逻辑仍在 submission/，未抽象为 Channel Protocol + 降级。 |

---

## 5. 缺口与风险（简要）

- **自动/人工投递**：设计完整，实现未落地；若需“手动审批再投递”，需补 REVIEW 状态、RPC、Policy 配置与 Agent Run 页。
- **统一 Agent 入口**：无 `run_agent` 与 Composer，无法单命令驱动“DISCOVER→…→DELIVER”；架构迁移（Phase A～E）工作量大。
- **技术债**：design 中提到的 DRY/OCP 问题（多处 LLM/YAML、if use_llm、subprocess 串联）仅部分通过 policy/discovery/domain 缓解，未系统性消除。
- **Agent Run 页**：仅为占位，与设计中的“REVIEW 审批 + 事件流”差距大。

---

## 6. 下一步建议（按优先级）

### 6.1 短期（可独立交付、风险低）

1. **~~Policy 页补充 delivery_mode / batch_review~~** ✅ 已完成
   - 在 sidecar settings 与 types 中增加两字段（只读或可编辑，视产品决策）；Policy 页增加控件；不实现 REVIEW 逻辑也可先统一“策略配置”的展示与未来扩展。
   - 状态：已实现，已在 PR #13 中合并。

2. **Agent Run 页最小可用**
   - 按 DESIGN 做一版“只读”的 Agent Run：展示 run 列表或当前 run 状态、事件流占位；为后续 REVIEW 列表和审批操作留入口。
   - 依赖：sidecar 是否有 list_runs 或等效 RPC；若无则需先定义最小 RPC 再实现 UI。

3. **文档与体验沉淀**
   - 将本文件纳入 AIEF 计划索引或 experience；补充“v0.1.8 后推荐路线图”到 README 或 CONTRIBUTING（若有）；必要时更新 REPO_SNAPSHOT。

### 6.2 中期（打通一条完整 Agent 路径）

4. **实现 REVIEW 与 run_agent 最小闭环**
   - 在现有 pipeline 与 policy 基础上：增加“REVIEW”状态与简单状态机（GATE 通过 → REVIEW → 等待 RPC 或 auto pass-through）；实现 getPendingReview / submitReview；Agent Run 页展示待审批列表与 approve/reject。
   - 不要求先完成 Phase B/C/D 全量；可先“单轮、单通道、dry-run”可跑通，再逐步替换为 Composer + 通道层。

5. **配置收敛**
   - 引入 `tools/config/`：fragments（含 PolicyConfig.delivery_mode/batch_review）、loader、validator；sidecar 从 loader 或已有 settings 读取，保证与 design 一致；为后续 Composer 预留接口。

### 6.3 长期（架构迁移与规范对齐）

6. **按 tasks.md 推进 Phase A 收口**
   - 补齐 domain（ReviewCandidate/ReviewDecision、invariants、events、run_state）、config（composer）、infra 统一；A15 将 run_* 中重复 LLM/YAML 迁到 infra，并加回归测试。

7. **Phase B～E 渐进**
   - EngineRegistry + 引擎层（B）；orchestration/agent_loop + run_agent（C）；channels + run_store（D）；CLI 收口与质量门禁（E）。每阶段以 TDD 与 Exit Criteria 为准，避免大爆炸式重写。

8. **质量与合规**
   - 为 design 中“禁止 subprocess / 禁止 if use_llm / DRY”增加静态检查或 CI 步骤；Exit Criteria 中可自动化的条目均有测试或脚本校验。

---

## 7. 建议的“下一步动作”（二选一）

- **若优先“可演示的 Agent 体验”**：做 **6.1 的 1 + 2** 和 **6.2 的 4**（Policy 两字段 + Agent Run 页最小可用 + REVIEW RPC 与审批 UI），再视需要做 6.2 的 5。
- **若优先“架构与可维护性”**：做 **6.1 的 1、3** 和 **6.3 的 6**（Policy 两字段 + 文档与快照更新 + Phase A 收口），再按 tasks 顺序推进 B～E。

两者可并行：由不同人分别推进“体验”与“地基”，在 config 与 sidecar 接口上约定好 delivery_mode/batch_review 与 REVIEW RPC 即可。

---

## 8. 并行方案与路径

两条线可同时推进，通过**先约定接口、再各自实现**避免冲突；在约定处汇合一次即可合线。

### 8.1 两条轨道

| 轨道 | 目标 | 负责人可独立推进 |
|------|------|------------------|
| **体验线（L1）** | 用户可见：Policy 两字段、Agent Run 页、REVIEW 审批与 RPC | 以 UI + sidecar 扩展为主，不拆现有 run_* 架构 |
| **地基线（L2）** | 架构与可维护性：config、domain 补齐、Phase A 收口 | 以 tools/config、tools/domain、infra 为主，不改 UI 契约 |

### 8.2 先做的共同约定（第 0 步，建议首日完成）

在动手写两条线的代码前，先定好“契约”，避免后期接口对不上。

1. **Policy 与 settings 契约**
   - 在 **类型与文档** 中固定：
     - `delivery_mode: "auto" | "manual"`（默认 `"auto"`）
     - `batch_review: boolean`（仅当 `delivery_mode === "manual"` 时有效，默认 `false`）
   - 约定存放位置：sidecar 的 `settings.get` 返回的 payload 中（与现有 `gate_policy`、`exclusion_list` 同级），例如：
     - `settings.delivery_mode`
     - `settings.batch_review`
   - 约定：若 sidecar 暂未持久化，可先返回固定默认值；L1 只读展示时也成立。

2. **REVIEW 相关 RPC 契约**
   - 方法名与请求/响应形状（仅文档 + 类型，可先不实现）：
     - `run.agent.getPendingReview` → 返回 `{ candidates: ReviewCandidate[] }` 或空列表
     - `run.agent.submitReview` → 入参 `{ decisions: ReviewDecision[] }`，返回 `{ accepted: number }` 等
   - `ReviewCandidate` / `ReviewDecision` 字段以 `openspec/changes/autonomous-agent-delivery-loop/design.md` 与 `tasks.md` 中的 A2 为准（job_lead_id、company、position、matching_score、action 等）。
   - 约定：L1 可先做“无 run 时返回空列表”的 stub 实现；L2 的 domain 中先加 ReviewCandidate/ReviewDecision 值对象，供后续 RPC 与 agent_loop 共用。

3. **分支与合并策略**
   - 两条线各自在 **独立 feature 分支** 上开发（例如 `feature/policy-delivery-mode-ui` 与 `feature/config-and-phase-a`），合并前都先合并/拉取 develop，减少冲突面。
   - 若同改一文件（例如 `ui/src/lib/sidecar/types.ts` 的 settings 类型）：**先合 L2 的 config/类型变更，再合 L1 的 UI 使用**；或约定 L1 只扩展、L2 只改 tools 与类型定义，冲突时以“类型与 RPC 契约”文档为准。

### 8.3 体验线 L1 路径（按顺序）

| 步骤 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| L1.1 | 在 sidecar 的 settings 返回中增加 `delivery_mode`、`batch_review`（可从现有 gate_policy 或占位配置读，默认 auto / false） | settings.get 含两字段；TypeScript 类型更新 | 8.2 契约 |
| L1.2 | Policy 页：在 Gate Policy 区块下增加两控件（只读或下拉/开关），展示并可选持久化 delivery_mode、batch_review | 策略页可看到/可选改两字段 | L1.1 |
| L1.3 | Sidecar 实现 `run.agent.getPendingReview`、`run.agent.submitReview` 的 stub（无 run 时返回空；submit 返回 accepted:0） | RPC 可调、不报错 | 8.2 契约 |
| L1.4 | Agent Run 页：最小可用——调用 getPendingReview，展示“待审批列表”占位或空状态；审批按钮调用 submitReview（可先写死一条测试用 decision） | Agent Run 页有审批入口、可点可调 | L1.3 |
| L1.5 | 若有真实 run 数据源：将 stub 接上真实“当前 run 的 REVIEW 候选”，实现一次“单轮审批 → 调 submitReview”的闭环 | 端到端 manual 审批一次可跑通 | 视 run_agent / 现有 pipeline 是否产出 REVIEW 数据 |

L1 可在 L1.4 完成后先合并到 develop，L1.5 可与地基线“run_agent 最小闭环”一起做。

### 8.4 地基线 L2 路径（按顺序）

| 步骤 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| L2.1 | 新增 `tools/config/fragments.py`：定义 PolicyConfig（含 delivery_mode、batch_review、excluded_companies、excluded_legal_entities 等），与 design 一致 | 配置模型统一、可被 sidecar 与后续 Composer 读 | 8.2 契约 |
| L2.2 | 新增 `tools/config/loader.py`（从 YAML + 环境/侧载读）+ `tools/config/validator.py`（校验必填与范围）；sidecar 的 gate_policy / 排除列表可改为从 loader 读（可选，不强制一次改完） | 配置有唯一入口、校验集中 | L2.1 |
| L2.3 | 在 `tools/domain/value_objects.py` 中增加 ReviewCandidate、ReviewDecision（与 tasks A2 一致），保证可序列化、不可变 | domain 层有 REVIEW 相关值对象 | 8.2 契约 |
| L2.4 | 按 tasks Phase A 其余项查漏：invariants、events、run_state、infra 统一（logging 等）；A15 可将 run_* 中重复 LLM/YAML 抽到 infra，并加回归测试 | Phase A 收口、为 B 做准备 | L2.1–L2.3 |

L2 不直接改 Agent Run 页或 REVIEW 交互逻辑；L2 的 config 与 domain 变更要为 L1 的 RPC 与后续 run_agent 提供类型与数据来源。

### 8.5 汇合与合线

- **第一次汇合**：L1.1 + L1.2 与 L2.1 + L2.2 都完成后，在 develop 上合并两条 feature 分支。若有冲突，以 8.2 的“Policy 与 settings 契约”为准；TypeScript 类型以 sidecar 实际返回为准。
- **第二次汇合**：L1.3 + L1.4 与 L2.3 都完成后，再次合并。此时 sidecar 的 getPendingReview/submitReview 可逐步从“返回 stub”改为“使用 domain 的 ReviewCandidate/ReviewDecision + 真实 run 状态”。
- **合线后**：在 develop 上做 L1.5 + “run_agent 最小闭环”（单轮、REVIEW 状态、GATE→REVIEW→DELIVER 或 pass-through），并让 Agent Run 页接真实 run 与审批流；L2 继续 Phase B～E。

### 8.6 并行路径一览

```
第 0 步（共同）  约定 delivery_mode/batch_review 与 REVIEW RPC 契约、分支策略
       │
       ├── 体验线 L1 ──► L1.1 settings 两字段 ──► L1.2 Policy 页控件 ──► L1.3 RPC stub ──► L1.4 Agent Run 最小页
       │                                                                        │
       └── 地基线 L2 ──► L2.1 config/fragments ──► L2.2 loader+validator ──► L2.3 domain Review* ──► L2.4 Phase A 收口
                                                                                    │
第一次汇合 ◄────────────────────────────────────────────────────────────────────────┘
（合并 L1.1+L1.2 与 L2.1+L2.2，解决类型/配置冲突）

第二次汇合 ◄── L1.3+L1.4 与 L2.3 合并（REVIEW 类型与 stub 对齐）

合线后 ──────── L1.5 + run_agent 最小闭环 + L2 Phase B～E 按 tasks 推进
```

按上述路径并行，两条线仅在“契约”和两次汇合处对齐，其余可独立开发与提交流程。
