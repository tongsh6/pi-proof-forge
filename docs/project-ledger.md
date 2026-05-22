# Project Ledger

Last updated: 2026-05-22

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
- External L3 pre-submit blocker diagnostics: pre-submit live blockers directly include missing readiness gates, full readiness gate results, and live input audit summaries.
- External L3 readiness: validation records include `live_run_readiness` gates and keep `submit_command_allowed=false` until every authorization gate and real-input validation gate passes, including URL format and local resume/profile file type checks.
- External L3 readiness semantics: post-command traceability blockers do not rewrite pre-run readiness; they are recorded in `submit_safety_decision.post_run_blocker_reason` and `live_blocker`.
- External L3 input audit: validation records include `live_input_artifacts`，用 Job URL scheme/host 与 resume/profile SHA256 指纹绑定输入产物，同时不持久化原始 URL、确认值或文件内容。
- External L3 rate limiting: validation records include `rate_limit_policy` and pass explicit rate-limit arguments to live submit commands; disabled rate limits are blocked before any external command starts.
- External L3 command/output audit: validation records only persist redacted live submission command and redacted stdout/stderr tails；原始 Job URL、resume/profile 路径、确认 job id 和 recruiter 不写入 command 或 output tail 证据。
- External L3 submit safety: validation records include `submit_safety_decision`；真实渠道命令是否阻断、允许待执行或已执行，必须在信任结果前成为显式可审计状态。
- External L3 traceability: successful external commands must link `external-l3-validation.json` to persisted `submission_log.yaml/json`, and submission logs must write back `external_l3_validation_run_id/path`; missing or one-way-only links are recorded as `submission_log_not_linked`.
- External L3 submission log audit: submission log 会写入自身 `input_artifacts`；L3 成功要求这些指纹与 validation record 匹配，且 External L3 关联日志中的原始 Job URL、resume/profile 路径字段必须写成 `<redacted>`。
- External L3 trace diagnostics: `submission_traceability` 写入逐项检查结果和 `failed_checks`，让 `submission_log_not_linked` 指向具体缺失或不匹配的证据。
- External L3 submission log summary: parsed submission logs promote status, error, mode, and last step into validation and post-command blocker diagnostics so business blockers are actionable.
- External L3 blocker diagnostics: post-command live blockers directly include failed traceability checks, returncode, and related submission log paths so the blocker record is actionable without deep JSON lookup.
- External L3 timeout handling: timed-out live commands are recorded as `external_channel_command_timed_out` blockers with timeout seconds, redacted output tails, and feedback traceability instead of failing before evidence is written.
- External L3 command launch errors: browser/driver/permission launch failures are recorded as `external_channel_command_launch_failed` blockers with redacted error evidence instead of failing before validation evidence is written.
- External L3 feedback trace: validation records now write `post_submit_feedback_traceability`; 真实投递结果或 live blocker 都必须成为下一步反馈动作的可追溯来源产物。

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
