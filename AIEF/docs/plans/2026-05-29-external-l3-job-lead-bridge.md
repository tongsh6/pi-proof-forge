# External L3 Job Lead Bridge Plan

## 背景

P0-017 `authorized_external_l3_live_run` 需要真实 Job URL、确认 job id、确认 recruiter、resume PDF、profile YAML 和 session readiness。当前这些信息已经部分存在于 `job_leads/*.yaml` 与历史 check-mode `submission_log.yaml/json` 中，但 External L3 runner 只从 `PIPF_EXTERNAL_L3_*` 环境变量读取 live 输入。

这导致 validated Job Lead 到 External L3 之间存在手工拼接断点，不符合项目“DISCOVER -> REVIEW -> DELIVER”的自动化闭环方向。

## 目标

新增一个最小桥接能力：

`validated job_lead + validation_log -> External L3 confirmation packet + shell-safe env template`

让系统从已保存的岗位线索和 check-mode 证据中自动生成候选确认包，用户只需要审批候选、确认目标身份、显式授权和最终提交边界。

## 非目标

- 不自动设置 `PIPF_EXTERNAL_L3_AUTHORIZED=true`。
- 不自动设置 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true`。
- 不触发真实外部提交。
- 不绕过 target/recruiter 人工确认。
- 不把 Job URL、recruiter、resume/profile 本地路径写入 External L3 validation record。
- 不改 GUI 页面；GUI 审批接入留到后续。

## 数据来源

- `job_leads/*.yaml`
  - 支持现有 `items:` 列表格式。
  - 支持单文件单 lead 格式。
- `validation_log`
  - 读取 check-mode `submission_log.yaml/json`。
  - 优先使用 `target_verify` step 中的 `url_job_id` / `dom_jobid` / `params_jobid` / `recruiter`。
- 本地运行输入
  - resume PDF 路径。
  - profile YAML 路径。
  - External L3 session root。

## 最小实现

新增模块：

```bash
python3 -m tools.acceptance.external_l3_job_lead_bridge \
  --lead-source job_leads/jl-validated-20260513.yaml \
  --lead-index 1 \
  --resume-pdf uploaded_resumes/rv_49ab4b78.pdf \
  --profile profiles/candidate_profile.yaml \
  --session-dir outputs/submissions
```

输出：

- redacted confirmation packet
  - 候选公司/岗位。
  - Job URL scheme/host/job id 指纹，不输出原始 URL。
  - recruiter 是否存在，不输出 recruiter 原值。
  - resume/profile 文件存在、扩展名、大小、SHA256，不输出 basename 和内容。
  - 缺口列表。
- shell-safe env template
  - 默认保留 `PIPF_EXTERNAL_L3_AUTHORIZED=false`。
  - 默认保留 `PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=false`。
  - 包含从 lead/log 提取的 live 输入赋值，供操作者确认后执行。

## 验收

- 能从 validated Job Lead 列表项加载候选。
- 能从 check-mode `target_verify` 提取 URL job id、DOM/params job id 和 recruiter。
- 缺少 `validation_log`、target verify、recruiter 或 job id 时输出结构化缺口。
- redacted confirmation packet 不持久化 Job URL 原值、recruiter 原值、resume/profile basename 或文件内容。
- env template 使用 shell-safe quoting，并默认不授权、不最终提交。
- env template 必须通过真实 shell 子进程验证环境变量可见性；默认人工会话确认也为 false，不能从 session 文件存在自动推导人工确认。
- lead 的岗位 URL 与 validation log 的 URL job id 不一致时输出 `target_job_id_matches` 缺口。
- 生成的 env template 可直接供 `run-acceptance --level L3` 使用，但仍由 External L3 runner 决定是否阻断。

## 后续

- 将 confirmation packet 接到 Agent Run / Jobs 页面审批。
- 将 check-mode refresh 接到候选确认包生成前。
- 在路线图中把 P0-017 的“用户提供 live 输入”细化为“系统生成候选确认包，用户审批授权”。
