# Execution Roadmap / 项目推进路线图

> 仓库文档中的 `<local-candidate>` 为脱敏占位；真实候选名称、路径与执行安排仅保存在本机记录。

本文件决定“下一步做什么”。`docs/project-ledger.md` 只记录事实，本文件维护推进顺序、依赖和完成口径。

路线图必须同时对齐：

- 项目愿景：`PLAN.md` 的 evidence-first 求职引擎。
- 项目宪法：`constitution.md` 的 Evidence-First、No Fabrication、Spec-First、TDD、外部自动化驱动真实页面验收。
- 核心系统设计：`openspec/specs/pi-proof-forge-core.md` 的 v2 六边形领域核心和核心 pipeline。
- Agent 设计：`openspec/changes/autonomous-agent-delivery-loop/design.md` 的 10 状态机、Gate、Review、Delivery。
- GUI 设计：`ui/design/DESIGN.md` 的 9 页信息架构与页面职责。

## Vision Alignment

PiProofForge 的主线不是“把页面做完”，而是完成可追溯的 evidence-first 求职闭环：

1. 原始材料资产化为 Evidence Cards，且 `results` / `artifacts` 缺失不得进入候选池。
2. Job Profile/JD 与 Evidence Cards 做可解释匹配，输出分项得分、理由、缺口任务。
3. 简历生成坚持模板拼装优先、LLM 受控改写次之，不引入无证据事实。
4. Scorecard 反驱补证据任务，而不是降低事实保真标准。
5. 投递与反馈回流到版本、权重、模板和证据补全。

因此路线图中的任何 `next` 任务都必须说明它推进了上述哪一段闭环，不能只因为局部实现容易就插队。

## System Design Alignment

执行路线必须遵守以下设计边界：

- GUI 页面顺序和职责以 `ui/design/DESIGN.md` 为准：Overview -> Resumes -> Evidence -> Jobs -> Quick Run -> Agent Run -> Submissions -> Policy -> System Settings。
- Quick Run 是 4 阶段单次 pipeline：Evidence Extraction -> Matching -> Generation -> Evaluation。
- Agent Run 是 10 状态机：INIT -> DISCOVER -> SCORE -> GENERATE -> EVALUATE -> GATE -> REVIEW -> DELIVER -> LEARN -> DONE。
- Policy 承载 Gate Policy 与 Exclusion List；System Settings 承载 Channels 与 LLM Config。
- 业务实现必须保持 v2 架构边界：domain 零外部依赖，engines/orchestration 向内依赖，infra 是唯一外部 IO/LLM/YAML 适配层。
- 新的 GUI 结构性变更必须同步 `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen`，否则不得标为完成。

## Current Mainline

用户旅程闭环：

`系统设置配置 LLM -> 简历中心个人资料和材料库 -> 证据页提炼/维护 Evidence Cards -> Jobs 建立岗位画像 -> Quick Run 生成匹配报告/简历/Scorecard -> Agent Run 门禁/审批/投递 -> Submissions 反馈迭代`

## Current Focus

`small_company_high_match_delivery`

P0-026 是唯一 `next`。当前优先解决结果证据的完整性与共同消费，任务状态以机器矩阵为准；个人候选、履历、源材料和真实运行记录不在本路线图中发布。

### 已完成的工程切片

- 正文量化只消费实际渲染的精确结果 Fact；同卡同文但未采用的结果不能借证。
- 来源版本失效后，规则、非语义 judge 与四层报告一致撤去旧 trace 的权威。
- 逐事实范围的引文在绑定文档内必须唯一；普通复审不能静默擦除歧义范围，显式恢复保留合法兄弟事实。
- 来源歧义提示和显式撤销已通过组件行为验证；原生页面深验尚未完成。
- 应用资产各阶段的工程验收结果见 [Project Ledger](project-ledger.md)；离线全量测试与工程门禁不代替本任务的真实 App 验收。

### 下一实施与验收

验收入口：`外部真实 Tauri 页面自动化：small_company_high_match_delivery`。这是既定的外部真实页面验收方式；该任务的专用外部自动化脚本尚未实现，不能把入口描述当作可执行命令。验收继续覆盖公司事实与偏好筛选、完整 JD、语义匹配、可追溯简历和 Scorecard，以及明确授权后的投递与反馈。历史本机结果不能代替本次验收。

1. 现有批量提炼允许截句、使用计划词表分流且仅检查包含关系。先在既有提炼和证据复审中核定完整命题、现行原文版本及测量条件，再由正文和 R3.2 共同消费。
2. 接通旧事实扩大引文后重新采纳的页面流程；复用来源复审入口，不新增平行编辑器或事实账本。
3. 同文数字的实测、预测、目标、模拟假设分别定位并理解；保留非量化成果、测试环境与未知项，不以唯一引文或词形替代语义。
4. 真实 JD + Splash、正式简历和实际投递验收仍未完成，须在明确授权范围内执行。离线工程继续推进，不以未经授权的真实验收为前提。

### 招聘平台接入批次（应用规划）

| 顺序 | 任务 | 范围与退出条件 |
| --- | --- | --- |
| S1 / P0-011 | 官方凭据与只读接入 | 搜索、完整 JD、来源身份和失败语义分别验证；只读能力不授予平台写权限 |
| S2 / P0-017A | 投递前置契约 | 固定岗位与内容版本、审批续跑、稳定岗位键、防重与权威回执 |
| S3 / P0-017 | 授权外部闭环 | 实际发送版本、业务回执、日志与反馈互相可追溯，未知结果不重试 |
| S4 / P0-018 | 每日受控投递 | 合并所有启用平台的限额；暂停、撤销、跨日及重启防重有效 |
| S5 / P0-019 | BOSS 来源 | 在线接入受外部契约阻塞时保留原因，人工导入不能冒充在线只读验收 |
| S6 / P0-020、P0-021 | 智联、51job 来源 | 每个平台独立验证；来源导入与投递能力分开表述 |
| S7 / P0-022、P0-023 | 脉脉、拉勾来源 | 复用完整 JD 手工导入、来源标记和结果跟踪 |
| S8 / P0-024 | 六平台覆盖验收 | 明确每家来源覆盖、在线读取和实际投递的独立状态 |
| P0-025 | 平台反馈回流 | 复用来源身份与已有投递记录，不伪造反馈或因补证重复发送 |

具体状态与顺序见 `acceptance/journey_implementation_matrix.yaml`。P0-026 之后的任务按依赖继续推进；外部契约阻塞只影响相应能力，不删除目标，也不形成并行 WIP。协议与接入依据见 [招聘平台接入方案](../AIEF/docs/plans/2026-09-27-recruitment-platform-integration.md)。

## Accepted Delivery Goal / 已确认的近期投递目标

应用主动发现 JD，以语义理解判断匹配，复用有来源的职业事实生成定向简历，并在另行授权范围内形成投递与跟踪闭环。每天实际投出 1–3 份合适简历是结果，不是凑量指标。

- 简历以获得面试为目标，正文事实必须能追问、能回溯；主导、参与和对接范围按真实证据表达。
- 优先复用已核实底稿，缺少合适版本时沿现有生成链补齐；不把手工提供成品 PDF 设为默认前提。
- 各平台共用明确的每日上限。候选不足、登录失效或结果未知时报告原因，不以检查模式、模拟成功或重复投递补足次数。
- 持续授权明确渠道、候选范围、简历版本、上限和有效期，支持暂停与撤销；功能规划和质量建议不替代具体外部操作授权。
- 实际链路从官方或人工来源、完整 JD、可解释匹配、定向版本、审批到回执与反馈逐项验收。具体个人候选及投递结果只保存在本地业务记录。

### 已有能力探索

| 职责 | 复用对象 | 推进约束 |
| --- | --- | --- |
| 事实来源与复审 | 材料库、Evidence Cards、字段来源、逐事实范围和现行修订 | 来源定位不能代替完整命题成立，变更撤去旧权威 |
| 匹配与选材 | 语义报告、精确事实引用、resume plan 和 trace | 不以关键词命中代替理解，不从未呈现证据取得正文覆盖 |
| 生成与评估 | 现有模板、共享 HTML/PDF 导出、四层质量报告 | 正文与评分共同消费已核定结果，合成排版不替代真实简历验收 |
| 授权与发送 | 审批快照、岗位身份、投递占位及回执记录 | 未知不重复发送，外部副作用以具体授权为边界 |
| 反馈 | 既有投递记录、平台反馈与个人复盘的独立来源 | 明示真实反馈与个人复盘，不把观察状态升级为招聘方意图 |


## Efficiency And Quality / 效率与质量约束

- 工程取舍遵守 `constitution.md` 第 6 条：质量达标、效率优先、成本可控，不做重型工程。
- 新增内容或功能前遵守第 7 条，先探索已有设计与实现，在当前任务中说明复用点和缺口；对已有能力优先修复或接通。
- 在当前任务与依赖范围内，优先处理影响用户闭环的具体缺陷；用最小可验收切片推进，不以扩大框架或完善审计层本身作为进展。
- 方案需要新增依赖、架构层或明显增加模型调用时，简述它解决的实际问题、收益和维护成本；复用当前任务记录即可，不新增固定评审流程。
- 验证覆盖受影响行为、关键失败路径与必需门禁；只有声明真实旅程完成时，才必须具备对应的真实页面或渠道证据，小改动不重复执行无关全链路。
- 达到约定验收标准后收口；后续优化仅在存在实际质量缺口、运行瓶颈或重复维护成本时进入任务队列。

## WIP Rules

- 一次只推进一个 journey step。
- 未达到 `deep_verified` 的上游依赖，不允许推进下游深度验收。
- 新功能不能只以源码 marker 或页面加载作为完成口径。
- 每个 `verified_native` 或 `deep_verified` 任务必须有自动化验收脚本和完成证据。
- 场景化验收必须由外部自动化驱动真实页面、真实 Tauri 桌面壳或真实浏览器边界；内部 handler/unit/contract 和 audit 只能作为辅助或汇总证据。
- 遇到同优先级任务时，按旅程顺序推进，而不是按局部可做性随机选择。
- `next` 任务必须映射到项目愿景的一段闭环和 GUI/系统设计中的明确页面职责。
- 对业务能力新增或语义变更，必须优先补 OpenSpec/设计计划或确认已有设计覆盖；实现必须带失败测试或验收缺口测试。

## Task Queue

### P0-001 System Settings LLM Deep Acceptance

Status: `deep_verified`

Journey step: `system_settings_llm`

Vision link:

- 保障后续证据提炼、匹配、生成、评测有可配置模型供应商。
- 属于运行环境前置能力，不替代 evidence-first 主链路本身。

Unlocks:

- `quick_run_llm_consumption`
- `agent_run_llm_consumption`

DoD:

- 真实 Tauri shell。
- 真实 sidecar。
- 本地 OpenAI-compatible `/v1/models` stub。
- Provider defaults。
- 连接检查返回模型列表。
- 选择模型、保存、重新读回。
- API key 只回读 masked 状态。
- 未配置 base_url 返回结构化 `BLOCKED_LOCAL_PROVIDER`。

Evidence:

- 外部真实页面自动化（待实现）
- `docs/acceptance-depth.md`

### P0-002 Quick Run Consumes Persisted LLM Config

Status: `deep_verified`

Journey step: `quick_run_llm_consumption`

Depends on:

- `system_settings_llm`

DoD:

- 使用临时 policy 配置 LLM。
- Quick Run 真实 Tauri 页面读到同一 provider/model/base_url/masked key 摘要。
- Quick Run 启动结果或 run context 能证明使用的是持久化配置摘要。
- 仍以 Evidence Cards、Job Profile、Matching Report、Resume、Scorecard 为主链路产物，不把 LLM 配置验收误当成 pipeline 验收。
- 不泄露明文 API key。
- 失败时输出结构化验收事件。

Expected evidence:

- `tests/acceptance/test_scenario_quick_run_generate_and_evaluate_resume.py`
- `tests/unit/gui/test_quick_run_page_contract.py`
- `outputs/quick_runs/qr_*.json`
- `outputs/agent_runs/qr_*/summary.json`

### P0-003 Agent Run Consumes Persisted LLM Config

Status: `deep_verified`

Journey step: `agent_run_llm_consumption`

Depends on:

- `system_settings_llm`
- `quick_run_llm_consumption`

Expected evidence:

- `tests/acceptance/test_scenario_agent_run_guided_batch.py`
- `tests/unit/gui/test_agent_run_page_contract.py`
- `outputs/agent_runs/ar_*.json`

### P0-006 Quick Run Consumes Material-Derived Inputs

Status: `deep_verified`

Journey step: `quick_run_material_consumption`

Depends on:

- `evidence_material_sources`

DoD:

- Quick Run 真实 Tauri 页面能证明材料库来源已进入运行前上下文。
- Quick Run 启动结果或 run context 能证明使用的是材料派生 Evidence 与选中 Job Profile。
- 生成 Matching Report、Resume、Scorecard 时保留 Evidence Card 可追溯路径。
- 不把“页面能看到材料来源”误当成 pipeline 消费验收。

Expected evidence:

- 外部真实页面自动化（待实现）
- 外部真实页面自动化脚本（待实现）
- `outputs/quick_runs/qr_*.json`
- `outputs/agent_runs/qr_*/summary.json`

### P0-004 Resumes Material Library Native Acceptance

Status: `verified_native`

Journey step: `resumes_material_library`

Vision link:

- 对应 PLAN 的“日志层/原始材料”输入。
- 只是 evidence-first 的前置资产入口，完成后必须继续推进 Evidence Card 提炼与校验。

Evidence:

- 外部真实页面自动化（待实现）

### P0-005 Evidence Material Sources Native Acceptance

Status: `verified_native`

Journey step: `evidence_material_sources`

Depends on:

- `resumes_material_library`

Vision link:

- 将材料入口连到 Evidence 页面，但当前仍只到“来源可见”；下一层应推进 Evidence Card 提炼、review 和 results/artifacts 门禁。

Evidence:

- 外部真实页面自动化（待实现）

### P0-007 Evidence Card Extraction And Review

Status: `deep_verified`

Journey step: `evidence_card_extraction_review`

Depends on:

- `evidence_material_sources`

Vision link:

- 这是项目核心护城河：原始材料 -> Evidence Cards。
- 必须验证 raw_source、results、artifacts、review 决策和 No Fabrication。

Expected evidence:

- L1/API 合同：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_evidence_review_20260521 --level L1`
- 后端合同：`python3 -m pytest tests/unit/sidecar/test_evidence_handler.py tests/acceptance/test_scenario_generate_review_and_complete_evidence_card.py -q`
- GUI 合同：`python3 -m pytest tests/unit/gui/test_evidence_page_contract.py tests/unit/gui/test_i18n_catalog.py -q`
- 外部真实页面深度验收：外部真实页面自动化（待实现）

### P0-008 Setup Job Target Deep Acceptance

Status: `deep_verified`

Journey step: `setup_job_target`

Depends on:

- `evidence_card_extraction_review`

Vision link:

- 为 Evidence Cards 提供可解释匹配目标，是 Evidence -> Matching -> Resume 闭环的下一段。
- 必须验证 pasted JD、strict JSON draft、review 决策、incomplete/complete profile 门禁，以及可访问 source URL 时的 Job Lead 双向链接。

Expected evidence:

- L1/API 合同：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_job_target_20260521 --level L1`
- 后端合同：`python3 -m pytest tests/unit/sidecar/test_jobs_handler.py tests/acceptance/test_scenario_setup_job_target.py -q`
- 外部真实页面深度验收 主入口：外部真实页面自动化（待实现）

### P0-009 Quick Run Generate And Evaluate Resume

Status: `deep_verified`

Journey step: `quick_run_generate_and_evaluate_resume`

Depends on:

- `system_settings_llm`
- `evidence_card_extraction_review`
- `setup_job_target`

Vision link:

- 完成单岗位主链路：eligible Evidence Cards -> explainable matching -> fact-preserving resume/PDF -> scorecard/gap feedback。
- 必须验证 complete job profile/JD、Personal Profile、saved eligible evidence 的选择、resume positioning 记录、匹配报告、候选人可见简历、PDF、Scorecard、gap tasks 和独立事实追溯。
- 简历生成目标是“针对目标公司/岗位簇的可投递版本”，不是一份简历投所有公司/岗位；候选人 PDF 不得包含 `Evidence trace`、本机路径、source report、内部 evidence id 或系统版本标题，这些追溯信息必须进入 run record / `resume_trace` / scorecard。
- Scorecard 未达可投递阈值、Personal Profile 缺必需字段或仍有必需 gap tasks 时，Quick Run 必须输出 `NEEDS_REVIEW` / `NEEDS_EVIDENCE`，不得把 PDF 标为合格投递版本。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_quick_run_generate_and_evaluate_resume.py`
- GUI acceptance：外部真实页面自动化（待实现）
- Run record：`outputs/quick_runs/qr_*.json`
- Pipeline summary：`outputs/agent_runs/qr_*/summary.json`

### P0-010 Agent Run Guided Batch

Status: `deep_verified`

Journey step: `agent_run_guided_batch`

Depends on:

- `quick_run_generate_and_evaluate_resume`
- `agent_run_llm_consumption`

Vision link:

- 将已验证的单岗位 Quick Run 闭环扩展到 Agent Run 的 10 状态机。
- 必须验证 gate/review/delivery 边界：未人工批准不得进入外部投递，运行日志必须可追溯。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_agent_run_guided_batch.py`
- GUI acceptance：外部真实页面自动化（待实现）
- Run record：`outputs/agent_runs/ar_*.json`
- Review queue：`outputs/review_queue/ar_*.json`

### P0-011 Channel Session Setup / 官方凭据与只读接入

Status: `deep_verified`

历史工程结论：官方只读 HTTP、会话内 Token、Settings 验证/清理/简历预览和 Jobs 搜索入库已沿既有 infra 接通。状态沿用既有旅程验收决策；账号会话、搜索批次与原生操作记录仅保存在本机，不构成本次应用资产整理的新验收。

认证方法迁移不能继承旧浏览器路线的验收结果。验收须覆盖配置、业务成功、清理后的明确认证错误、既有线索保留，并分别核实完整 JD、指定简历版本及真实发送回执。官方入口与协议研究见 `docs/reports/2026-09-08-liepin-integration-research.md`。

Journey step: `channel_session_setup`

Depends on:

- `agent_run_guided_batch`

Vision link:

- 在受控投递前建立官方认证与真实岗位读取边界，为完整 JD 和可解释匹配提供可追溯输入。
- 用户在官方页面完成登录和取凭据；App 后端只读验证，不保存密码、不处理验证码、不触发简历修改或真实投递。

Expected evidence:

- 已执行入口：`CUA 原生动作记录：outputs/acceptance/liepin_official_readonly/native-readonly-live-20260928.json`。
- 原生动作链：配置凭据 → 验证后端只读能力 → 回读仅显示状态 → 搜索 → Jobs 查看真实结果；覆盖失效/清理后的状态复位。
- 契约验证：分别处理简历 `errCode` / 搜索 `code`、简历文本和列表字段、401/429/非 JSON；确认无写请求和凭据泄露。
- 9 月 browser 会话脚本及 `tests/acceptance/test_scenario_channel_session_setup.py` 是复用基础和历史证据，需增量更新，不能直接证明官方 Token 切片通过。

### P0-012 Submission Check Mode

Status: `deep_verified`

Journey step: `submission_check_mode`

Depends on:

- `channel_session_setup`
- `agent_run_guided_batch`

Vision link:

- 使用已验证渠道会话、已保存 Job Lead 和已生成 PDF 简历执行 check-mode 投递演练。
- 必须记录登录态、目标岗位、简历路径、频控、安全门禁和 submit_skipped，仍然不得触发最终投递。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_submission_check_mode.py`
- GUI acceptance：外部真实页面自动化（待实现）

### P0-013 Feedback Iteration After Check Mode

Status: `deep_verified`

Journey step: `feedback_iteration_after_check_mode`

Depends on:

- `submission_check_mode`

Vision link:

- 将 check-mode 的 scorecard gap、阻断原因或目标恢复结果转成可审计的迭代决策。
- 必须保留原始 artifact，记录用户选择，并路由回 Evidence、Jobs 或 Resume 生成，让下一轮 check-mode 有明确版本关联。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_feedback_iteration_after_check_mode.py`
- GUI acceptance：外部真实页面自动化（待实现）

### P0-014 Closed Loop E2E Audit

Status: `deep_verified`

Journey step: `closed_loop_e2e_audit`

Depends on:

- `feedback_iteration_after_check_mode`

Vision link:

- 审计完整 evidence-first 求职闭环是否已从 L1 合同、外部真实页面深度验收 证据和 journey report 上连成一条链。
- 不新增业务能力，优先补齐断裂的 traceability、验收覆盖和文档事实。

Expected evidence:

- L1 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_closed_loop --level L1`
- 已完成：L1 acceptance runner 内置 `closed_loop_e2e_audit`，审计 selected cases、journey rules、外部真实页面深度验收 evidence 和 Quick Run -> Agent Run -> Submissions -> feedback iteration traceability。
- 审计证据：`outputs/acceptance/acceptance_closed_loop_20260522/closed-loop-audit.json`

### P0-015 External L3 Submission Validation

Status: `deep_verified`

Journey step: `external_l3_submission_validation`

Depends on:

- `closed_loop_e2e_audit`

Vision link:

- 将已验证的本地/check-mode 闭环推进到受控外部渠道验证。
- 必须继续保持显式用户授权、最终提交门禁、频控、target verify、无 secret/captcha 绕过和可回溯反馈记录。

Expected evidence:

- L3 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3`
- 当前交付：L3 runner 默认生成 live blocker 记录；未显式授权或未单独最终确认时，`external_submission_attempted=false`。
- 真实渠道路径：仅当 `PIPF_EXTERNAL_L3_AUTHORIZED=true`、`PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true`、`PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true`、`PIPF_EXTERNAL_L3_SESSION_DIR` 指向已存在的共享 session 根目录且 Liepin 持久化会话目录包含非空、可识别的浏览器状态标记，并且 Job URL / resume PDF / profile / confirmed job id / confirmed recruiter 均已提供时，才允许启动 `tools.submission.run_submission --submit`。
- 证据：`outputs/acceptance/acceptance_external_l3/external-l3-validation.json` 与 `.md`。

### P0-016 External L3 Authorization Handoff

Status: `deep_verified`

Journey step: `external_l3_authorization_handoff`

Depends on:

- `external_l3_submission_validation`

Vision link:

- 将 External L3 blocker 转成可执行的授权交接包，而不是让用户只看到“未授权”。
- 必须列出下一次真实渠道验证所需 env、最终提交确认清单、禁止输入项和不含真实值的命令模板。

Expected evidence:

- L3 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3`
- 交接包字段：`operator_handoff.required_env`、`pre_run_checklist`、`forbidden_inputs`、`runbook`、`preflight_command_template`、`preflight_review_checklist`、`preflight_review_result`、`authorization_readiness_action_plan`、`authorization_intake_checklist`、`authorized_template_release_decision`、`live_run_go_no_go_decision`、`command_template`
- 证据：`outputs/acceptance/acceptance_external_l3/external-l3-validation.json` 与 `.md`

### P0-017A Official Delivery Prerequisites / 既定 S2

Status: `deep_verified`

状态与 journey 矩阵的 official_delivery_prerequisites 条目同步；实际个人回执与运行记录留在本地，不作为应用示例。旧 browser/API 交接说明不能替代当前路线的验收证据。

Journey step: `official_delivery_prerequisites`

Depends on:

- `channel_session_setup`
- `external_l3_authorization_handoff`

沿既定 S2 核实完整 JD、平台原始 ID/type、审核版本与实际发送内容的绑定和回执语义；补齐审批续跑、平台路由、最小稳定岗位键/in-flight 防重以及 API recorder/L3/runbook。仍受 P0-017 的具体目标与最终提交授权边界约束，不因为只读认证通过就试投。该阶段按下述首片推进，旧 browser handoff 的完成状态不替代 API 契约验收。

已实现的工程边界包括完整 JD 来源绑定、结构化解析、凭据安全存储、审批前版本固定及重复批准幂等。合成样本可验证预览、批准、明确检查/阻断和重开恢复；这类测试不能单独证明官方接口已发送指定内容。真实渠道验收必须核对实际发送版本与权威回执，不转入未经授权的其他渠道。

Expected evidence:

- 目标入口：`外部真实页面与官方契约验证：投递前置能力（待实现）`。
- 完整 JD 与审核版本可追溯、实际发送绑定有证据、成功/失败/未知回执有依据；未知结果不重试、不自动切换邮件。
- 真实 App 的审批/前置检查与辅助契约测试共同验证，无法绑定版本或缺关键接口时保留具体 blocker。

### P0-017 Authorized External L3 Live Run

Status: `deep_verified`

状态与 journey 矩阵的 authorized_external_l3_live_run 条目同步。具体目标、个人资料、实际回执和渠道状态只在本地验收记录中保存；旧 CLI 浏览器路线的验证不能自动代表其他发送路线。

Journey step: `authorized_external_l3_live_run`

Depends on:

- `official_delivery_prerequisites`
- `external_l3_authorization_handoff`
- `channel_session_setup`

Vision link:

- 在用户显式授权并单独确认最终提交后，执行一次真实外部渠道 L3 验证，或记录真实渠道 blocker。
- 必须把真实渠道结果或 blocker 与 submission log、L3 validation record 和后续反馈追溯连接起来。

Expected evidence:

- 下列 session 目录、browser 步骤与旧 runbook 属于当前浏览器实现。官方 API 迁移必须同步 recorder、L3、runbook 与受影响验收，以后端凭据检查和版本/回执证据落实等价门禁；不得伪造浏览器状态文件，或将 Token 填进旧授权模板来放行。
- L3 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3`
- 前置条件：用户提供 `PIPF_EXTERNAL_L3_AUTHORIZED=true`、`PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true`、`PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true`、指向已存在共享 session 根目录的 `PIPF_EXTERNAL_L3_SESSION_DIR`、真实 Job URL、resume PDF、profile YAML、确认 job id 与确认 recruiter。
- 候选准备入口：`python3 -m tools.acceptance.external_l3_job_lead_bridge --lead-source <job_leads.yaml> --lead-index <n> --resume-pdf <resume.pdf> --profile <profile.yaml> --session-dir <session-root>` 可从已验证 Job Lead 与 check-mode submission log 自动生成脱敏确认包和 shell-safe env 模板；该模板默认不授权、不确认最终提交，仍需用户审批候选和授权边界。
- 人工运行入口：`docs/runbooks/external-l3-live-run.md` 是 P0-017 真实运行 runbook；`operator_handoff.runbook` 和 Markdown 报告必须引用该路径，并声明文件存在状态、SHA256 指纹、必需章节完整性、运行前必须复核、复制命令前必须替换 live 输入、原始 live 输入不持久化。
- 预检证据：`external-l3-validation.json` 必须包含 `live_run_readiness.ready`、`submit_command_allowed`、`missing_gates` 和逐项 gate 状态；真实输入 gate 必须覆盖 Job URL 格式、resume PDF 文件存在且扩展名有效、profile YAML 文件存在且扩展名有效。
- Pre-submit blocker 诊断证据：submit 命令启动前产生 live blocker 时，`live_blocker.failed_checks` 与 `live_blocker.diagnostics` 必须直接汇总 missing gates、readiness gates 和输入产物审计摘要；`external-l3-validation.md` 必须同步展示 submit 是否允许启动、missing gates 和输入审计摘要，journey contract 必须拒绝 Markdown 与 JSON blocker 诊断不一致的报告。
- Readiness 语义：`live_run_readiness` 只表示 submit 命令启动前的 gate 结果；命令执行后的 traceability blocker 必须记录在 `submit_safety_decision.post_run_blocker_reason` 和 `live_blocker`，不得回写成 pre-run gate 失败；journey contract 必须验证 `submit_safety_decision` 中的 blocker reason 与 `live_blocker.reason` 一致。
- 输入产物证据：`external-l3-validation.json` 必须包含 `live_input_artifacts`，用 scheme/host、文件扩展名、大小与 SHA256 证明本次验证绑定到具体输入产物，同时不持久化 Job URL 原值、确认值、文件原始内容或 resume/profile 文件名；文件名字段只能写 `<redacted>` 与 `basename_persisted=false`。`external-l3-validation.md` 必须同步展示文件名与原内容未持久化结论，让人工审阅无需深挖 JSON。
- 频控证据：`external-l3-validation.json` 必须包含 `rate_limit_policy`，并把 max-per-batch、cooldown seconds、daily limit 显式传给真实 submit 命令；频控被关闭时必须在 submit 前阻断。
- 人工会话证据：`external-l3-validation.json` 必须包含 `session_readiness`、`manual_session_ready_confirmed` gate 和 `manual_session_storage_ready` gate；真实渠道命令启动前必须由用户确认共享渠道 session 已通过人工登录或刷新可用，设置 `PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true`，且 `PIPF_EXTERNAL_L3_SESSION_DIR` 指向已存在的共享 session 根目录并包含至少一个非空 Liepin 持久化会话状态标记，例如 `Local State`、`Default/Preferences`、`Default/Network/Cookies` 或 `storage-state.json`；空文件和 `.DS_Store` 等误放文件不得计为状态证据。未确认或 session 存储未准备好时必须阻断在 submit 命令启动前，自动化不得接收或持久化密码、验证码或短信码。
- 禁止输入证据：`external-l3-validation.json` 必须包含 `forbidden_input_audit`，只记录 forbidden env 是否出现，不记录原值；一旦提供密码、验证码、短信码或原始密钥类输入，必须在 submit 命令启动前记录 `forbidden_external_l3_sensitive_inputs` blocker。
- 目标确认预检证据：`external-l3-validation.json` 必须包含 `target_confirmation_audit`，只记录 Job URL 岗位 ID 是否可解析、确认岗位 ID 是否提供、二者是否一致、确认 recruiter 是否提供，以及 recruiter 页面匹配必须由 `target_verify` 证明的边界；不记录原始 ID 或 recruiter 原值；岗位 ID 二者不一致时必须在 submit 命令启动前记录 `target_confirmation_mismatch` blocker。
- 命令审计证据：真实渠道命令执行后，validation record 只允许保存脱敏 command 和脱敏后的 stdout/stderr 尾部，不能保存 Job URL、resume/profile 路径、确认 job id 或确认 recruiter 原值。
- 提交安全证据：`external-l3-validation.json` 必须包含 `submit_safety_decision`，记录最终提交命令是否被阻断、允许待执行或已执行，并保留授权、最终确认、真实输入和禁止凭据/验证码输入的决策依据；pre-submit blocker 的 `blocking_reason` 与 post-command blocker 的 `post_run_blocker_reason` 必须分别与同一条 `live_blocker.reason` 对齐。
- 授权确认证据：`operator_handoff.authorization_packet` 必须记录必需确认声明、授权签核清单、签核待补数、证据清单、中止条件、脱敏策略和禁止输入项，且不持久化原始确认值；授权签核清单必须把外部渠道授权、最终提交确认、人工 session、真实输入产物、目标确认和禁止输入映射到 env、gate、source_path、status 与原值不落盘边界；`operator_handoff.authorization_packet.pending_acknowledgement_count=0` 是模板发布、Go/No-Go 放行和授权模板执行前置条件；确认声明、中止条件和 pre-run checklist 必须覆盖 `PIPF_EXTERNAL_L3_SESSION_DIR` 指向已存在 session 根目录且 Liepin 持久化会话目录包含非空、可识别浏览器状态标记；`operator_handoff.runbook` 必须把交接包绑定到中文真实运行 runbook 的路径、SHA256 和必需章节完整性；`operator_handoff.runtime_options` 必须记录当前 channel、session/output 目录、timeout 和 headless 配置；`operator_handoff.preflight_command_template` 必须保持 `PIPF_EXTERNAL_L3_AUTHORIZED=false` 和 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=false`，用于无授权本地预检；`operator_handoff.preflight_result_expectation` 必须说明预检正常结果应为 `live_blocker_recorded` / `explicit_user_authorization_required`，且不触碰外部渠道、不完成 P0-017；`operator_handoff.preflight_review_checklist` 必须把授权模板执行前的复核项结构化到 validation 状态、blocker reason、外部提交未启动、submit 命令未允许、P0-017 未完成、输入审计脱敏、session、频控、证据清单、runbook 指纹和反馈追溯；`operator_handoff.preflight_review_result` 必须对这些复核项写出 observed 值和 pass/fail，并把真实运行输入、session 或目标确认缺口记录为 `authorization_decision_blockers`；`operator_handoff.authorization_readiness_action_plan` 必须把这些缺口转成可执行待补行动，覆盖人工 session、Job URL、resume PDF、profile YAML 和目标确认的必需证据与原值不落盘边界；`operator_handoff.authorization_intake_checklist` 必须把显式授权、最终提交确认、人工 session、session dir、Job URL、resume PDF、profile YAML、确认 job id 和确认 recruiter 映射到 env、占位符、gate、当前状态和原值不落盘边界；`operator_handoff.authorized_template_release_decision` 必须在待补行动清零、授权输入接收清单清零、授权签核待补数清零、预检复核允许进入授权决策、authorization packet 就绪、显式授权和最终提交确认存在前保持 `template_released_to_operator=false`、`copy_execution_allowed=false`，并列出发布阻断项与发布前必需条件；`operator_handoff.live_run_go_no_go_decision` 必须汇总 readiness、submit safety、行动计划、输入清单、授权签核计数、模板发布决策和 P0-017 完成门禁，在授权模板未发布或 submit 命令未允许前保持 `go_for_live_run=false`、`submit_command_may_start=false` 和 `copy_authorized_template_allowed=false`，且每个 no-go blocker 必须映射到处理路线、证据来源和必需证据；`operator_handoff.live_run_execution_sequence` 必须把预检、复核、No-Go 路线处理、授权行动、授权输入、授权签核、模板发布、Go/No-Go、授权模板执行和 P0-017 完成验证排成结构化顺序门禁，并把第一处阻断作为下一可执行步骤；真实渠道命令已执行但 P0-017 未完成时，状态必须是 `authorized_live_run_executed_pending_p0_verification`，并把 `next_executable_step` 指向 `verify_p0_017_completion`，避免把 post-command blocker 误读为还没执行授权模板；只有这些缺口清零时才允许进入授权决策，且在真实运行前始终保持 `authorized_template_execution_allowed=false`；`operator_handoff.command_template` 必须使用 shell-safe 的 live 输入占位符，并反映这些运行配置与当前有效频控参数；`external-l3-validation.md` 必须分开展示本地预检模板、预检预期结果、预检复核清单、预检复核结果、授权就绪行动计划、授权输入接收清单、授权确认包与签核清单、授权模板发布决策、真实运行 Go/No-Go 决策、No-Go 处理路线、真实运行执行顺序门禁和授权真实运行模板，不能把已被覆盖或已失效的默认值写成下一次真实运行模板，也不能让路径空格或 `<...>` 占位符被 shell 误解析；`operator_handoff.command_template_review` 必须记录 `copy_paste_ready=false`、占位符替换要求、显式授权要求、独立最终提交确认要求、人工会话可用确认要求、session 存储就绪确认要求、执行顺序、预检模板不启用授权/最终提交、授权模板执行前必须按预检复核清单与复核结果复核证据，避免操作者把带授权 env 的模板盲贴为真实运行命令。
- 授权确认 verifier：`external_l3_authorization_packet_recorded` 必须同时覆盖无授权 no-go 态、签核清零的授权待执行态和真实渠道命令已执行态；当 `operator_handoff.authorization_packet.status=executed` 且签核计数为 `pending_acknowledgement_count=0` / `satisfied_acknowledgement_count=6` 时，journey report 必须把确认包判为有效执行态，而不是回退为缺失。
- 证据清单：`external-l3-validation.json` 必须包含 `evidence_manifest`，统一列出 validation JSON/Markdown、关键嵌入段、中文真实运行 runbook、preflight review checklist/result、authorization packet、authorization readiness action plan、authorization intake checklist、authorized template release decision、live run Go/No-Go decision、live run execution sequence、P0-017 completion gate、live blocker 或 submission log、feedback source 的位置、必需性、存在状态和 `raw_live_inputs_persisted=false`；runbook 清单项必须与 `operator_handoff.runbook` 的路径、指纹和章节完整性一致；authorization packet 清单项必须证明签核清单、签核待补数和原值不落盘边界自洽；preflight review checklist/result、authorization readiness action plan、authorization intake checklist、authorized template release decision、live run Go/No-Go decision、live run execution sequence 与 P0-017 completion gate 清单项必须与 `operator_handoff` 的必需复核项、待补行动、env/gate 映射、签核计数、发布阻断项或发布成功态、发布前必需条件、no-go 决策或 go 决策、resolution routes、执行顺序和路线图完成证据一致；`external-l3-validation.md` 必须逐项同步展示同一清单的位置、必需性、存在状态和状态值，journey contract 必须拒绝 Markdown 与 JSON 清单不一致的报告，让人工复核无需在多个 JSON 段之间拼接证据边界。
- 结果分级：`external-l3-validation.json` 必须包含 `outcome_summary`，明确 runner `pass` 只代表证据写出与验收规则通过；必须区分 `pre_submit_blocker_recorded`、`post_command_blocker_recorded` 和 `external_validated`，并在真实外部验证成功前保持 `p0_017_complete=false`。`external-l3-validation.json` 还必须包含 `p0_017_completion_gate`，逐项列出显式授权、最终提交确认、人工 session、session 存储、真实输入、外部提交、submission log 反向链接、submission log success、反馈追溯和 `external_validated` outcome 的完成证据；任一 required evidence 未满足时，必须保持 `acceptance_pass_is_completion=false` 并列出完成阻断项。`external-l3-validation.md` 与顶层 acceptance step message 必须同步展示该分级和完成门禁，并区分 submit 命令未启动与命令后 blocker；blocker 场景中的 `outcome_summary.next_action` 必须与 `live_blocker.next_action` 一致，Markdown 中的 outcome、blocker reason、next action 和 P0-017 完成门禁必须与 JSON 一致，避免顶层摘要把“阻断被正确记录”误读为“P0-017 已完成”或给出另一个处理路径。
- 追溯证据：真实渠道命令即使返回成功，也必须解析并确认 `submission_log.yaml/json` 存在，且 submission log 路径必须位于预期 submission 输出根目录下，并写回本次 `external_l3_validation_run_id`、`external_l3_validation_path` 和匹配 validation record 的输入产物指纹；命令输出指向允许根目录外时，validation 和 Markdown 必须只记录允许根目录、路径边界结论和拒绝原因，不得读取相邻 JSON 或泄露被拒绝的原始越界路径；submission log 必须声明 `live_inputs_redacted=true` 与 `input_artifacts.job_url.raw_value_persisted=false`，其中的原始 Job URL、resume/profile 路径字段以及 `steps.detail` 内的确认岗位 ID、确认 recruiter、页面读取到的岗位 ID/招聘方等真实输入必须脱敏；External L3 模式下提交器不得捕获或引用原始浏览器截图或 HTML snapshot，SubmissionRecorder 必须在记录层忽略 screenshot 引用，validation 必须递归拒绝 submission log 中的截图/HTML snapshot 字段、嵌套诊断字段或路径片段，只能通过 `input_artifacts` 和存在性/匹配数摘要保留非内容型追溯；否则记录为 `submission_log_not_linked` blocker。只有 submission log 自身 `status=success` 时才能计为 `external_validated`；returncode 为 0 但 log status 不是 success 时必须记录业务 blocker，已知 `error` 使用精确 `external_channel_*` 归因，未知业务失败才回落到 `external_channel_submission_not_success`。
- 诊断证据：`submission_traceability` 必须记录 `checks` 与 `failed_checks`，并在 `external-l3-validation.md` 同步展示 failed checks 与逐项 checks 表；journey contract 必须拒绝 Markdown 检查表与 JSON 不一致的报告，让操作者能区分缺日志、JSON 不可解析、反向链接不匹配或输入产物指纹不匹配。
- Blocker 诊断证据：真实渠道命令执行后产生 live blocker 时，`live_blocker.failed_checks` 与 `live_blocker.diagnostics` 必须直接汇总 returncode、submission log 路径、traceability checks 和成功投递关键步骤摘要；当 submission log 可解析且 `error` 属于已知渠道业务失败时，即使命令 returncode 为 0，post-command blocker reason 也必须优先使用 `external_channel_rate_limited`、`external_channel_login_required`、`external_channel_security_redirect`、`external_channel_job_unavailable`、`external_channel_target_verify_failed`、`external_channel_submit_safety_failed`、`external_channel_send_resume_failed`、`external_channel_submission_uncertain` 或 `external_channel_runtime_failed` 等精确归因；`main_chat_click_failed:*`、`send_resume_click_failed:*`、`confirm_send_button_not_found`、`upload input not found*` 与 `phase=*` 这类真实发简历链路错误必须归入 `external_channel_send_resume_failed`。未知错误才回落到 `external_channel_command_returned_nonzero`；journey contract 验证器必须对 `batch_cooldown`、`daily_limit_exceeded` 等已知业务 error 与 blocker reason 做一致性校验，禁止只在文档中声明该要求。
- Submission log 业务摘要：当 `submission_log.json` 可解析时，validation record 必须把 status、error、mode 和已脱敏的 last step 写入 `submission_traceability.submission_log_summary`，并同步到 Markdown 报告与 post-command live blocker diagnostics；journey contract 必须拒绝缺少 mode 或 Markdown 摘要与 JSON 不一致的报告；即使原 submission log detail 触发 traceability blocker，也不得把原始 detail 复制进 validation record；如果 last step detail 包含未脱敏 target_verify 观测值或 HTML snapshot 描述，摘要必须使用脱敏占位。
- Submission log 关键步骤证据：成功投递的 `submission_log.json` 必须记录并通过 `rate_limit`、`login_check`、`target_verify`、`submit_safety`、`chat_send_resume` 和 `submit`；缺失或失败时不得把 returncode=0 信任为 L3 成功，必须转为 traceability blocker；Markdown 报告必须同步展示必需步骤、已记录步骤、缺失步骤和失败步骤，让人工复核无需深挖 JSON。
- Timeout 证据：真实渠道命令超时时，validation record 必须写出 `external_channel_command_timed_out` live blocker、timeout 秒数、脱敏 stdout/stderr tail 和下一步处理路径；Markdown 报告必须同步展示 timeout blocker 原因、超时状态和 timeout 秒数，journey contract 必须拒绝 Markdown 与 JSON 不一致的报告。
- 命令启动错误证据：真实渠道命令因浏览器、驱动、权限或本地运行时问题启动失败时，validation record 必须写出 `external_channel_command_launch_failed` live blocker，并脱敏保存错误类型/信息；Markdown 报告必须同步展示错误类型和脱敏错误信息，且不得泄露 Job URL 或本地文件路径。
- 反馈证据：`external-l3-validation.json` 必须包含 `post_submit_feedback_traceability`；成功时连接 submission log 到 feedback iteration，blocker 时连接 blocker record 到阻断处理路径；blocker 场景中的 `source_reason` 必须与 `live_blocker.reason` 一致，Markdown 报告必须同步展示与 JSON 一致的 `source_status`、`source_reason` 和下一步，避免后续反馈入口处理的是另一个原因。
- 证据：`outputs/acceptance/acceptance_external_l3/external-l3-validation.json`，以及真实渠道生成且反向链接 L3 validation 的 `outputs/submissions/liepin/*/submission_log.yaml/json`。

## Machine Contract

机器可读真源是 `acceptance/journey_implementation_matrix.yaml`。

本文件和矩阵的基本约束由 `python3 -m tools.cli.entrypoints check roadmap --root .` 与 `tests/acceptance/test_journey_implementation_matrix.py` 锁定。
