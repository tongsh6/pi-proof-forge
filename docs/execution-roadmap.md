# Execution Roadmap / 项目推进路线图

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

`external_l3_submission_validation`

下一次“继续推进项目”默认只处理 `acceptance/journey_implementation_matrix.yaml` 中第一个 `status: next` 的任务。

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
- 必须验证 complete job profile 与 saved eligible evidence 的选择、resume positioning 记录、匹配报告、简历、PDF、Scorecard、gap tasks 和事实追溯。

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

### P0-011 Channel Session Setup

Status: `deep_verified`

Journey step: `channel_session_setup`

Depends on:

- `agent_run_guided_batch`

Vision link:

- 在受控投递前建立人工登录/会话边界。
- 必须验证不保存密码、不绕过验证码、不触发真实投递，只做渠道 session 状态与人工操作入口。

Expected evidence:

- L1 acceptance：`tests/acceptance/test_scenario_channel_session_setup.py`
- GUI acceptance：外部真实页面自动化（待实现）

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

Status: `next`

Journey step: `external_l3_submission_validation`

Depends on:

- `closed_loop_e2e_audit`

Vision link:

- 将已验证的本地/check-mode 闭环推进到受控外部渠道验证。
- 必须继续保持显式用户授权、最终提交门禁、频控、target verify、无 secret/captcha 绕过和可回溯反馈记录。

Expected evidence:

- L3 主入口：`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3`
- 待补：真实外部渠道成功记录，或清晰的 live blocker 记录；不得在缺少用户授权和最终确认时触发真实提交。

## Machine Contract

机器可读真源是 `acceptance/journey_implementation_matrix.yaml`。

本文件和矩阵的基本约束由 `python3 tools/check_execution_roadmap.py --root .` 与 `tests/acceptance/test_journey_implementation_matrix.py` 锁定。
