# External L3 真实运行 Runbook

本文是 P0-017 `authorized_external_l3_live_run` 的人工执行真源。它只描述如何准备、复核和审计一次真实渠道 L3 验证，不保存 Job URL、确认值、简历路径、profile 路径、密码、验证码或短信码。

## 适用边界

- 仅适用于 `acceptance_external_l3` 的 Liepin 真实渠道验证。
- 真实 submit 命令只能在用户显式授权、独立最终提交确认、人工 session 可用确认和 session 存储就绪后启动。
- 自动化不得输入、保存或绕过密码、验证码、短信码、账号恢复流程或原始密钥。
- 未通过任一 preflight gate 时，必须保留 live blocker 证据，不得触碰真实渠道。

## 前置产物

- 已审核的 resume PDF。
- 已审核的 profile YAML。
- 真实 Job URL。
- 人工确认的 job id。
- 人工确认的 recruiter。
- 已人工登录或刷新可用的共享渠道 session 根目录。
- Liepin 持久化会话目录下至少一个非空、可识别的浏览器状态标记，例如 `Local State`、`Default/Preferences`、`Default/Network/Cookies` 或 `storage-state.json`。

## 运行前检查

1. 复核 `outputs/acceptance/acceptance_external_l3/external-l3-validation.md` 中的 `授权交接包`。
2. 确认命令模板中的 `<https-url>`、`<resume.pdf>`、`<profile.yaml>`、`<job-id>` 和 `<recruiter>` 已替换为本次真实输入。
3. 先运行 `本地预检命令模板`，确认输入审计、session 存储、频控、runbook 指纹和 evidence manifest 均能写出；该模板必须保持 `PIPF_EXTERNAL_L3_AUTHORIZED=false` 与 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=false`，且复核结果必须显示授权模板执行前需要先复核预检证据。
4. 确认 `本地预检预期结果` 显示预检正常结果是 `live_blocker_recorded` / `explicit_user_authorization_required`，并且 `external_submission_attempted=false`、`submit_command_allowed=false`、`p0_017_complete=false`。
5. 确认 `本地预检复核清单` 中所有 required 项均存在，重点复核 validation 状态、blocker reason、外部提交未启动、submit 命令未允许、P0-017 未完成、输入审计脱敏、session、频控、证据清单、runbook 指纹和反馈追溯。
6. 确认 `本地预检复核结果` 显示所有 required 项 `status=pass`；如果 `authorization_decision_blockers` 非空或 `ready_for_authorization_decision=false`，先补齐真实输入、人工 session 和目标确认，不得请求授权或复制授权模板。
7. 确认 `授权签核清单` 中外部渠道授权、最终提交确认、人工 session、真实输入产物、目标确认和禁止输入均映射到 env、gate、证据来源和当前状态，并确认 `pending_acknowledgement_count=0`；任一签核项 pending 时不得发布授权模板、不得通过 Go/No-Go、不得执行授权模板。
8. 按 `授权就绪行动计划` 逐项补齐人工 session、Job URL、resume PDF、profile YAML 和目标确认；补齐过程不得把 Job URL、文件路径、确认 job id 或 recruiter 原值写回仓库、文档、测试或验收报告。
9. 确认 `授权输入接收清单` 中每个待补输入/确认都已按对应 env、占位符和 gate 补齐；如果 `pending_item_count` 非 0，不能复制授权模板。
10. 确认 `授权模板发布决策` 中 `template_released_to_operator=true` 且 `copy_execution_allowed=true`；如果模板已展示但发布决策仍为 false，说明模板仅供复核，不能复制执行。
11. 确认 `授权模板发布决策` 的发布阻断项为空，且发布前必需条件均已满足。
12. 确认 `真实运行 Go/No-Go 决策` 中 `go_for_live_run=true`、`submit_command_may_start=true` 且 `copy_authorized_template_allowed=true`；如果仍为 no-go，必须按 `blocking_evidence`、`resolution_routes` 和 `required_before_go` 处理，不得启动真实运行。
13. 确认 `真实运行执行顺序门禁` 中 `authorized_template_execution_allowed=true`；如果 `next_executable_step` 仍指向前置步骤，必须先完成该步骤，不得跳到授权模板。
14. 确认 `PIPF_EXTERNAL_L3_AUTHORIZED=true` 只在用户明确授权后保留。
15. 确认 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true` 只在用户独立确认允许最终提交路径后保留。
16. 确认 `PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true` 只在人工登录或刷新确认 session 可用后保留。
17. 确认频控参数仍为正数，且符合本次真实渠道风险边界。
18. 确认没有设置 `PIPF_EXTERNAL_L3_PASSWORD`、`PIPF_EXTERNAL_L3_CAPTCHA_CODE`、`PIPF_EXTERNAL_L3_SMS_CODE` 或 `PIPF_EXTERNAL_L3_RAW_API_KEY`。

## 执行命令

从最新 `external-l3-validation.md` 先复制 `本地预检命令模板` 并替换所有 live 输入占位符；预检仍应记录 blocker，且不得触碰真实渠道。只有预检证据完整、命令模板复核显示 `preflight_must_run_before_authorized_template=true`、预检结果符合 `本地预检预期结果`、`本地预检复核清单` 全部 required 项已人工复核、`本地预检复核结果` 全部 required 项已通过、`授权签核清单` 已证明每项人工确认都有 env/gate/source 映射且不持久化原值且 `pending_acknowledgement_count=0`、`授权就绪行动计划` 的待补行动清零且 `authorization_decision_blockers` 为空、`授权输入接收清单` 的待补输入/确认清零、`授权模板发布决策` 明确模板已发布并允许复制执行、`真实运行 Go/No-Go 决策` 明确 `go_for_live_run=true` 且没有待处理 no-go 路线、`真实运行执行顺序门禁` 明确授权模板可执行、用户显式授权并独立确认最终提交后，才复制 `授权真实运行命令模板`。模板中的 live 输入不应写回仓库、文档、测试或验收报告。

```bash
bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3
```

如果命令模板和本文冲突，以最新代码生成的 `operator_handoff.command_template` 为准，但必须先修正文档或代码中的漂移，再把真实运行结果作为 P0-017 证据。

## Blocker 处理

- `explicit_user_authorization_required`：停止运行，取得明确授权后重新生成交接包。
- `final_submit_confirmation_required`：停止运行，取得独立最终提交确认后重新生成交接包。
- `manual_session_storage_not_ready`：回到渠道 session 设置，人工登录或刷新 session，并确认非空状态标记存在。
- `forbidden_external_l3_sensitive_inputs`：移除禁止 env，确认不会输入密码、验证码、短信码或原始密钥。
- `target_confirmation_mismatch`：重新人工复核 Job URL、job id 和 recruiter，不得用猜测值继续。
- `external_channel_*`：优先阅读 `submission_traceability.submission_log_summary`、failed checks 和必需步骤摘要，按真实渠道业务 blocker 处理。
- `submission_log_not_linked`：不得信任 returncode，先修复 validation record 与 submission log 的双向追溯。

## 运行后审计

1. 打开 `outputs/acceptance/acceptance_external_l3/external-l3-validation.json`，确认 `outcome_summary.p0_017_complete` 是否为 `true`。
2. 打开对应 Markdown 报告，确认结果分级、live blocker、submission traceability 和 post-submit feedback trace 与 JSON 一致。
3. 如果 `external_l3_success=true`，确认 `outputs/submissions/liepin/*/submission_log.yaml` 或 `.json` 存在，且反向链接本次 validation run id/path。
4. 确认 submission log 的 `live_inputs_redacted=true`，且 Job URL、resume/profile 路径、文件名、页面观测值、截图和 HTML snapshot 没有落盘。
5. 复核 `P0-017 完成门禁`；只有所有 required evidence 都为 `satisfied` 且 `acceptance_pass_is_completion=true` 时，才可把本次 acceptance pass 解读为 P0-017 完成。
6. 如果只记录 blocker，把 blocker reason、next action 和 feedback trace 作为下一轮处理入口，不得把 acceptance pass 解读为 P0-017 完成。

## 完成口径

P0-017 只有在以下证据同时成立时才可从 `next` 更新为完成状态：

- `external-l3-validation.json` 的 `status=external_validated`。
- `p0_017_completion_gate.p0_017_complete=true` 且 `completion_blockers` 为空。
- `outcome_summary.external_l3_success=true` 且 `outcome_summary.p0_017_complete=true`。
- submission log 存在、位于允许输出根目录下，并反向链接本次 validation run id/path。
- submission log 关键步骤 `rate_limit`、`login_check`、`target_verify`、`submit_safety`、`chat_send_resume` 和 `submit` 均记录且通过。
- validation record、Markdown 和 submission log 均不持久化原始 live 输入或浏览器原始截图/HTML。
