# Project Ledger

Last updated: 2026-05-23

## Current Acceptance Policy

- Scenario acceptance for GUI behavior must be driven by external automation against the real page, real browser boundary, or real Tauri desktop shell.
- Production pages must not contain acceptance-only environment branches, self-starting flows, page event logging hooks, or verifier controllers.
- Repository scripts must not expose embedded GUI acceptance entrypoints.
- Audit code may aggregate real artifacts, but it must not substitute for real-page scenario automation.

## Current Mainline

- System Settings: LLM provider defaults, model discovery, save/reload, masked secret behavior, and blocked local-provider failure path are covered by scenario and contract tests.
- Resumes and Evidence: material library inputs feed the evidence-first workflow and Evidence Card review contracts.
- Jobs: pasted JD text can create reviewed job targets for downstream matching and runs.
- Quick Run: selected eligible Evidence Cards and complete Job Profiles produce matching, resume, PDF, scorecard, and gap artifacts with traceability.
- Agent Run: guided batch stops at review state, writes review queue artifacts, and keeps delivery disabled before approval.
- Submissions: channel session setup, check mode, submit-skipped logging, and feedback iteration are represented by sidecar contracts and real artifacts.
- Closed-loop audit reads durable artifacts from `outputs/quick_runs`, `outputs/agent_runs`, `outputs/submissions`, and `outputs/feedback_iterations`.
- External L3: `run-acceptance --level L3` now writes a guarded live blocker or real-channel result record; missing explicit authorization or missing separate final-submit confirmation never attempts external submission.
- External L3 handoff: validation records include an `operator_handoff` package with required env presence, pre-run checklist, forbidden inputs, and a redacted command template for a future authorized live run.
- External L3 authorization packet: `operator_handoff.authorization_packet` records required confirmation statements, evidence, abort conditions, redaction policy, and prohibited inputs without persisting raw confirmation values.
- External L3 pre-submit blocker diagnostics: pre-submit live blockers directly include missing readiness gates, full readiness gate results, and live input audit summaries；Markdown 报告同步展示 submit 是否允许启动、missing gates 和输入审计摘要，journey validation 会拒绝 Markdown/JSON blocker 诊断漂移。
- External L3 readiness: validation records include `live_run_readiness` gates and keep `submit_command_allowed=false` until every authorization gate and real-input validation gate passes, including URL format and local resume/profile file type checks.
- External L3 readiness semantics: post-command traceability blockers do not rewrite pre-run readiness; they are recorded in `submit_safety_decision.post_run_blocker_reason` and `live_blocker`.
- External L3 input audit: validation records include `live_input_artifacts`，用 Job URL scheme/host、文件扩展名、大小与 resume/profile SHA256 指纹绑定输入产物，同时不持久化原始 URL、确认值、文件内容或 resume/profile 文件名；人读 Markdown 报告也展示 `basename_persisted=false` 与 `raw_content_persisted=false`。
- External L3 rate limiting: validation records include `rate_limit_policy` and pass explicit rate-limit arguments to live submit commands; disabled rate limits are blocked before any external command starts.
- External L3 session readiness: validation records include `session_readiness`、`manual_session_ready_confirmed` gate 和 `manual_session_storage_ready` gate；共享渠道 session 未经人工登录或刷新确认可用，或 session 根目录不存在、Liepin 持久化会话目录不存在、目录内没有非空可识别浏览器状态标记时，真实 submit 命令不会启动，且自动化仍不得接收或保存密码、验证码或短信码。
- External L3 forbidden input audit: validation records include `forbidden_input_audit`；密码、验证码、短信码和原始密钥类 env 值永不持久化，且一旦出现就阻断在任何真实 submit 命令启动前。
- External L3 target confirmation audit: validation records include `target_confirmation_audit`；只记录 URL 岗位 ID 是否可解析、确认岗位 ID 是否提供和二者是否一致、确认 recruiter 是否提供，以及 recruiter 页面匹配必须由 `target_verify` 证明的边界；不持久化原始 ID 或 recruiter 原值，且岗位 ID 不一致时阻断在 submit 命令启动前。
- External L3 command/output audit: validation records only persist redacted live submission command and redacted stdout/stderr tails；原始 Job URL、resume/profile 路径、确认 job id 和 recruiter 不写入 command 或 output tail 证据。
- External L3 submit safety: validation records include `submit_safety_decision`；真实渠道命令是否阻断、允许待执行或已执行，必须在信任结果前成为显式可审计状态；`blocking_reason`/`post_run_blocker_reason` 必须与 `live_blocker.reason` 保持一致。
- External L3 authorization acknowledgement checklist: `operator_handoff.authorization_packet.acknowledgement_checklist` 把外部渠道授权、最终提交确认、人工 session、真实输入产物、目标确认和禁止输入映射到 env、gate、证据来源、当前状态和原值不落盘边界；`pending_acknowledgement_count` 必须在模板发布、Go/No-Go 放行和授权模板执行前清零，授权确认不再只是声明文本，未满足项不能被当作模板发布证据。
- External L3 handoff runtime policy: `operator_handoff.runtime_options` 记录当前 channel、session/output 目录、timeout 和 headless 配置；`operator_handoff.preflight_command_template` 保持 `AUTHORIZED=false` 与 `FINAL_SUBMIT_CONFIRMED=false`，用于无授权本地预检；`operator_handoff.command_template` 使用 shell-safe 的 live 输入占位符，并写入当前运行配置与有效频控参数；Markdown 报告分开展示本地预检模板和授权真实运行模板，避免操作者覆盖 env 后交接模板回退成旧默认值或被 shell 误解析。
- External L3 preflight expectation: `operator_handoff.preflight_result_expectation` 记录本地预检的正常结果应为 `live_blocker_recorded` / `explicit_user_authorization_required`，且 `external_submission_attempted=false`、`submit_command_allowed=false`、`p0_017_complete=false`，避免操作者把预检 blocker 误判为真实失败或完成。
- External L3 preflight review checklist: `operator_handoff.preflight_review_checklist` 记录授权模板执行前必须复核的结构化清单，覆盖 validation 状态、blocker reason、外部提交未启动、submit 命令未允许、P0-017 未完成、输入审计脱敏、session、频控、证据清单、runbook 指纹和反馈追溯；Markdown 报告同步展示该清单，避免操作者只凭散落字段判断可授权执行。
- External L3 preflight review result: `operator_handoff.preflight_review_result` 根据本次 validation 实际字段逐项写出 observed 值和 pass/fail；无授权本地预检复核项全部通过时仍会把缺失的真实运行输入、session 或目标确认 gate 记录为 `authorization_decision_blockers`，并保持 `ready_for_authorization_decision=false` 与 `authorized_template_execution_allowed=false`，避免把预检通过误读成可直接请求授权或执行授权模板。
- External L3 authorization readiness action plan: `operator_handoff.authorization_readiness_action_plan` 把 `authorization_decision_blockers` 转成待补行动，覆盖人工 session、Job URL、resume PDF、profile YAML 和目标确认；每个行动都记录阻断 gate、必需证据、`blocks_authorization_decision=true` 与 `raw_live_inputs_persisted=false`，让操作者按行动补齐而不是反查 gate 名称。
- External L3 authorization intake checklist: `operator_handoff.authorization_intake_checklist` 把每个真实运行输入或确认映射到具体 env、占位符、gate、当前状态和原值不落盘边界；模板发布前必须清零，避免操作者在行动计划、env 表和命令模板之间人工拼接。
- External L3 authorized template release decision: `operator_handoff.authorized_template_release_decision` 把授权真实运行模板的展示和发布分开；待补行动未清零、授权输入接收清单未清零、授权签核待补数未清零、预检复核未允许进入授权决策、authorization packet 未就绪、显式授权或最终提交确认缺失时，保持 `template_released_to_operator=false` 与 `copy_execution_allowed=false`，并列出发布阻断项和发布前必需条件。
- External L3 live run Go/No-Go decision: `operator_handoff.live_run_go_no_go_decision` 汇总 readiness、submit safety、授权行动计划、授权输入清单、授权签核计数、模板发布决策和 P0-017 完成门禁；授权签核待补数未清零、授权模板未发布或 submit 命令未允许前保持 `go_for_live_run=false`、`submit_command_may_start=false` 与 `copy_authorized_template_allowed=false`，并把每个 no-go blocker 映射到 resolution route、证据来源和必需证据，让操作者不再跨段拼接能否启动真实运行或下一步怎么处理。
- External L3 live run execution sequence: `operator_handoff.live_run_execution_sequence` 把本地预检、预检复核、No-Go 路线处理、授权行动、授权输入、授权签核、模板发布、Go/No-Go、授权模板执行和 P0-017 完成验证排成结构化门禁；当前无授权交接包会把 `next_executable_step` 固定在 `resolve_no_go_routes`，防止操作者跳过前置步骤直接复制授权模板。
- External L3 live run runbook: `operator_handoff.runbook.path` 指向 `docs/runbooks/external-l3-live-run.md`，并记录存在状态、SHA256 指纹和必需章节完整性；该中文 runbook 固化 P0-017 的授权边界、人工 session preflight、live 输入替换、blocker triage 和运行后证据复核，且声明不持久化原始 live 输入。
- External L3 handoff command review: `operator_handoff.command_template_review` 记录 `copy_paste_ready=false`、占位符替换、显式授权、独立最终提交确认、人工会话可用、session 存储就绪确认、执行顺序、预检模板不启用授权/最终提交，以及授权模板执行前必须复核预检证据；Markdown 报告同步展示命令模板复核，避免带 `AUTHORIZED=true`、`FINAL_SUBMIT_CONFIRMED=true` 与 `SESSION_READY_CONFIRMED=true` 的模板在 session 根目录不存在或 Liepin 持久化会话目录没有非空可识别状态标记时被盲贴执行。
- External L3 evidence manifest: validation records include `evidence_manifest`，统一列出 validation JSON/Markdown、关键嵌入段、中文真实运行 runbook、live run Go/No-Go decision、live run execution sequence、P0-017 completion gate、live blocker 或 submission log、feedback source 的必需性、存在状态和脱敏边界；live run Go/No-Go 清单项必须证明 no-go 状态、Go 前条件和 resolution routes 都存在，执行顺序清单项必须证明顺序门禁、下一可执行步骤和原值不落盘边界都存在；runbook 清单项必须与 `operator_handoff.runbook` 的路径、指纹和章节完整性一致；Markdown 报告必须逐项同步展示证据清单，journey contract 会拒绝 Markdown 与 JSON 清单不一致的报告，避免人工复核时跨段拼接证据。
- External L3 outcome summary: validation records include `outcome_summary`，把 acceptance `pass` 与真实业务结果分开，区分 pre-submit blocker、post-command blocker 和 `external_validated`；顶层 acceptance step message 也区分 submit 命令未启动与命令后 blocker；真实外部验证成功前 `p0_017_complete=false`；blocker next action 必须与 `live_blocker.next_action` 一致，Markdown 结果分级必须与 JSON 结果分级一致。
- External L3 P0-017 completion gate: validation records include `p0_017_completion_gate`，把路线图完成口径结构化为 required evidence；显式授权、最终提交确认、人工 session、真实输入、外部提交、submission log 反向链接、submission log success、反馈追溯和 external_validated outcome 未全部满足前，`acceptance_pass_is_completion=false`。
- External L3 traceability: successful external commands must link `external-l3-validation.json` to persisted `submission_log.yaml/json`, and submission logs must write back `external_l3_validation_run_id/path`; missing or one-way-only links are recorded as `submission_log_not_linked`; returncode 0 with a non-success submission log is recorded as `external_channel_submission_not_success`, not `external_validated`; nonzero external commands with parseable known `submission_log_summary.error`, including `batch_cooldown`/`daily_limit_exceeded`, are promoted to exact `external_channel_*` business blockers before falling back to `external_channel_command_returned_nonzero`, and journey report validation fails if that precise mapping regresses.
- External L3 submission log path guard: validation only reads submission logs under the allowed submission output root；越界路径会记录 `outside_allowed_submission_root`，Markdown 只展示允许根目录、路径边界结论和拒绝原因，不泄露被拒绝的原始路径。
- External L3 submission log audit: submission log 会写入自身 `input_artifacts`；L3 成功要求这些指纹与 validation record 匹配，且 External L3 关联日志必须声明 `live_inputs_redacted=true` 与 `input_artifacts.job_url.raw_value_persisted=false`，原始 Job URL、resume/profile 路径字段、resume/profile 文件名、steps.detail 原文、截图路径和 HTML snapshot 引用都必须脱敏或不落盘；validation 会递归拒绝截图/HTML snapshot 字段、嵌套诊断字段或路径片段。
- External L3 trace diagnostics: `submission_traceability` 写入逐项检查结果和 `failed_checks`，Markdown 报告同步展示同一 failed checks 与 checks 表，journey validation 会拒绝 Markdown/JSON 检查表漂移，让 `submission_log_not_linked` 指向具体缺失或不匹配的证据。
- External L3 submission log summary: parsed submission logs promote status, error, mode, and a redacted last step into validation、Markdown 和 post-command blocker diagnostics so business blockers are actionable；journey validation rejects missing mode or Markdown/JSON summary drift；unsafe target_verify observed values or HTML snapshot details are replaced with a redacted placeholder before entering validation summaries.
- External L3 submission log required steps: 成功 submission log 必须包含并通过 `rate_limit`、`login_check`、`target_verify`、`submit_safety`、`chat_send_resume` 和 `submit` 步骤；否则 validation 记录 traceability blocker，而不是信任 returncode 0。
- External L3 blocker diagnostics: post-command live blockers directly include failed traceability checks, returncode, and related submission log paths so the blocker record is actionable without deep JSON lookup.
- External L3 timeout handling: timed-out live commands are recorded as `external_channel_command_timed_out` blockers with timeout seconds, redacted output tails, feedback traceability, and matching Markdown timeout diagnostics instead of failing before evidence is written.
- External L3 command launch errors: browser/driver/permission/runtime launch failures are recorded as `external_channel_command_launch_failed` blockers with redacted error type/message in JSON and Markdown, without leaking Job URL or local file paths.
- External L3 feedback trace: validation records now write `post_submit_feedback_traceability`; 真实投递结果或 live blocker 都必须成为下一步反馈动作的可追溯来源产物；blocker source reason 必须与 `live_blocker.reason` 一致，Markdown 反馈追溯必须与 JSON 的 source status/reason/next action 一致。

## Verification Anchors

- `constitution.md`
- `docs/acceptance-depth.md`
- `docs/execution-roadmap.md`
- `acceptance/journey_implementation_matrix.yaml`
- `tools/acceptance/acceptance_runner.py`
- `tests/acceptance/test_acceptance_runner.py`
- `tests/unit/gui/test_native_verifier_contract.py`

## Last Verified Commands

- `python3 -m pytest tests/ -q`
- `pnpm --dir ui build`
- `cargo check --manifest-path ui/src-tauri/Cargo.toml`
- `python3 tools/check_execution_roadmap.py --root .`
