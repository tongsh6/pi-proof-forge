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
4. 确认 `PIPF_EXTERNAL_L3_AUTHORIZED=true` 只在用户明确授权后保留。
5. 确认 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true` 只在用户独立确认允许最终提交路径后保留。
6. 确认 `PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=true` 只在人工登录或刷新确认 session 可用后保留。
7. 确认频控参数仍为正数，且符合本次真实渠道风险边界。
8. 确认没有设置 `PIPF_EXTERNAL_L3_PASSWORD`、`PIPF_EXTERNAL_L3_CAPTCHA_CODE`、`PIPF_EXTERNAL_L3_SMS_CODE` 或 `PIPF_EXTERNAL_L3_RAW_API_KEY`。

## 执行命令

从最新 `external-l3-validation.md` 先复制 `本地预检命令模板` 并替换所有 live 输入占位符；预检仍应记录 blocker，且不得触碰真实渠道。只有预检证据完整、命令模板复核显示 `preflight_must_run_before_authorized_template=true`、用户显式授权并独立确认最终提交后，才复制 `授权真实运行命令模板`。模板中的 live 输入不应写回仓库、文档、测试或验收报告。

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
5. 如果只记录 blocker，把 blocker reason、next action 和 feedback trace 作为下一轮处理入口，不得把 acceptance pass 解读为 P0-017 完成。

## 完成口径

P0-017 只有在以下证据同时成立时才可从 `next` 更新为完成状态：

- `external-l3-validation.json` 的 `status=external_validated`。
- `outcome_summary.external_l3_success=true` 且 `outcome_summary.p0_017_complete=true`。
- submission log 存在、位于允许输出根目录下，并反向链接本次 validation run id/path。
- submission log 关键步骤 `rate_limit`、`login_check`、`target_verify`、`submit_safety`、`chat_send_resume` 和 `submit` 均记录且通过。
- validation record、Markdown 和 submission log 均不持久化原始 live 输入或浏览器原始截图/HTML。
