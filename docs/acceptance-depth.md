# 自动化深度验收规范

本规范用于判断自动化验收是否足以证明一个用户目标已经真实闭环。

## 判定标准

一个验收脚本只有同时满足以下条件，才算深度验收：

1. 有明确用户目标，不只检查页面或字段存在。
2. 执行真实动作链，覆盖用户会触发的关键状态变化。
3. 由外部自动化驱动真实页面、真实 Tauri 桌面壳或真实浏览器边界。
4. 穿过真实系统边界，例如 Tauri bridge、sidecar、持久化或真实协议 stub。
5. 断言结果能被后续系统环节读取或消费。
6. 覆盖至少一个失败路径，且失败原因结构化。
7. 覆盖安全边界，尤其是 secret 不回显、不误用。
8. 失败时能定位到具体断裂点。

以下都不能单独算深度验收：

- 只跑 handler/unit/contract 测试。
- 只检查源码 marker、按钮存在、页面加载或翻译 key。
- 只由内部 audit 顺序执行多个测试，但没有真实页面动作链产生的事件和 artifact。

审计层可以汇总和校验证据，但不能替代外部自动化驱动真实页面的场景验收。

## System Settings LLM 口径

外部真实页面自动化（待实现） 必须验证：

- 真实 Tauri 桌面壳加载 System Settings。
- 真实 sidecar 返回 `settings.get`。
- Provider 默认值联动会填充 LM Studio 本地默认配置。
- 脚本启动 OpenAI-compatible `/v1/models` stub，并通过真实 `settings.checkLlmConnection` 读取模型列表。
- 页面选择检测到的模型，并通过 `settings.update` 保存。
- 重新 `settings.get` 后可读回 provider、base_url、model 和 masked API key 状态。
- 明文 API key 不出现在读回配置中。
- 未配置 base_url 的连接检查返回结构化 `BLOCKED_LOCAL_PROVIDER`。

只检查源码 marker、按钮存在或页面加载，不满足 System Settings LLM 深度验收。

## Quick Run Material Consumption 口径

外部真实页面自动化（待实现） 必须验证：

- 真实 Tauri 桌面壳加载 Quick Run。
- 真实 sidecar 同时读取持久化 LLM 配置、材料库来源、Evidence 列表和 Job Profile 列表。
- 运行前事件包含材料来源数量、选中材料来源、active Job Profile、`saved_eligible` Evidence Cards 和 masked LLM 摘要。
- Quick Run 启动真实本地 pipeline，且 `run.quick.start` 使用 complete Job Profile、selected eligible Evidence Cards 和 persisted LLM config。
- 本次 pipeline 使用独立 evidence 目录，匹配阶段只消费 staging 后的 selected eligible Evidence Cards。
- Quick Run record 保留 `material_source`、`raw_path`、`evidence_dir`、Matching Report、Resume、PDF、Scorecard、gap tasks、resume positioning 和 masked LLM 摘要。
- Matching Report 中的 `evidence_card_ids` 必须是本次 selected eligible Evidence Cards 的子集。
- Resume 输出包含对应 Evidence Card 的 `Evidence trace`，能从简历回溯到材料来源，并记录 fact-preserving traceability。
- 外部自动化必须证明 LLM required 路径被调用，不能静默 fallback 到非 LLM 路径。
- 明文 API key 和 policy secret storage 字段不得出现在 Quick Run record 中。

只检查 Quick Run 页面能看到材料来源，不满足材料消费深度验收。

## Agent Run Guided Batch 口径

外部真实页面自动化（待实现） 必须验证：

- 真实 Tauri 桌面壳加载 Agent Run。
- 真实 sidecar 读取 persisted LLM 摘要，且 run record 只保留 masked secret 状态。
- Agent Run 使用 active Job Profile、eligible Evidence Cards 和 saved Job Leads 启动 guided batch。
- run record 记录 preflight confirmation、effective policy limits、selected candidate ids 和 no-real-submit 确认。
- 真实 AgentLoop 事件至少覆盖 INIT、DISCOVER、SCORE、GENERATE、EVALUATE、GATE、REVIEW。
- Gate 结果写入 run record，Review queue 写入 `outputs/review_queue/<run_id>.json`。
- 人工 review 前不得出现 DELIVER 事件，delivery plan 必须记录 `submit_enabled=false` 与 `external_submission_attempted=false`。
- run log 必须持久化到 `outputs/agent_runs/<run_id>/run_log.json`，且页面/事件能回溯到该 run log。

只检查 Agent Run 页面能启动或只验证 LLM 摘要，不满足 guided batch 深度验收。

## Channel Session Setup 口径

外部真实页面自动化（待实现） 对 `channel_session_setup` 必须验证：

- 真实 Tauri 桌面壳加载 Submissions。
- 真实 sidecar 暴露 channel session API，且 API/UI/log 中都带 `channel`。
- 支持的通道以可扩展列表呈现，P0 至少包含 `liepin`，调用层不得写成 Liepin-only 合同。
- 缺失 channel 和不支持 channel 返回结构化错误。
- start session 只打开/记录人工登录边界，不输入、不保存 credentials。
- captcha/SMS 输入和绕过参数必须被拒绝，自动化不得写入 captcha/SMS。
- 仅 `login_modal_absent` 不能把会话标为 valid，必须返回 `session_unknown`。
- `login_required` 返回结构化 `login_required`。
- 只有 positive authenticated signal 才能持久化 `session_valid`。
- session artifact 记录 `session_path`、`checked_at`、`clear_available`、safe account identity 或 `account_identity_unknown`。
- account identity 只能保存非敏感或 masked 字段。
- adapter-specific 字段必须按 channel namespace 保存。
- clear 只清理选中的 channel session，后续读取不得把 cleared session 视为 valid。
- `session_check_log` 必须记录 channel、步骤、terminal status 和安全边界。

只检查 Submissions 页面加载或只显示投递记录，不满足 channel session setup 深度验收。

## Submission Check Mode 口径

外部真实页面自动化（待实现） 对 `submission_check_mode` 必须验证：

- 真实 Tauri 桌面壳加载 Submissions。
- 真实 sidecar 使用 `submission.checkMode.start` 创建 check-mode submission log。
- API 必须要求 channel、channel Job Lead、resume PDF、usable shared session 和 preflight confirmation。
- 缺失 session、unknown/cleared session、用户拒绝账号 identity 都必须在 open target 前结构化阻断。
- preflight 必须记录 selected channel、Job Lead、resume PDF、session metadata、no-real-submit、final confirm disabled。
- check-mode 必须记录 adapter capabilities，且 adapter-specific 字段按 channel namespace 保存。
- submission log 必须记录 original Job Lead、final verified target、resume version/PDF、session metadata、rate limit decision、login check、target verify、attachment status 和 submit skipped。
- `send_resume_path_check` 必须发生在 target verify 之后。
- `final_submit_attempted=false`、`external_submission_attempted=false`、`submit_enabled=false` 必须同时出现在返回值和 persisted log 中。
- Submission detail 必须能读取同一 log 的 steps、original/final target、JSON/YAML 路径和 terminal status。

只检查 Submissions 表格新增了一条记录，不满足 check-mode 深度验收。

## Feedback Iteration 口径

外部真实页面自动化（待实现） 对 `feedback_iteration_after_check_mode` 必须验证：

- 真实 Tauri 桌面壳加载 Submissions。
- 真实 sidecar 从上一轮 check-mode submission log 列出反馈项。
- 缺失 `source_run_id`、unsupported feedback source 和未选择 action 必须结构化阻断。
- iteration record 必须保存到 `outputs/feedback_iterations/<iteration_id>/iteration_record.json`。
- record 必须包含 immutable source snapshot，并保留上一轮 submission log / resume artifact。
- 用户选择的 action 必须写入 `selected_actions`，不能静默应用修改。
- 选择 regenerate resume 时必须创建新的 resume version id/path，且不得覆盖 previous resume version。
- new/updated claims 必须带 Evidence Card 链接。
- comparison summary 必须包含 previous/new version、changed sections、evidence ids、new/updated claims、removed claims 和 remaining gap tasks。
- record 必须给出 `next_check_mode_candidate`，且继续保持 `real_submit_disabled=true`。

只显示一条反馈提示或只复制 check-mode 状态，不满足 feedback iteration 深度验收。

## Closed Loop E2E Audit 口径

`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_closed_loop --level L1` 对 `closed_loop_e2e_audit` 必须验证：

- L1 runner 覆盖 `acceptance/journey_contract.yaml` 中所有 selected cases，且所有 case step 通过。
- Journey report 中所有 L1 mainline rules 均为 pass。
- `acceptance/journey_implementation_matrix.yaml` 中所有 `deep_verified` step 的 evidence path 或 glob 都能解析到真实文件。
- Quick Run native evidence 必须证明 selected Evidence -> fact-preserving matching -> traceable resume/PDF artifact。
- Agent Run native evidence 必须证明 guided batch、review queue、no delivery event、`submit_enabled=false` 和 persisted run log。
- Submissions native evidence 必须证明 check-mode submit skipped、feedback iteration 继承同一个 source run、新 resume version 进入下一轮 check-mode candidate，且继续 `real_submit_disabled=true`。
- 审计结果必须写入 `outputs/acceptance/<run_id>/closed-loop-audit.json` 和 `.md`，失败时列出具体断裂检查。

只把多个独立验收脚本顺序跑一遍，不检查 journey rule、evidence artifact 和跨阶段 traceability，不满足 closed-loop 深度验收。

## External L3 Submission Validation 口径

`bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3` 对 `external_l3_submission_validation` 必须验证：

- 默认不得触碰外部渠道；未设置 `PIPF_EXTERNAL_L3_AUTHORIZED=true` 时，必须只写入 live blocker 证据。
- 即使已有用户授权，未设置独立的 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true` 时，也必须阻断在最终提交前。
- 真实执行只允许在同时具备授权、最终确认、channel、Job URL、resume PDF、profile YAML、确认 job id 和确认 recruiter 时启动。
- P0 支持的外部渠道为 `liepin`；其他渠道必须记录 `unsupported_external_l3_channel`，不得隐式 fallback。
- L3 证据必须写入 `outputs/acceptance/<run_id>/external-l3-validation.json` 和 `.md`。
- 证据必须覆盖 `user_authorized_external_session`、`explicit_final_submit_gate`、`live_channel_result_or_blocker_recorded`、`post_submit_feedback_traceability` 和 `no_secret_or_captcha_bypass`。
- live blocker 是有效 L3 输出，但必须明确 `external_submission_attempted=false`、blocker reason、category 与 next action。
- submit 命令启动前产生 live blocker 时，`live_blocker` 必须直接包含 `failed_checks` 和 `diagnostics`，包括 missing gates、逐项 readiness gates 和真实输入审计摘要。
- L3 证据必须包含 `live_run_readiness`，逐项记录授权、最终确认、渠道、岗位 URL、URL 格式、resume PDF 路径与文件格式、profile YAML 路径与文件格式、确认 job id 和确认 recruiter 的 gate 状态；未全 pass 时 `submit_command_allowed=false`。
- `live_run_readiness` 表示 submit 命令启动前的 gate 结果；真实渠道命令执行后产生的 traceability blocker 不得回写成 pre-run gate 未通过，而应记录在 `submit_safety_decision.post_run_blocker_reason` 和 `live_blocker`。
- 即使所有 env 字符串都存在，真实 Job URL 不是 http/https、resume 不是存在的 `.pdf` 文件或 profile 不是存在的 `.yaml/.yml` 文件，也必须在启动 submit 命令前记录 live blocker。
- L3 证据必须包含 `live_input_artifacts`：记录 Job URL 的 scheme/host、resume/profile 的文件名、扩展名、大小和 SHA256；不得持久化 Job URL 原值、确认值或文件原始内容。
- L3 证据必须包含 `rate_limit_policy`：记录 max-per-batch、cooldown seconds、daily limit 和状态文件路径；频控被关闭时必须在 submit 命令启动前记录 live blocker。
- L3 证据必须包含 `forbidden_input_audit`：runner 只记录密码、验证码、短信码和原始密钥类 forbidden env 是否出现，不持久化原值；任一 forbidden input 出现时必须阻断在 submit 命令启动前。
- 如果真实渠道命令被执行，`external-l3-validation.json` 只能持久化脱敏后的 command 和 stdout/stderr 尾部；Job URL、resume/profile 路径、确认 job id 和确认 recruiter 必须以 `<redacted>` 形式保存。
- L3 证据必须包含 `submit_safety_decision`，明确最终提交命令是 `blocked_before_command`、`allowed_pending_execution` 还是 `allowed_and_executed`，并证明显式授权、独立最终确认和真实输入齐备才允许 submit。
- blocker 或真实渠道结果必须包含 `operator_handoff`：列出 required env 是否存在、最终提交前 checklist、禁止输入项和不含真实值的命令模板。
- `operator_handoff` 必须包含结构化 `authorization_packet`：记录必需确认声明、必需证据、中止条件、脱敏策略和禁止输入项；不得持久化 Job URL、文件路径、确认 job id 或 recruiter 原值。
- 真实渠道命令返回成功也不等于 L3 成功；必须解析并确认 `submission_log.yaml` 与同目录 `submission_log.json` 均存在，且 submission log 必须写回 `external_l3_validation_run_id`、`external_l3_validation_path` 和匹配本次 validation 的 `input_artifacts`，同时把原始 Job URL、resume/profile 路径字段写成 `<redacted>`，共同写入 `submission_traceability.linked_to_validation=true`。
- 如果 submission log 存在但没有反向指向本次 L3 validation record，必须记录为 `submission_log_not_linked` blocker，不得把单向日志路径解析视为真实验收通过。
- 如果 submission log JSON 可解析，`submission_traceability` 必须写入 `submission_log_summary`，包含 status、error、mode 和 last step；post-command live blocker diagnostics 也必须携带该摘要，让 rate limit、login required、target verify 等业务 blocker 可直接诊断。
- `submission_traceability` 必须记录逐项 `checks` 与 `failed_checks`，区分缺少 log hint、YAML/JSON 不存在、JSON 不可解析、run id/path 不匹配和输入产物指纹不匹配。
- 真实渠道命令执行后产生 live blocker 时，`live_blocker` 必须直接包含 `failed_checks` 和 `diagnostics`，包括 returncode、submission log 路径和逐项 traceability checks，避免用户为理解 blocker 再反查深层字段。
- 无论真实渠道成功还是记录 live blocker，L3 证据都必须包含 `post_submit_feedback_traceability`：成功时以 submission log 作为反馈来源，blocker 时以 `external-l3-validation.json` 作为反馈来源，并明确下一步反馈/阻断处理路径。
- 真实渠道命令返回非零时不得伪装成功；必须保留 stdout/stderr tail 和 log hint，作为 exact live blocker。
- 真实渠道命令超时时也不得让 validation 失败在写 evidence 之前；必须记录 `external_channel_command_timed_out` live blocker、timeout 秒数、脱敏 stdout/stderr tail 和后续处理路径。
- 真实渠道命令启动错误也不得让 validation 失败在写 evidence 之前；必须记录 `external_channel_command_launch_failed` live blocker，并保存脱敏后的错误类型/信息。
- runner 不接受 credentials、captcha 或 SMS 输入，也不得保存 secret；如果用户误传相关 env，必须记录 `forbidden_external_l3_sensitive_inputs` blocker，且只保留出现状态不保留值。

只把 L3 标为 `not_started`，或在缺少授权/最终确认时尝试外部提交，都不满足 External L3 验收。
