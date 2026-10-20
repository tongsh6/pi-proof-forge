# PiProofForge Sidecar RPC Contract

2026-10-20 推断确认接续：`evidence.confirmInference` 接受成功返回的新 `card_sha256` 是同一卡下一字段确认的输入；保存一字段时保留另一字段已有 provenance，仍设为待审核、不可自动入池。客户端每次成功更新卡指纹、剩余候选及计数；部分失败不重放已成功项，确认后不隐式再次调用 `inferFields`。

2026-10-20 用户修订职责取向：本人经历项目在缺少分工记录且无反向信息时，推断优先主导/负责人视角；仍按 L3 候选记录来源与确认状态。已采纳 L3 职责在角色行、行动和 trace 中保持原义，不机械降为参与；明确参与、协助及否定限定不被提升。R1.4 对有出处且已由用户确认的 L3 不因等级自动拒绝，未确认归因仍待核对。候选 value 只保存业务文本，等级及默认归因说明单独呈现。

2026-10-18 四层质量报告（Phase A）：Scorecard JSON 增加 `quality_report`（`schema_version:1`，`evaluation_version: quality-v1`），结构为 `{resume_version, job_profile_id, thresholds_version, first_screen:{mode:explicit|fallback}, thresholds, tiers:{eligible,fit,strong,distinct}, auto_pass, llm_pending[], gap_tasks[], legacy_scores:{rule_total, llm_expression}}`；每层为 `{passed, failures:[{rule,target,reason}], metrics, matrix?, highlights?}`，failure 的 `target` 必须指向具体 bullet、经历条目或证据卡 id（`ec_*`）。`auto_pass = 四层 passed 且 llm_pending 为空`；Phase A 只实现规则判项，`R1.4/R2.1/R2.3/R3.1/R3.5/R4.1/R4.4` 仍在 `llm_pending`，因此 `auto_pass` 保持 false。规则总分与表达分只写入 `legacy_scores`，不再决定通过。评估阶段的 `pdf_check` 为空，`R1.5` 显式失败；PDF 导出后由 sidecar 用 `pdf_page_count` 回填页数并重算 `auto_pass`（裁切检查暂记 `clip_check:not_available`，真实两页无裁切由原生验收确认）。`run.quick.start` 返回顶层 `quality_report`；`resume_readiness` 增加 `auto_pass`、`quality_report`、`quality_failures[]`，删除 `evaluation_reference_score`。简历 Markdown 使用 `<!-- first-screen-end -->` 标记首屏，渲染层忽略该注释行。`NativePdfPreparation.quality` 增加 `auto_pass`、`quality_report`、`quality_failures[]`、`legacy_scores`，审批门禁改为消费 `quality_report.auto_pass`。

2026-10-18 生成按等级降级（Phase D1–D4）：A/B 简历模板按字段 provenance 渲染——L1/L4 可写负责/主导，L3 动作/结果降级参与/推动且角色行标注「参与 / 推动」，L5 时间卡不进入正文，`precision=year` 只呈现起始年；证据卡按 JD 语义引用排序（引用优先，未引用最多 4/最少 2 条），首屏标记 `<!-- first-screen-end -->` 位于第一条经历之后。生成 trace 的 `claims[]` 对 `time_range`/`role_scope` 增加 `provenance`（level/evidence/confirmed_by_user/first_person_hits 等），trace 顶层增加 `field_provenance:{card_id:{time_range,role_scope,time_range_level,role_scope_level}}`；评估器读取卡内 `*_provenance_json` 使 R1.4 对真实卡生效。B4 突出点正文回填未在本阶段实现（评估发生在生成之后）。

2026-10-20 DeepSeek Provider：`settings.get.llm_config` 增加 `thinking_enabled`、`api_key.source`（`saved|environment|legacy|none|storage_error`）与 `configured_providers[]`。`settings.update` 的 `llm_config` 支持 `thinking_enabled`，`api_key` 按 provider 写入本机凭据文件（0600），不写入 `policy.local.yaml`；`provider` 需匹配 `^[a-z][a-z0-9_]{0,31}$` 才能存取密钥。新增 RPC `settings.clearLlmApiKey`：params `{provider}`，返回 `{provider,cleared,configured_providers[]}`。`settings.checkLlmConnection` 使用 provider 名称；在线 provider 缺密钥返回 `BLOCKED_PROVIDER_CREDENTIAL`，LM Studio 既有 `BLOCKED_LOCAL_PROVIDER` 保持。`LLMClient` 对 `provider=deepseek` 注入 `thinking.disabled` 或 `thinking.enabled + reasoning_effort=high`，并支持 `LLM_THINKING=on/off` 环境变量；其他 provider 不受影响。

2026-10-18 证据可信等级与推断（Phase C）：`evidence.get`/`evidence.list` 增加字段级 provenance（`time_range_provenance`/`role_scope_provenance`，卡 YAML 以 `*_provenance_json` 持久化；L1–L5、precision/evidence/confidence/confirmed_by_user/first_person_hits；缺省按 L1/L5 兼容）与 `time_range_level`/`role_scope_level`。新 RPC `evidence.inferFields`：params `{card_ids?}`（缺省=分流为 needs_fill 且缺时间/角色的卡），返回 `{status,enabled,cards:[{card_id,card_sha256,cache,status,candidates:[{field,value,level,precision?,confidence,evidence[],first_person_hits?,candidate_hash}],documents,windows}],summary}`；候选不写卡，结果存 `app-data/evidence_inference.json`（按卡 sha256+文档集合缓存，否决 hash 不再提名）；关闭推断时 status=rules_only 且只返回 L2 时间线索。新 RPC `evidence.confirmInference`：params `{evidence_id,card_sha256,field,action:accept|reject,value?}`；accept 保留候选等级并写 `confirmed_by_user/confirmed_at`，修改值后接受记 L4，reject 记 hash；卡片进入待审核。`settings.get` 增加 `evidence_inference:{enabled}`，`settings.update` 支持 section `evidence_inference`（持久化 policy.local.yaml）。

2026-10-18 质量判项与突出点决策（Phase B）：Scorecard JSON 增加 `quality_judge:{cache:hit|miss|disabled,model,prompt_version,key?,judged_sections?,rejected_items?,error?}`；判项覆盖后 `quality_report.llm_pending` 清空，未覆盖/无效响应继续保留 pending（fail-closed，不伪造通过）。`tiers.distinct.highlights[]` 为 `{highlight_id,bullet_ref,jd_item_id,exceeds,level,reason,citations,first_screen,selected_by_user}`，`tiers.distinct.metrics.candidates[]` 为候选清单（含 `rejected` 标记）。新增 RPC `quality.decideHighlight`：params `{meta,run_id,resume_sha256,highlight_id,action:reject|select}`，写 `app-data/quality_decisions.json`（按 resume sha，同一候选 reject/select 互斥），返回 `run_id/resume_sha256/highlight_id/action/decisions:{rejected[],selected[]}`；错误码 `quality_run_id_invalid`/`quality_resume_sha256_invalid`/`quality_highlight_invalid`/`quality_decision_invalid`/`quality_run_not_found`。用户决策不写卡、不改生成事实，重新评测后生效。
2026-10-13 评估v3：Quick Run 的 `semantic_review` 增加 `assessment_scope:{qualification_count,responsibility_count,check_count}`，逐项 requirements 增加 `kind` 和 `checks:[{requirement_id,criterion,status,resume_status,reason,cautions?}]`。匹配产物保留子项判断并在复用时校验汇总一致性。`NativePdfPreparation.quality` 为 `unrecorded` 或绑定版本的 `{status:bound,matching_mode,matching_score,resume_score,expression_score,content_ready,quality_passed,gap_tasks,evaluation_version,...hashes}`；新候选质量摘要进入批准manifest，篡改摘要/内容或换PDF均拒绝。旧记录不回填虚构分数。原上传批准另记录 quality_sha256 与 accepted_quality_gaps，不增加新的平台权限。

2026-10-13 `evidence.saveDraft` 增量：同项目补证沿重审保存，增加 `expected_sha256` 和 `review.merge_sources`。开启补证时 source_material_ids/source_documents 只能追加、不能移除原来源，精确文档最多8个；`draft.field_sources` 为 `{field,value,quote,material_id,document_id}[]`，支持 time_range/role_scope/context/actions/results，逐项核对正文、原文及指纹。新事实必须绑定引用；普通编辑后的重审与最后批准的事实快照比较，不能把待审核编辑当成旧事实。陈旧卡版本报 `evidence_review_changed`，错误引用报 `field_source_*`，来源不允许的替换报 `evidence_review_source_mismatch`。`evidence.get` 返回 field_sources/source_sha256/source_error；来源失效时 candidate_pool_eligible=false。补证卡的材料指纹进入职业档案修订、语义输入与生成 trace，旧卡无此元数据时保持兼容。

> 状态：active
> 用途：冻结 Tauri host / React frontend / Python sidecar 之间的字段级 JSON-RPC contract，避免 UI 与 sidecar 并行开发时发生漂移。
> 裁决关系：若本文件与 `ui/design/DESIGN.md` 的 JSON-RPC 摘要冲突，以本文件为准；若与更高层产品约束冲突，以 `ui/design/DESIGN.md` 与 `AIEF/context/tech/GUI_ARCHITECTURE.md` 回收修正。

## 1. 总则

2026-10-12 求职偏好：`profile.get.profile.job_preferences` 返回 schema_version、items、source、revision、confirmed_at。`profile.generateJobPreferences(material_id, document_id)` 只生成 draft；items 为 kind(primary/bridge/explore/avoid)、text、quote。`profile.saveJobPreferences(draft, expected_revision, confirmed:true)` 校验来源与引用后保存；独立 revision 防止覆盖，职业档案 review 保留。Quick Run 新增可选 `career_direction`：status(aligned/needs_review/excluded)、reason、jd_quote、preference；excluded 时 run 为 SKIPPED，不进入生成与发送；无简历文件时 `resume_readiness.status=NOT_GENERATED`、`content_ready=false`，不能显示已生成。

2026-10-12 `run.quick.start` 增量：UI 默认 `options.use_llm=true` / `require_llm=true` / `timeout_seconds=1800`，关闭语义模式时明确传 false/false/120。结果可选 `semantic_review`（旧规则结果为 null/缺失）：`mode: semantic`、`fit_score`、`resume_score`、`expression_score`、`reviewed_card_count`、`all_requirements_supported`、`requirements[]`。每项含 `requirement_id/text/status/resume_status/reason/citations[]`；引用含 `fact_id/quote/source_id/field/in_resume`。证据池状态为 supported/partial/insufficient/conflict，简历状态另允许 not_present。语义结果下 `resume_readiness.evaluation_score` 使用非关键词表达分；有任何要求未支持或未呈现时质量不通过，`deliverable=false` 和现有审批边界保持。

- 传输模型固定为 `JSON-RPC 2.0 over stdio`
- request / response 使用 `id` 做单次配对
- 跨 request / response / event / log 的动作关联统一使用 `meta.correlation_id`
- 所有 `id`、`run_id`、`evidence_id`、`submission_id`、`resume_id`、`job_profile_id`、`job_lead_id` 均为字符串
- 时间字段统一使用 ISO-8601 UTC string，例如 `2026-03-07T10:00:00Z`

## 2. Envelope

### 原生猎聘会话 Host Command（2026-09-30）

`open_liepin_native_session`、`check_liepin_native_session`、`inspect_liepin_native_attachments` 是固定 Tauri Host Command，不经过 Python 会话存储。仅允许主窗口且当前来源为本地 App；远程猎聘页不能访问 sidecar 或本地文件。参数不接收任意 URL/脚本/凭据。

返回 `{status, url?, authenticated?, attachment_view?}`；URL 删除 query/fragment。`attachment_view` 仅包含 `entry_count`、`inputs: [{accept,multiple,disabled}]` 与有界 `hints`，不读取文件、Cookie 或 Token。登录/附件检查不代表上传或投递完成。网站安全验证优先于正向登录信号；无法确认时 fail closed。

`evidence.saveDraft` 允许库内 `.txt` 引用类型 `text_document`；仍要求审核和成果来源校验。`evidence.generateDraft` 继续仅接受 `.md`，前端对 TXT 只开放手动草稿。

Quick Run 页面明确传入 `options.material_id`；模板模式传入 `use_llm=false, require_llm=false`，选择模型润色后两者为 true。只复用现有 RPC 参数，不改变持久化 LLM 配置。

### 指定 PDF 原生投递（2026-09-30）

主界面 `run.agent.prepareLiepinPdf({quick_run_id})` 固定既有生成 PDF 原始字节、已审核 Lead/Profile 与独立追溯，返回 `meta, run_id, company, position, job_lead_id, matching_score, pdf_path, pdf_sha256, phase, account_effects_accepted, can_confirm_send`。已有运行恢复原快照与阶段，即使岗位已经占位也不能新建第二次操作。

固定 Host Command：`upload_liepin_native_pdf({runId,acceptAccountEffects})`、`inspect_uploaded_liepin_pdf({runId})`、`inspect_liepin_pdf_target({runId})`、`start_liepin_pdf_communication({runId})`、`continue_liepin_pdf_delivery({runId,action})`。最后一个的 action 仅为 `inspect|prepare|send`。所有命令要求本地主窗口来源；不接受文件路径、任意 URL/脚本、Token 或 Cookie。

Host 内部依次调用以下 sidecar 方法（均包含标准 `meta.correlation_id`）：

| 方法 | 输入与效果 |
| --- | --- |
| `run.agent.beginPdfUpload` | `run_id, accept_account_effects`；批准并在释放固定 PDF bytes 前写 in-flight，返回 upload_ref/filename/pdf_sha256/pdf_bytes；未知不重传 |
| `run.agent.finishPdfUpload` | `run_id, upload_ref, observation`；保留上传真实响应，尚不标投递成功 |
| `run.agent.inspectPdfPacket` / `recordPdfInspection` | 取得固定文件身份 / 写入有界观察；比对上传成功、当前唯一附件、fileId、附件 ID、文件大小；可回读时核对完整字节 SHA256 |
| `run.agent.pdfTargetPacket` / `recordPdfTarget` | 取得快照目标 / 保存真实 URL、公司、岗位与入口观察；不发送 |
| `run.agent.beginPdfDelivery` | `run_id`；复核最新 JD、审批、附件、排除规则，必须已有 generated_pdf 批次，原子占位后返回一次性 delivery_ref |
| `run.agent.recordPdfCommunication` | `run_id, delivery_ref, observation`；只记沟通阶段，不算 PDF 成功 |
| `run.agent.pdfInteractionPacket` / `recordPdfInteraction` | `run_id, action` / 加 delivery_ref、observation；发简历入口与最终确认各只执行一次，最终前验证唯一选中 fileId 和当前会话 |
| `run.agent.verifyPdfReceipt` | `run_id`；仅本地核验已保存的 send-resume 请求/响应、附件绑定、岗位上下文与快照，更新既有 SubmissionRecorder、占位与审批结果；重复调用幂等，无网络或重发 |

阶段：`prepared → in_flight → uploaded_unverified → attachment_verified → delivery_in_flight → communication_started → resume_interaction_pending → final_send_pending → success`。上传 `unknown` 保留原记录；只有同版官方 beforeUpload 契约证明旧 27 字符文件名在请求前拒绝，才记 `not_submitted` 并允许短名继续同一文件。`can_confirm_send` 来自后端对当前确认框的判断，不能由前端自报。

业务回执 parser v1 只认可实际观察到的固定 `https://api-c.liepin.com/api/com.liepin.im.c.chat.send-resume` POST、HTTP 200、匹配 attachmentId/会话请求及精确 `{"flag":1,"data":{}}` 成功形状；其他形状未知。私有 `native_receipt.json`、摘要日志、审批记录与 SQLite 均绑定同一 PDF/attempt，普通日志不含签名 URL 或请求头。最终发送开始后历史绑定冻结，当前平台附件变化不得使旧回执失效。

业务错误保持显式，例如 `account_effects_consent_required`、`pdf_upload_already_attempted`、`attachment_verification_required`、`pdf_batch_authorization_required`、`pdf_delivery_already_started`、`resume_interaction_already_started`、`pdf_confirmation_not_verified`、`pdf_final_send_already_started`、`pdf_receipt_unconfirmed`。原生 App 自行保存和核验的业务回执使用 `receipt_source=app_browser`。

### 渠道会话真实浏览器边界（2026-09-06 增量）

- `submission.channelSession.start/check/clear` 的业务输入均为 `channel`；凭证、验证码和短信输入仍禁止。`check` 的旧 `login_signals` / `account_identity` 参数不再采信，前端已移除。
- `start` 通过官网首页 `https://www.liepin.com/` 的实际表单/登录入口，确认手机号输入框可见后才返回 `opened_login_page=true`；已登录则直接检查并返回会话状态。该字段表示本次操作，不能从历史 `waiting_for_manual_login` 状态推导；HTTP 错误或表单不存在均为失败。
- `check` 从后端所持浏览器或已保存 profile 获取实际正向信号，并写入 `session.verification_source=owned_playwright`；只有正向信号且没有登录阻断时返回 `session_valid`。旧的未验证有效记录按 `session_unknown` 读取。
- 浏览器启动/检查失败通过现有 RPC error 返回，同时撤销旧的有效状态。成功检查释放 profile，后续投递默认复用 App profile；显式会话环境配置仍优先。
- 清除会话和 sidecar 关闭释放对应浏览器；无明文凭证、验证码或短信值进入 RPC。本增量不启用真实投递。

### 2.1 Request

```json
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "method": "evidence.list",
  "params": {
    "meta": {
      "correlation_id": "corr_001"
    }
  }
}
```

必填字段：

- `jsonrpc`: 固定 `"2.0"`
- `id`: request 唯一 ID
- `method`: 方法名
- `params.meta.correlation_id`: 当前用户动作链路的全局关联 ID

### 2.2 Success Response

```json
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "result": {
    "meta": {
      "correlation_id": "corr_001"
    }
  }
}
```

### 2.3 Error Response

```json
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "error": {
    "code": "TIMEOUT",
    "message": "sidecar request timeout",
    "details": {
      "correlation_id": "corr_001",
      "retryable": true
    }
  }
}
```

### 2.4 Event Notification

```json
{
  "jsonrpc": "2.0",
  "method": "event.emit",
  "params": {
    "event_type": "agent.run.updated",
    "correlation_id": "corr_001",
    "timestamp": "2026-03-07T10:00:00Z",
    "payload": {}
  }
}
```

## 3. Common Types

### 3.1 Pagination

```json
{
  "cursor": null,
  "page_size": 20
}
```

规则：

- `page_size` 默认 `20`
- 最大 `100`
- `cursor = null` 表示首屏

### 3.2 Sort

```json
{
  "field": "updated_at",
  "order": "desc"
}
```

规则：

- `order` 只能是 `asc | desc`
- `field` 必须在各方法白名单内

### 3.3 List Result

```json
{
  "items": [],
  "next_cursor": null
}
```

### 3.4 Secret Status

```json
{
  "configured": true,
  "masked": true,
  "updated_at": "2026-03-07T10:00:00Z"
}
```

规则：

- secret 不得以明文出现在任何 response 中
- UI 只能看到 `configured / masked / updated_at`

## 4. Error Codes

| Code | Retryable | 含义 |
|------|-----------|------|
| `UNSUPPORTED_VERSION` | no | 协议版本不兼容 |
| `SIDECAR_UNAVAILABLE` | yes | sidecar 不可用或连接断开 |
| `TIMEOUT` | yes | 请求超时 |
| `VALIDATION_ERROR` | no | 参数非法 |
| `NOT_FOUND` | no | 资源不存在 |
| `CONFLICT` | no | 资源状态冲突 |
| `STORAGE_ERROR` | maybe | 文件、截图或 secret 存储失败 |
| `PERMISSION_DENIED` | no | 权限不足 |
| `INTERNAL_ERROR` | maybe | 未分类内部错误 |

错误对象字段：

- `code`: 上表枚举
- `message`: 人类可读摘要
- `details.correlation_id`: 必填
- `details.retryable`: 必填
- `details.field_errors`: 仅 `VALIDATION_ERROR` 可选
- `details.resource_id`: 资源型错误可选

## 5. Event Types

| event_type | payload |
|------------|---------|
| `sidecar.state.changed` | `{ state, previous_state }` |
| `quick.run.updated` | `{ run_id, stage, status, progress, summary }` |
| `quick.run.log` | `{ run_id, stage, level, message }` |
| `agent.run.updated` | `{ run_id, status, round, gate_summary }` |
| `agent.run.log` | `{ run_id, level, message }` |
| `agent.run.event` | `{ run_id, type, description }` |
| `submission.updated` | `{ submission_id, status, channel }` |
| `settings.validation.failed` | `{ section, field_errors }` |

## 6. Method Contracts

### 6.1 system.handshake

用途：版本协商与能力声明。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "ui_version": "0.1.0",
  "protocol_version": "1.0.0",
  "capabilities": ["events", "file-preview", "pdf-export"]
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "accepted_protocol_version": "1.0.0",
  "sidecar_version": "0.1.0",
  "capabilities": ["events", "file-preview"],
  "deprecations": []
}
```

### 6.2 system.ping

`params`: `{ "meta": { "correlation_id": "corr_001" } }`

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "state": "ready",
  "timestamp": "2026-03-07T10:00:00Z"
}
```

### 6.3 system.shutdown

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "graceful": true
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "accepted": true
}
```

### 6.4 evidence.list

排序白名单：`updated_at`, `score`

筛选字段：`query`, `status`, `role`, `tags`, `date_range`

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "cursor": null,
  "page_size": 20,
  "sort": { "field": "updated_at", "order": "desc" },
  "filters": {
    "query": "",
    "status": null,
    "role": null,
    "tags": [],
    "date_range": null
  }
}
```

`result.items[]`

```json
{
  "evidence_id": "ec_001",
  "title": "Evidence title",
  "time_range": "2024.01 - 2024.12",
  "role_scope": "Backend Engineer",
  "score": 87,
  "status": "ready",
  "updated_at": "2026-03-07T10:00:00Z"
}
```

### 6.5 evidence.get

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence_id": "ec_001"
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence": {
    "evidence_id": "ec_001",
    "title": "Evidence title",
    "time_range": "2024.01 - 2024.12",
    "context": "Context",
    "role_scope": "Backend Engineer",
    "actions": "Actions",
    "results": "Results",
    "stack": ["Python", "PostgreSQL"],
    "tags": ["search", "ranking"],
    "artifacts": [
      {
        "resource_id": "res_001",
        "filename": "brief.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 12345,
        "created_at": "2026-03-07T10:00:00Z"
      }
    ]
  }
}
```

### 6.6 evidence.import

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "source_paths": ["/controlled/import/path/brief.pdf"],
  "target_evidence_id": null,
  "mode": "create"
}
```

规则：

- `mode`: `create | append | replace`
- 原始用户绝对路径不得在后续持久 response 中回显

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence_id": "ec_001",
  "imported_resources": ["res_001"]
}
```

### 6.7 jobs.listProfiles

排序白名单：`match_score`, `updated_at`

筛选字段：`status`, `query`, `tags`

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "cursor": null,
  "page_size": 20,
  "sort": { "field": "updated_at", "order": "desc" },
  "filters": {
    "status": null,
    "query": "",
    "tags": []
  }
}
```

`result.items[]`

```json
{
  "job_profile_id": "jp_001",
  "title": "Senior Backend Engineer",
  "company": "Acme",
  "status": "active",
  "match_score": 82,
  "evidence_count": 5,
  "resume_count": 0,
  "updated_at": "2026-03-07T10:00:00Z",
  "business_domain": "E-commerce",
  "source_jd": "jd_inputs/jd-2026-001.txt",
  "tone": "architecture",
  "keywords": ["Python", "Kafka"],
  "must_have": ["Distributed systems", "Stability"],
  "nice_to_have": ["FinOps"],
  "seniority_signal": ["Owner"]
}
```

规则：

- `cursor = null` 表示首屏；`next_cursor` 为下一个 offset 的字符串，传回 `cursor` 后继续分页
- `status` 缺省时，若已有 matching report 则 sidecar 推导为 `active`，否则推导为 `draft`
- `match_score`、`evidence_count`、`updated_at` 取同一 `job_profile_id` 最新 matching report 快照；若不存在 matching report，则返回 `0 / 0 / job_profile 文件 mtime（格式化为 ISO-8601 UTC string）`
- `resume_count` 当前首版固定返回 `0`，后续接入 Resume 资产后再扩展
- `tags` 当前匹配 `keywords` 字段，采用大小写不敏感的全量包含匹配

### 6.8 jobs.listLeads

排序白名单：`updated_at`, `created_at`

筛选字段：`source`, `status`, `favorited`, `query`

`result.items[]`

```json
{
  "job_lead_id": "jl_001",
  "company": "Acme",
  "position": "Backend Engineer",
  "source": "liepin",
  "status": "new",
  "favorited": false,
  "updated_at": "2026-03-07T10:00:00Z"
}
```

### 6.9 jobs.convertLead

2026-09-28 增量：`jobs.listLeads.items[]` 兼容增加 `url`、`platform`、`platform_job_id`、`platform_job_type`、`jd_status`、`fetched_at`。旧数据缺失时返回空字符串。猎聘官方搜索仅提供摘要，标记 `jd_status=summary_only`；转换时 `source_jd` 留空、URL 放 `source_url`、关联原 `job_lead_id`，画像状态为 `saved_incomplete`，待完整 JD 补齐与审核。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "job_lead_id": "jl_001"
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "job_profile_id": "jp_001"
}
```

### 6.10 run.quick.start

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence_id": "ec_001",
  "job_profile_id": "jp_001",
  "options": {
    "generate_resume": true
  }
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "qr_001",
  "status": "DONE",
  "exit_code": 0,
  "run_record": "outputs/agent_runs/qr_001/run_log.json",
  "summary": "outputs/agent_runs/qr_001/summary.json"
}
```

说明：
- `run.quick.start` 启动本地单次 pipeline；当前 sidecar 同步返回执行结果。
- `status` 可为 `DONE`、`SKIPPED`、`FAILED` 或 `TIMEOUT`。
- `resume_readiness` 独立于执行状态，包含 `status`（`NEEDS_EVIDENCE` / `NEEDS_REVIEW`）、`deliverable=false`、`quality_passed`（由 `quality_report.auto_pass` 与追溯/PDF/语义完整性门禁共同决定）、`auto_pass`、`quality_report`、`quality_failures[]`、`evaluation_score`（旧版参考分，仅展示）、`reasons[]`、`gap_tasks[]` 及缺失资料字段；不再提供 `evaluation_reference_score`（78 参考线已废弃）；本轮未实现人工批准写回，不自动标记可投递。
- generation 使用简历中心 `personal_profile.yaml` 和选定 Job Profile/JD；`artifacts.resume_trace` 指向独立 `.trace.json`，`traceability.resume_traceable` 通过正文与输入指纹检查得出，正文不承载内部追溯标记。
- CLI fallback 仍可由 UI 展示，但 Quick Run 页面不再只展示命令。
- 桌面端 Quick Run 自动化不属于 sidecar JSON-RPC contract。验收必须由外部自动化驱动真实页面或真实桌面壳；生产前端不得内置 verifier env 分支、自启动验收流程或验收事件钩子。外部脚本应通过真实 UI 动作与 `outputs/quick_runs` / summary 等产物校验结果。

### 6.11 run.quick.cancel

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "qr_001"
}
```

`result`: `{ "meta": { "correlation_id": "corr_001" }, "accepted": true }`

### 6.12 run.agent.start

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "job_profile_id": "jp_001",
  "options": {
    "max_rounds": 5,
    "execute_dry_run": false
  }
}
```

说明：
- `execute_dry_run` 缺省为 `false`；缺省行为只创建桌面端运行控制记录并返回 `queued`。
- 仅当 `execute_dry_run=true` 时，sidecar 可执行本地 dry-run AgentLoop；该模式不得触发真实投递或外部可见动作。

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "ar_001",
  "status": "queued"
}
```

### 6.13 run.agent.stop

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "ar_001"
}
```

`result`: `{ "meta": { "correlation_id": "corr_001" }, "accepted": true }`

### 6.14 run.agent.get

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "ar_001",
  "event_cursor": null,
  "event_limit": 50
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run": {
    "run_id": "ar_001",
    "status": "EVALUATE",
    "round": 2,
    "started_at": "2026-03-07T10:00:00Z"
  },
  "gate_checks": [],
  "events": [],
  "next_event_cursor": null
}
```

### 6.15 resume.list

说明：Resumes 页面首版 bridge 可通过聚合 `personal_profile`、`uploaded_resumes[]`、`generated_resumes[]` 与当前选中版本 `preview` 载荷满足 UI 读取需求；在单一 RPC 方法未冻结前，不强制拆分为独立 profile 或 preview 方法。

排序白名单：`updated_at`, `score`

筛选字段：`job_profile`, `status`, `company`

`result.items[]`

```json
{
  "resume_id": "rv_001",
  "name": "Resume v3",
  "job_profile_id": "jp_001",
  "status": "latest",
  "score": 86,
  "company": "Acme",
  "updated_at": "2026-03-07T10:00:00Z"
}
```

### 6.16 resume.exportPdf

Markdown 简历通过共享 HTML/CSS 模板导出，返回 `html_path` 指向同源 HTML。缺少渲染器、超时或无完整 PDF 时返回错误且保留原 PDF，不静默降级为纯文本版；已上传 PDF 的复制行为保持不变。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "resume_id": "rv_001",
  "destination": "/controlled/export/path/resume.pdf"
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "resource_id": "pdf_001"
}
```

### 6.17 submission.list

排序白名单：`submitted_at`, `status`

筛选字段：`company`, `channel`, `status`, `date_range`

`result.items[]`

```json
{
  "submission_id": "sub_001",
  "company": "Acme",
  "position": "Backend Engineer",
  "channel": "liepin",
  "mode": "check",
  "status": "done",
  "error": "",
  "job_url": "https://www.liepin.com/job/123.shtml",
  "submitted_at": "2026-03-07T10:00:00Z",
  "last_step": {
    "name": "submit",
    "status": "skipped",
    "detail": "submit not enabled; stopped before final confirm"
  },
  "rate_limit_status": "success",
  "rate_limit_detail": "batch_count=1; daily_count=1"
}
```

### 6.18 submission.detail

原生会话观测新增派生布尔值 `can_return_to_attachments`，仅官方 `/resume/parse-result` 且状态为 unverified/authenticated 时为 true。`check_liepin_native_session` 在该条件下复核当前 URL，正常导航固定附件页后重新观察认证；不会把该布尔值当登录成功，不提交同步表单，登录/安全验证/空白不触发恢复。

已完成 PDF 的平台附件移除：新增固定 Host Command `remove_liepin_native_pdf_attachment(run_id, confirmed)`，仅本地主窗口可用，前端不能传文件名/路径/平台 ID。返回原 `NativePdfPreparation`，附 `platform_filename` 与 `attachment_removal_state`。内部 `run.agent.beginPdfRemoval` 要求 confirmed=true、完整成功证据、120秒内的唯一当前卡片及原字节校验，再保存 in_flight/removal_ref；`run.agent.finishPdfRemoval` 必须引用同一 removal_ref。精确 `remove-attachment-resume` POST 回执含同一 encryAttachmentId、HTTP200/flag1，且前后 fileId 集合仅移除目标时为 removed；否则 unknown 且不重试。只有程序证明未点击最终确认且无移除请求时为 not_submitted，可重新检查。原 PDF、历史回执、成功状态、投递额度不变。错误包括 `attachment_removal_confirmation_required`、`attachment_removal_success_required`、`attachment_removal_identity_unverified`、`attachment_removal_already_attempted`、`attachment_removal_not_pending`。

固定只读 Host Command `recheck_liepin_native_pdf_removal(run_id)` 先刷新原附件检查，再调用 `run.agent.recheckPdfRemoval`。只有 unknown 中明确零请求放行、至少一个请求前拦截、无网络回执、目标及集合原样，以及当前同一附件原字节成立，才保存 `request_guard_blocked_before_send` 复核证据并返回 not_submitted；保留旧 unknown 历史，不调用移除脚本。其他情况返回 `attachment_removal_outcome_unverified` 或当前身份错误。JSON 的单一 data 封装在请求发出前校验，不放宽身份或一次性约束。

2026-10-01 多附件增量：原生 PDF 的绑定记录 `attachment_count` 表示账号当次列表数量，可大于 1；目标附件仍须由上传响应 fileId、批准文件名/长度与当前卡片唯一关联。`continue_liepin_pdf_delivery(action=prepare)` 仅在验证目标会话后打开确认框并选中唯一已批准 fileId，不执行最终发送；send 保持独立且重新核对。附件只读 `hints` 最多 20 条，其中最多 10 条为有界的可见控件文本，不回传脚本、凭据或任意页面对象。

2026-10-01：受控真实投递新增 `evidence`：`status=verified|incomplete`、`reason`、`parent_run_id`、`job_lead_id`、`job_profile_id`、`delivery_kind`、`resume_version_id`、`resume_sha256`、`receipt_source`、`receipt_sha256`。只读核验批准快照、回执与 SQLite；不完整不改投递状态。`retry_allowed=false` 同时适用于列表、详情中的同通道/邮件重试。

`submission.feedback.list(source_run_id)` 保留 `items/supported_actions`，新增同源 `source_binding` 与 `iterations` 历史记录。真实投递终态来源为 `submission_receipt`，成功为 info，不再误报 check-mode 高优先级错误。

`submission.feedback.createIteration` 对受控真实投递接受 `feedback_source=user_note|manual_recruiter`（默认 user_note）、必填且不超过 4000 字符的 `user_notes`、现有动作集合中除 `prepare_next_check_mode` 的动作。服务器派生来源与版本，拒绝其他投递的 `source_feedback_items` 和直接提交 `new_or_updated_claims`。记录保存 `source_binding`、`feedback_source`、`source_snapshot_sha256`；原日志/PDF/回执不变，记录文件 0600。重新生成动作只返回 `next_quick_run_candidate`（岗位画像、原提交编号、需审核），`new_resume_version_id_or_none` 保持空。错误包括 `feedback_source_mismatch`、`feedback_note_required`、`feedback_note_too_long`、`unsupported_feedback_source`、`feedback_claims_require_generation`、`feedback_job_profile_missing`、`managed_feedback_use_quick_run`。旧检查模式返回契约保留。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "submission_id": "sub_001"
}
```

`result.submission`

```json
{
  "submission_id": "sub_001",
  "company": "Acme",
  "position": "Backend Engineer",
  "channel": "liepin",
  "mode": "check",
  "status": "success",
  "error": "",
  "job_url": "https://www.liepin.com/job/123.shtml",
  "submitted_at": "2026-03-07T10:00:12Z",
  "started_at": "2026-03-07T10:00:00Z",
  "ended_at": "2026-03-07T10:00:12Z",
  "resume_path": "outputs/v1.md",
  "profile_path": "profiles/candidate_profile.yaml",
  "headless": false,
  "browser_channel": "chrome",
  "last_step": {
    "name": "submit",
    "status": "skipped",
    "detail": "submit not enabled; stopped before final confirm"
  },
  "rate_limit_status": "success",
  "rate_limit_detail": "batch_count=1; daily_count=1",
  "steps": [
    {
      "name": "open_job_page",
      "status": "success",
      "detail": "job page opened",
      "screenshot": "screenshots/02_open_job_page.png",
      "screenshot_path": "outputs/submissions/liepin/sub_001/screenshots/02_open_job_page.png",
      "screenshot_exists": true
    }
  ],
  "log_json_path": "outputs/submissions/liepin/sub_001/submission_log.json",
  "log_yaml_path": "outputs/submissions/liepin/sub_001/submission_log.yaml"
}
```

规则：

- `steps[]` 必须保持日志中的原始顺序。
- `screenshot_path` 只允许指向当前 run 目录内文件；越界路径必须返回空字符串且 `screenshot_exists=false`。
- `log_yaml_path` 在 YAML 日志不存在时返回空字符串。

### 6.19 submission.retry

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "submission_id": "sub_001",
  "strategy": "same_channel"
}
```

规则：

- `strategy`: `same_channel | fallback_email`

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "submission_id": "sub_001",
  "status": "queued"
}
```

### 6.20 settings.get

`params`

```json
{
  "meta": { "correlation_id": "corr_001" }
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "gate_policy": {
    "n_pass_required": 3,
    "matching_threshold": 70,
    "evaluation_threshold": 75,
    "max_rounds": 5,
    "gate_mode": "strict",
    "delivery_mode": "auto",
    "batch_review": false
  },
  "exclusion_list": [],
  "excluded_legal_entities": [],
  "channels": [],
  "llm_config": {
    "provider": "deepseek",
    "model": "deepseek-flash",
    "base_url": "https://api.deepseek.com",
    "api_key": {
      "configured": true,
      "masked": true,
      "updated_at": "2026-10-20T10:00:00Z",
      "source": "saved"
    },
    "configured_providers": ["deepseek"],
    "thinking_enabled": false,
    "timeout": 60,
    "temperature": 0.2
  }
}
```

### 6.21 settings.update

2026-09-28 增量：`settings.get` 额外返回 `liepin_api`，使用下述 `LiepinAuthState`。它表示官方只读连接，与既有 `channels` 中浏览器投递会话状态独立；配置了只读 Token 不代表允许投递。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "section": "gate_policy",
  "payload": {
    "delivery_mode": "manual",
    "batch_review": true
  }
}
```

规则：

- `section`: `gate_policy | exclusion_list | excluded_legal_entities | llm_config`
- `gate_policy` payload 当前支持更新字段：`delivery_mode`、`batch_review`；为部分更新，未传字段保持原值
- `delivery_mode` 枚举：`auto | manual`；`batch_review` 为布尔值，仅 `delivery_mode=manual` 时生效
- `llm_config` payload 当前支持更新字段：`provider`、`model`、`base_url`、`api_key`、`timeout`、`temperature`、`thinking_enabled`；为部分更新，未传字段保持原值
- `api_key` 按 provider 保存到本机凭据文件；payload 携带 `api_key` 时，`provider`（或当前已保存 provider）必须匹配 `^[a-z][a-z0-9_]{0,31}$`，否则拒绝
- `provider=lm_studio` 且 `api_key="lm-studio"` 保持本地占位语义，不强制创建凭据文件
- `thinking_enabled` 为布尔值，仅 `provider=deepseek` 时影响请求；写入 `policy.local.yaml` 的 `llm_thinking_enabled`
- `channels` 当前为 `settings.get` 只读返回字段，不支持 `settings.update`
- `settings.get` 永不返回 secret 明文

2026-09-28 本地模型兼容：`provider=lm_studio` 的结构化提取在 infra 将旧 `json_object` 转成对象 `json_schema`；Jobs 使用现有草稿字段类型的 schema，业务必需字段与严格 JSON 校验不变。对已实测 `qwen/qwen3.8-27b`，仅该转换且调用方未显式指定时，单次请求补 `reasoning_effort=none`；不改变 LM Studio 全局配置或其他服务商/模型的设置。连接检查只证明模型列表可读取，实际推理单独验收。

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "section": "gate_policy",
  "saved": true
}
```

### 6.22 settings.checkLlmConnection

用途：只读检查 OpenAI-compatible 本地模型端点，用于 System Settings / 用户旅程验收。该方法只返回结构化成功或 blocked 状态，不写入配置。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "payload": {
    "base_url": "http://127.0.0.1:1234/v1",
    "api_key": "lm-studio",
    "timeout": 1
  }
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "status": "blocked",
  "code": "BLOCKED_LOCAL_PROVIDER",
  "message": "LM Studio models endpoint is unavailable at http://127.0.0.1:1234/v1/models: connection refused",
  "base_url": "http://127.0.0.1:1234/v1",
  "model_count": 0,
  "models": []
}
```

规则：

- `status`: `pass | blocked`
- 成功时 `code=OK` 且 `models` 返回最多 20 个模型 id
- `provider=lm_studio` 的本地端点不可达、返回空模型列表或未配置 base_url 时，返回 `code=BLOCKED_LOCAL_PROVIDER`
- `openai_compatible` 的 localhost 端点允许不带密钥，但失败时返回 `code=BLOCKED_PROVIDER` 且消息使用 provider 名称，不冒用 LM Studio
- 在线 provider（OpenAI / DeepSeek / OpenAI Compatible）缺少密钥时返回 `code=BLOCKED_PROVIDER_CREDENTIAL`；其余不可达/空列表返回 `code=BLOCKED_PROVIDER`
- 请求的 provider 与当前生效 provider 不同时，只读取该 provider 自己的凭据文件；不得复用当前生效密钥
- 请求的 provider 与当前生效 provider 不同且 payload 未提供 `base_url` 时，返回 blocked，不得把目标 provider 的密钥发往当前生效端点
- 返回值不得包含 API key 明文

### 6.22.1 settings.clearLlmApiKey

用途：按 provider 删除本机保存的模型 API Key，不修改 model/base_url/timeout/temperature。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "provider": "deepseek"
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "provider": "deepseek",
  "cleared": true,
  "configured_providers": ["lm_studio"]
}
```

规则：

- `provider` 必须匹配 `^[a-z][a-z0-9_]{0,31}$`
- 未保存的 provider 删除为空操作，仍返回 `cleared=true`
- 删除失败返回固定错误，不包含路径、密钥或底层异常
- 清除当前 provider 后，`settings.get.llm_config.api_key.configured=false`（除非环境变量仍提供密钥）

### 6.23 evidence.create

用途：创建一张空白证据卡，对应 Evidence 页面 "New Card / 新增" 按钮。创建成功后 UI 可立即跳转到详情编辑态。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "title": "Evidence title",
  "time_range": "2024.01 - 2024.12",
  "context": "",
  "role_scope": "Backend Engineer",
  "actions": "",
  "results": "",
  "stack": [],
  "tags": []
}
```

规则：

- `title` 必填，最长 200 字符；其余文本字段可为空字符串
- `stack` 与 `tags` 为字符串数组，允许空数组
- 创建成功后自动分配 `evidence_id`，`status` 初始为 `"draft"`

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence_id": "ec_002",
  "status": "draft",
  "created_at": "2026-03-07T10:00:00Z"
}
```

### 6.24 evidence.update

用途：更新证据卡的文本字段，对应 Evidence 详情面板编辑功能（编辑图标触发）。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence_id": "ec_001",
  "patch": {
    "title": "Updated title",
    "time_range": "2024.01 - 2025.06",
    "context": "Updated context",
    "role_scope": "Senior Backend Engineer",
    "actions": "Updated actions",
    "results": "Updated results",
    "stack": ["Python", "PostgreSQL", "Redis"],
    "tags": ["search", "ranking", "performance"]
  }
}
```

规则：

- `patch` 为部分更新；仅传入需要修改的字段，未传字段保持原值
- `evidence_id` 不存在时返回 `NOT_FOUND`
- `title` 若传入则不得为空字符串
- `artifacts` 不通过本方法更新，使用 `evidence.import` 管理附件

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence_id": "ec_001",
  "updated_at": "2026-03-07T10:05:00Z"
}
```

### 6.25 evidence.delete

用途：删除指定证据卡及其所有附件，对应 Evidence 详情面板删除图标触发。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence_id": "ec_001"
}
```

规则：

- `evidence_id` 不存在时返回 `NOT_FOUND`
- 删除为逻辑软删除；关联附件文件引用计数归零后由 sidecar 异步回收
- 若证据卡正被活跃 run 引用，返回 `CONFLICT`，不执行删除

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "evidence_id": "ec_001",
  "deleted": true
}
```

### 6.26 overview.get

用途：拉取 Overview 页面全部聚合数据，包含 4 个统计指标、最近活动流、匹配趋势折线数据与缺口列表。无分页，一次性返回。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" }
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "metrics": {
    "evidence_count": 12,
    "matched_jobs_count": 8,
    "resume_count": 5,
    "submission_count": 23
  },
  "recent_activities": [
    {
      "activity_id": "act_001",
      "type": "resume_generated",
      "description": "Resume v3 generated for Acme",
      "timestamp": "2026-03-07T09:50:00Z"
    },
    {
      "activity_id": "act_002",
      "type": "submission_sent",
      "description": "Submitted to Acme via liepin",
      "timestamp": "2026-03-07T09:30:00Z"
    }
  ],
  "match_trend": [
    { "date": "2026-02-28", "score": 74 },
    { "date": "2026-03-01", "score": 78 },
    { "date": "2026-03-07", "score": 87 }
  ],
  "gaps": [
    {
      "gap_id": "gap_001",
      "severity": "high",
      "description": "Missing system design evidence for target roles",
      "suggested_action": "Add evidence card for distributed system projects"
    }
  ]
}
```

规则：

- `recent_activities[].type` 枚举：`resume_generated | submission_sent | evidence_imported | agent_run_completed`
- `match_trend` 按 `date` 升序排列，最多返回最近 30 个数据点
- `gaps[].severity` 枚举：`high | medium | low`
- 任一聚合子请求失败时，整体返回 `INTERNAL_ERROR`，不做部分成功

### 6.27 resume.upload

用途：上传用户本地简历文件，对应 Resumes 页面 "Upload Resume / 上传简历" 按钮。模式固定为 `create`，每次调用创建新的已上传简历记录。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "source_paths": ["/controlled/import/path/my_resume.pdf"],
  "language": "zh",
  "label": "简历 2025 版"
}
```

规则：

- `source_paths` 长度固定为 1；不支持批量上传
- `language` 枚举：`zh | en`；不传时 sidecar 自动检测，检测失败默认 `zh`
- `label` 可选，最长 100 字符；不传时以文件名（去除扩展名）作为默认标签
- 原始用户绝对路径不得在后续持久 response 中回显
- 支持 mime type：`application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "resume_id": "rv_010",
  "label": "简历 2025 版",
  "language": "zh",
  "resource_id": "res_010",
  "uploaded_at": "2026-03-07T10:00:00Z"
}
```

### 6.28 resume.getPreview

可渲染的生成 Markdown 和上传文本增量返回 `preview_html`，与 PDF 导出调用同一模板；`preview` 结构保留兼容。GUI 在现有白纸区域以 sandbox iframe 等比显示，禁止脚本、导航和远程资源。PDF/DOCX 等原先 pending 的预览不伪造 HTML 内容。

用途：获取指定简历版本的结构化预览数据，供 Resumes 页面 Preview 面板渲染白色纸张预览区。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "resume_id": "rv_001"
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "resume_id": "rv_001",
  "preview": {
    "name": "Zhang San",
    "contact": {
      "phone": "+86 138 0000 0000",
      "email": "zhangsan@example.com",
      "city": "Beijing"
    },
    "summary": "Experienced backend engineer with 5 years in distributed systems.",
    "experience": [
      {
        "company": "Acme",
        "title": "Senior Backend Engineer",
        "period": "2022.01 - 2025.01",
        "bullets": [
          "Built high-throughput search service handling 100k QPS",
          "Reduced p99 latency from 200ms to 40ms"
        ]
      }
    ],
    "skills": ["Python", "Go", "PostgreSQL", "Kubernetes"]
  }
}
```

规则：

- `resume_id` 不存在时返回 `NOT_FOUND`
- `preview` 为渲染所需的结构化字段，不含原始 Markdown 或 HTML
- 若简历尚未生成可渲染预览（如刚上传的原始文件），返回 `preview: null` 并附 `preview_status: "pending"`

### 6.29 profile.get

用途：读取当前用户的个人资料，对应 Resumes 页面 Personal Profile 区域的展示数据。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" }
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "profile": {
    "name": "Zhang San",
    "phone": "+86 138 0000 0000",
    "email": "zhangsan@example.com",
    "city": "Beijing",
    "current_position": "Senior Backend Engineer",
    "completeness": 80,
    "missing_fields": ["city"],
    "updated_at": "2026-03-07T09:00:00Z"
  }
}
```

规则：

- `completeness` 为 0-100 整数，由 sidecar 根据必填字段覆盖率计算
- `missing_fields` 为字段名数组，枚举值为 `name | phone | email | city | current_position`
- 首次使用时 profile 可能全为空，此时 `completeness` 为 0，`missing_fields` 包含全部 5 个字段

### 6.30 profile.update

用途：保存用户个人资料编辑结果，对应 Resumes 页面 "Edit Info / 编辑资料" 操作提交。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "expected_revision": "revision_from_profile_get",
  "patch": {
    "name": "Zhang San",
    "phone": "+86 138 0000 0000",
    "email": "zhangsan@example.com",
    "city": "Beijing",
    "current_position": "Senior Backend Engineer"
  }
}
```

规则：

- `expected_revision` 必须来自加载该表单的 `profile.get`，缺失或版本过期返回 `profile_changed`

- `patch` 为部分更新；仅传入需要修改的字段，未传字段保持原值
- `email` 若传入必须为合法邮箱格式，否则返回 `VALIDATION_ERROR`
- `phone` 若传入允许国际格式，不做严格校验
- 所有字段均为明文字符串，无 secret 字段，response 不涉及任何敏感信息

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "saved": true,
  "updated_at": "2026-03-07T10:10:00Z"
}
```

### 6.31 jobs.createProfile

用途：创建新的 Job Profile，对应 Jobs 页面 "New Profile / 新建" 主按钮。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "title": "Senior Backend Engineer",
  "description": "Looking for backend engineer with distributed systems experience.",
  "tags": ["Python", "Go", "Kubernetes"],
  "status": "draft"
}
```

规则：

- `title` 必填，最长 200 字符
- `status` 枚举：`active | draft`；不传时默认 `draft`
- `tags` 为字符串数组，允许空数组
- 创建成功后自动分配 `job_profile_id`，`match_score` 初始为 `null`

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "job_profile_id": "jp_010",
  "status": "draft",
  "created_at": "2026-03-07T10:00:00Z"
}
```

### 6.32 jobs.updateProfile

用途：更新 Job Profile 字段，对应 Jobs 页面卡片编辑操作。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "job_profile_id": "jp_001",
  "patch": {
    "title": "Senior Backend Engineer (Updated)",
    "description": "Updated description with additional requirements.",
    "tags": ["Python", "Go", "PostgreSQL"],
    "status": "active"
  }
}
```

规则：

- `patch` 为部分更新；仅传入需要修改的字段，未传字段保持原值
- `job_profile_id` 不存在时返回 `NOT_FOUND`
- `status` 枚举：`active | draft | archived`
- `title` 若传入则不得为空字符串

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "job_profile_id": "jp_001",
  "updated_at": "2026-03-07T10:15:00Z"
}
```

### 6.33 jobs.deleteProfile

用途：删除指定 Job Profile，对应 Jobs 页面卡片删除操作。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "job_profile_id": "jp_001"
}
```

规则：

- `job_profile_id` 不存在时返回 `NOT_FOUND`
- 删除为逻辑软删除；关联的 Job Leads 引用不自动级联删除，但 `job_profile_id` 外键置 `null`
- 若 Job Profile 正被活跃 run（`run.agent.start` 或 `run.quick.start`）引用，返回 `CONFLICT`，不执行删除

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "job_profile_id": "jp_001",
  "deleted": true
}
```

## 7. Security Boundary

- secret 不得进入前端持久化 state；默认 OS credential store 规划保留，但猎聘 Token 按 2026-09-28 用户指定改用本机明文权限文件，不接入钥匙串，具体边界见 6.37 官方只读接口。
- secret 不得出现在导出配置文件中
- 配置导出时，secret 字段必须导出为 `{ "configured": true }` 或完全省略
- 配置导入时，若文件中包含 secret 明文字段，必须直接返回 `VALIDATION_ERROR`
- 日志、事件、错误对象中不得包含 secret 明文

## 8. Parallel Development Rule

- 在 `ui/design/contracts/sidecar-rpc.md` 未冻结前，不得并行实现 UI typed client 与 Python sidecar handlers
- 若 method、字段、错误码、event payload 任一变更，必须同步更新：
  - `ui/design/contracts/sidecar-rpc.md`
  - `ui/design/DESIGN.md` 中的协议摘要
  - 相关实现代码与测试

### 6.34 run.agent.getPendingReview

2026-09-28 增量：返回明确的 `run_id`、`delivery_results`，候选包括待审批及已批准但尚未恢复执行的项。每项额外带 `status`、`snapshot_status: ready|invalid` 和只读 `resume_preview`（固定 Markdown 原文）。返回前核对后台快照清单、岗位身份及 Markdown/PDF 指纹；缺失/变更不能批准。省略 run_id 时按最近更新时间恢复队列，不按文件名字典序猜测新旧。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "run_2026_001"
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "candidates": [
    {
      "job_lead_id": "jl_001",
      "company": "Acme",
      "position": "Backend Engineer",
      "matching_score": 85,
      "evaluation_score": 90,
      "round_index": 1,
      "resume_version": "v1",
      "job_url": "https://example.com/job/1"
    }
  ]
}
```

### 6.35 run.agent.submitReview

2026-09-28 增量：写操作要求明确的安全 `run_id`。整批决策在写入前校验候选、动作及快照；重复同意幂等，不重复计入 accepted，拒绝/跳过后的候选不能在原队列改回批准。决定先原子持久化，再从保存的文件恢复执行；不再次生成简历。返回 `{accepted, delivery_results}`，每个结果含 `job_lead_id/status/code/success/submission_id`；批准数与真实成功数分开。

运行回读同步 `review_queue/delivery_results/deliveries_completed` 和事件：`REVIEWED_CHECK_ONLY` 表示检查通过但未发送，`DELIVERY_BLOCKED` 表示存在阻断/未知，`REVIEW_SNAPSHOT_BLOCKED` 表示文件准备失败。dry-run 从后台不可变快照取得，前端不能升级；真实官方来源仍明确阻断 `official_delivery_contract_unverified`。结果未知暂停剩余已批准项且禁止继续同批发送。历史无快照队列只可拒绝/跳过，需重新生成后审批；`createReviewCandidates` 不接受前端注入快照。

审批写入使用进程锁和原子替换；同一运行已有队列不能由创建接口或重新运行覆盖。已有批准项只能继续原快照，不能重新批准计数。渠道回执明确 `not_submitted` 时不占真实发送记录；有成功回执才记成功，明确失败与未知单独保留。当前该恢复入口只支持猎聘通道，其他通道返回 `reviewed_channel_unavailable`，不会经 Email 降级。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "run_2026_001",
  "decisions": [
    {
      "job_lead_id": "jl_001",
      "action": "approve",
      "decided_by": "user",
      "decided_at": "2026-03-13T10:00:00Z",
      "note": "Good match"
    }
  ]
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "accepted": 1
}
```

### 6.36 run.agent.createReviewCandidates

Internal API for run_agent to populate review queue.

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "run_2026_001",
  "candidates": [
    {
      "job_lead_id": "jl_001",
      "company": "Acme",
      "position": "Backend Engineer",
      "matching_score": 85,
      "evaluation_score": 90,
      "round_index": 1,
      "resume_version": "v1",
      "job_url": "https://example.com/job/1"
    }
  ]
}
```

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "run_id": "run_2026_001",
  "created": 1
}
```

### 6.37 猎聘官方只读接入（P0-011，2026-09-28）

三个新方法均经过现有 stdio JSON-RPC，不新增 HTTP/RPC 服务端口。平台访问固定官方 HTTPS，仅允许读取简历与搜索；不接受调用方设置 base URL、请求路径、请求头或写操作。

`LiepinAuthState`（无 Token 值或可逆掩码）：

```json
{
  "configured": false,
  "state": "unconfigured",
  "code": "AUTH_REQUIRED",
  "last_checked_at": "",
  "last_error": "",
  "scope": "read_only",
  "storage": "local_file",
  "storage_path": "~/Library/Application Support/PiProofForge/credentials/liepin-token",
  "saved": false
}
```

- `state`：`unconfigured | unverified | valid | invalid | rate_limited | error`。
- `settings.get` 只读回状态，不触发外部请求；原浏览器 profile 不改变该状态。
- 2026-09-28 替代会话内存方案：用户接受本地明文权限文件、不接入钥匙串。macOS 固定路径 `~/Library/Application Support/PiProofForge/credentials/liepin-token`，凭据目录 `0700`、文件 `0600`；首次使用恢复为 `unverified`。正常 shutdown/进程退出只释放内存，不删除保存项。前端提交后清空输入框，不进入 localStorage、普通配置、导出文件或日志。
- `valid` 仅在后端只读请求的 HTTP、业务码和结构校验均通过后建立。失败撤销旧有效态；业务结果未知不自动重试。

**settings.liepinCredential**

- 入参：`{meta, action: "set" | "check" | "clear", token?: string}`；`set` 使用 token，其他操作不需要传凭据。
- 返回：`{meta, auth: LiepinAuthState}`。
- `set` 校验并原子保存文件后更新内存，不访问平台，状态为 `unverified`；空白/非法输入返回 `INVALID_INPUT` 并保留原有保存项。文件保存失败返回 `CREDENTIAL_STORAGE_ERROR`，不宣称新 Token 已保存。
- `check` 使用后端 Token 读取平台简历验证业务连接，仅返回状态，丢弃正文；`clear` 删除本地保存项后清理内存与检查结果，删除失败返回 `CREDENTIAL_STORAGE_ERROR`，不宣称已删除。
- `LiepinAuthState.storage` 为 `local_file`；额外返回 `storage_path`（不含密钥）与 `saved`（本地保存项是否已确认存在），使读取失败/删除失败时仍可进行删除。读取错误不会伪装成未配置成功；不跟随符号链接、不自动降低文件权限检查。用户真实 Token 不参与自动清理验收。

**settings.liepinResume**

- 入参：`{meta}`。
- 返回：`{meta, status: "pass" | "blocked", code, message, resume_text, auth}`。
- 成功返回真实 `data.result` 文本；失败 `resume_text=""`。前端以纯文本临时预览，不写文件、不自动更新个人资料/证据卡；清理、替换或失败时清除预览。

**jobs.searchLiepin**

- 入参：`{meta, keyword: string, page?: integer}`。keyword 非空且最多 200 字符；page 默认 0，限定 0–100，每次仅请求一页。适配器映射 `keyword → jobName`。
- 返回：`{meta, status, code, message, items: JobLeadListItem[], received_count, imported_count, page, auth}`。
- 成功空列表为 `pass/OK`、数量 0；失败为 `blocked`，不得当成空搜索成功。
- 官方响应按简历 `errCode=0/data.result`、搜索 `code=0/data.list` 分别校验。保留真实岗位 ID/type；详情 URL 只接受猎聘 HTTPS 域名，不把摘要升级为完整 JD。
- 归一化后的岗位复用 `job_leads/*.yaml`；按平台+岗位类型+原始 ID 生成稳定文件标识，重复搜索更新来源字段且保留本地状态/收藏/画像关联。该去重仅用于岗位导入，不等于投递幂等已经完成。
- `JobLeadListItem` 新增 `salary`、`location` 原文字段，搜索导入/列表/详情保持一致；缺失或 null 保存为空字符串，界面显示“未提供”，不推算薪资。非字符串且非 null 的上游字段返回 `INVALID_RESPONSE`，整批校验后才写入；重搜更新薪资地区且保留完整 JD、审核和画像绑定。
- `imported_count` 仅计新增记录，重复读取为 0。写入失败返回 `STORAGE_ERROR`；已写入的条数/items 明确返回，重试仍按稳定 ID 去重。
- 可识别错误码：`AUTH_REQUIRED`、`AUTH_INVALID`、`RATE_LIMITED`、`NETWORK_ERROR`、`INVALID_RESPONSE`、`API_ERROR`、`INVALID_INPUT`、`STORAGE_ERROR`、`CREDENTIAL_STORAGE_ERROR`、`INTERNAL_ERROR`。错误只返回固定安全消息，不含上游响应正文、请求头或 Token。

验收分层：HTTP/sidecar/RPC 本地测试验证契约；真实 Tauri 页面的配置→只读验证→搜索→列表与清理动作另验。当前方法不实现附件绑定、真实投递、平台消息或定时任务。

### 6.38 猎聘授权页原生打开（2026-09-28）

- 前端调用无参数 Tauri host command `open_liepin_authorization`，不是 sidecar JSON-RPC。
- Host 固定打开 `https://www.liepin.com/mcp/auth`，地址与官方 CLI `liepin_cli/core/browser.py` 一致；不接受任意 URL、命令或凭据参数。
- 复用系统默认浏览器：macOS `/usr/bin/open`，Windows `rundll32.exe`，Linux `xdg-open`，无需新增插件或依赖；本机验收范围为 macOS。
- 启动失败或非零状态返回固定 `OPEN_AUTHORIZATION_FAILED`，页面显示本地化提示及可复制地址；不返回进程错误原文。成功只代表打开请求交给系统，不代表登录/授权成功。
- 点击入口不读写 Token，不建立网站登录态，不修改浏览器远程调试或安全设置。

### 6.39 原官方岗位补全与审核绑定（P0-017A 首片）

**jobs.fetchLiepinDetail**

- 入参：`{meta, job_lead_id}`；不接受调用方提供 URL、Token、Cookie 或任意请求参数。
- 返回：`{meta, status, code, message, job_lead_id, job_profile_id, jd_text, source_url, source_jd_sha256, jd_status}`。
- 后端按已保存的 `liepin_official` Lead 取得 URL 与原始岗位 ID；匿名读取白名单内公开详情页，拒绝重定向/验证码/登录/下架页面。以 JSON-LD JobPosting 原始 identifier 核实岗位，正文与 DOM 职位介绍交叉校验，不使用 SEO 摘要或从 URL 展示数字猜原始 ID。
- 抓取成功把规范化正文与 SHA256 写回原 Lead，状态为 `full_unreviewed`；同正文的既有审核可保留，正文改变则撤销关联画像旧审核。抓取失败不改旧资料。返回完整文本用于既有审核区；接口成功不等于审核通过。
- 错误为固定安全消息：`INVALID_INPUT`、`NOT_FOUND`、`NETWORK_ERROR`、`JOB_DETAIL_UNAVAILABLE`、`JOB_ID_MISMATCH`、`INVALID_RESPONSE`、`SECURITY_CHALLENGE`、`STORAGE_ERROR`。

**已有方法增量**

- `jobs.generateProfileDraft` 可传 `job_lead_id`；绑定来源时从后端原 Lead 回填身份与来源 URL，不信任模型生成的平台 ID。仍使用已配置模型生成待审核草稿；模型未配置/不可用时返回既有 blocked 结果，不能自动批准。
- `jobs.saveProfileDraft` 可传 `job_lead_id`、`job_profile_id`，已有 draft 也可携带这两个引用；后端核对关联一致性。绑定来源的公司与平台身份来自原 Lead，来源不匹配或试图替换他人画像时拒绝。
- complete 保存仍要求完整 JD、必需字段和 `review.decision=approved`；更新原 Lead 与稳定关联 Profile，不另建 manual Lead。保存 `source_jd_sha256`、`jd_origin`、审核时间，Lead 状态为 `complete_reviewed`。
- `jobs.convertLead` 对已有有效关联返回同一 profile ID；新画像回写原 Lead 关联，官方来源未经审核保持 `saved_incomplete`。
- `jobs.updateProfile` 保留来源、原始岗位身份和审核字段；标题/关键词/描述改变后撤销旧审核并转为 `saved_incomplete`，仅修改 status 不能绕过审核。
- 重新搜索保留正文、关联和审核；官方 URL 跟踪参数不改变职位身份，但协议/主机/路径变动不能冒充同一已审核来源。
- `jobs.listProfiles/items` 及 `jobs.listLeads/items` 增量回读相关来源、关联、正文和 hash 字段；正文属于本地业务数据，不进入脱敏验收摘要。

**候选和投递边界**

- 官方候选须同时满足 Lead/Profile 关联、平台 ID/type、完整正文 hash、active/approved 状态与当前运行画像一致；App 和 CLI 使用同一校验，显式选择无合格项时不回退其他岗位。
- Candidate 与 REVIEW 记录保留平台、原始岗位身份、画像 ID、JD 状态和指纹；这些字段不等于已具备可续跑的批准简历附件快照。
- DeliveryRequest 使用平台路由；现有 `deliver_with_fallback` 名称保留，但只调用一次匹配通道，未知结果不重试、不自动转邮件。Settings 不再宣告自动跨通道降级。
- 官方来源的生成 PDF 路线仍在进入旧浏览器前返回 `official_delivery_contract_unverified`；平台默认简历另走下述显式准备/审批路线。默认简历成功不证明项目生成 PDF 已发送。


### 6.40 从职位页准备平台默认简历审批（2026-09-29）

**run.agent.prepareLiepinDefault**

- 输入仅 `{meta, job_lead_id}`，拒绝调用方提供岗位 URL、平台 ID、简历正文和批准状态。
- 输出 `{meta, status: "ready" | "blocked", code, run_id?, job_profile_id?, reused?}`；不回传简历正文或凭据。
- 后端复用已保存的官方 Lead/Profile，先验证完整 JD 审核、企业/主体排除、历史投递占位，再重读当前公开 JD 和平台简历。此方法无发送操作。
- 默认简历使用文本 SHA256 固定发送前观测；它不是平台锁定版本，也不是项目生成 PDF。保存不可变审批快照、pending 队列与运行记录。未经批准不发送；发送前再次核对简历/JD 指纹并通过稳定岗位键原子占位。
- 同一目标/JD/简历的 pending 快照校验通过时复用原运行，`reused=true`。职位页跳到 `/agent-run?run_id=<明确编号>`，审批页不得以最新队列替换指定运行。
- 未执行匹配/评测时两分数均为 null，显示“未评估”。不会把证据缺失写成 0 分低匹配。
- 失败码：`INVALID_INPUT`、`JOB_REVIEW_REQUIRED`、`EXCLUDED_TARGET`、`ALREADY_ATTEMPTED`、`RESUME_UNAVAILABLE`、`JOB_DETAIL_UNAVAILABLE`、`PREPARATION_UNAVAILABLE`。仅展示本地固定文案。

**结果来源与历史读回**

- `ReviewDeliveryResult` 增加 `receipt_source`、`app_verified`。产品通道的成功分别标记 `app_api` / `app_browser`；只有带 submission_id 的通道确认结果计入 App 自行确认。
- 历史 `website_history` 保留实际成功事实和防重，读回显示 `externally_confirmed/external_observation_confirmed`，`app_verified=false`。未知来源的历史成功显示 `receipt_source_unverified` 并保持阻断，不能自动升级。
- `AgentRunSummary` 区分 `deliveries_completed`（实际成功事实）、`app_verified_deliveries`、`externally_confirmed_deliveries`。含外部观察确认的结束批次标记 `EXTERNAL_CONFIRMATION_ONLY`，不是 App 闭环完成。旧事件及原始记录保留，读取时投影当前语义。
- 开发代理控制招聘网站取得的结果仅作外部观察，不能用作产品 API 回执或 App 闭环验收。


### 6.41 API 回执本地重核（2026-09-29）

- `run.agent.recheckReceipt({meta, run_id, job_lead_id})` 只接受现有运行/候选身份，禁止响应正文或成功结论入参。返回 `{meta, status, code, delivery_results?}`。未知候选的发送尝试 ID 现在始终保留。
- App 仅从该次提交的 `api_receipt.json` 加载受保护业务字段（目录 0700、文件 0600、归属当前用户）。普通日志保存 SHA256、解析版本和原因，凭据及未知字段不进入回执证据。
- 重核校验文件 hash、原 HTTP 响应指纹、run/candidate/job ID/type、已批准简历 SHA256 和持久化 attempt；不执行网络请求。新解析器明确确认时原子同步实际结果，成功/失败仍占据防重；原始 unknown 事件保留，重核事件追加。重复点击不发请求、不重复计数。
- 旧日志缺少原响应证据或文件被改动：`blocked/RECEIPT_EVIDENCE_UNAVAILABLE`。仅外部网站观察不进入本入口。原始数据仍无法判定时保留 unknown；不会把外层 errCode=0 当成功。
- 审批结果的未知条目提供“核验已有回执”，明确只读取本机响应、不会重新投递。按钮不要求用户再次配置 Token。


投递追踪增量：API 记录沿 `input_artifacts` 保存岗位公司/职位、审批运行、Lead 与简历版本引用；`submission.list/detail` 回读这些业务字段，详情提供返回原审批的入口。API 记录 `retry_allowed=false`，旧 `submission.retry` 明确拒绝 API 尝试且不改原状态；未知只允许本地回执重核。检查历史记录沿用旧行为。

岗位手工审核增量：Jobs 的“手动整理画像”仅创建前端待审核表单，复用原 `jobs.saveProfileDraft`。来源绑定仍由后端校验，摘要、必备要求和关键词必须完整；没有调用模型，不伪造模型成功。


### 6.42 十岗测试批次额度与旧回执引用

- `run.agent.get` 增加 `delivery_batch: {batch_id, authorized_max, consumed, confirmed, remaining, unresolved} | null`。该信息跨运行，不等于当前运行的 App 验收数。当前用户授权批次 `validation_10_20260928` 最大 10，历史两笔一并纳入；已占用 10 后停止新增真实发送。
- SQLite 授权配置不可因重复调用改变上限或重置占用；所有 `deliver_once` 渠道共用原子预占。未知暂停当前批次，明确未发送释放该次占位；已发成功/失败仍保留防重。到达上限返回 `delivery_batch_limit_reached`，不得变为新批次续投。
- 准备阶段先返回 `BATCH_LIMIT_REACHED` / `BATCH_UNRESOLVED`，不读取凭据；发送时仍独立检查，防止并发准备突破名额。
- `run.agent.recheckReceipt` 可为旧 API 日志寻找 App 已接收的、完整响应 SHA256 完全相同且文件校验通过的业务响应。必须校验旧快照/尝试绑定；借用文件以 `api_receipt_reference` 留痕并保留 `prior_receipt_source`，不创建伪造的旧响应。找不到精确证据保持原结果，自身文件损坏不得借引用绕过。
- 此能力改变回执核验来源，不增加或释放真实尝试额度，不把外部网页观察本身当作 API 回执。

### P0-018 每日持续授权

- `daily.status` 返回 `authorization`、`candidates`（仅真实已准备且尚未上传/发送的猎聘 PDF）、上海自然日 `today`（confirmed/occupied/remaining/unresolved）及最近 14 个日期的 `history`。只展示源文件路径和指纹，不复制正文或凭据。
- `daily.save(run_ids, maximum, time, expires_at)` 保存草稿；`run_ids` 最多 30 项，身份和 SHA256 全部从既有快照取得；maximum 为 1–3 整数、time 为上海 HH:mm、expires_at 必须带时区且晚于当前时间。保存不启用。启用后范围不可改，只能撤销后另建。
- 本地主窗口命令 `change_daily_authorization(id,state,confirmed)` 调用内部 `daily.change`，支持 active/paused/revoked；active 要求 confirmed=true、非空清单、文件身份重新核验及有效期限。暂停/撤销同时给当前原生文档写入批次取消标志，不撤回已经发出的请求。过期状态由当前时间计算，不可通过恢复绕过。
- 固定本地主窗口命令 `run_daily_delivery(force)`：false 为 App 每分钟检查，true 为今日手动触发；二者共用 `daily.claim` 日期唯一键。领取后 Rust 顺序复用会话、附件要求、上传、字节绑定、目标/会话、确认及回执核验；每个写步骤再次核对 `daily.check` 和快照中的 daily_cycle。未知即停止，执行结束 `daily.finish` 保存短缺原因并保留未决占位。
- `close_interrupted_daily(id)` 仅原生执行锁空闲时关闭中断批次，不重复任何平台请求；在途尝试转 unknown，仍须沿原回执入口核验。成功数量只读 SQLite 业务结果，不采信前端声明。内部 claim/check/finish 的时间使用服务器 UTC/上海换算，没有生产测试时钟参数。
- 所有原生招聘会话命令和每日整批共用执行互斥；暂停/撤销 RPC 不争用该锁，因此运行中仍可生效。原测试批次保持原计数，新每日批次独立绑定于授权；首次持续授权启用后，所有受控 reserve 共享每日三次总上限和未决阻断。
- `daily.permit(run_id)` 是内部最终写许可：读取快照及已有占位，验证上海日界（含旧单笔入口），返回当日日界与授权到期中较早的 `write_deadline_ms` 和 daily_cycle。Rust 在导航等待后重新读取；页面点击及网络写入检查截止与取消标志。观察完成后门禁保持关闭直到原生重载销毁旧文档，不给延迟 POST 留出恢复旧发送函数的窗口。官方默认简历路线也在只读前置完成后、最终 POST 前复核占位日界。
- `daily.preview(run_id)` 只返回该运行已核验快照的 `pdf_base64` 与 `pdf_sha256`，不接受路径；前端再次比对清单指纹并以内嵌 PDF 显示，不依赖未启用的 asset 协议，也不把文件字节写入普通日志。

### 工作文档选择与简历质量

- `evidence.listMaterialDocuments(material_id,query?)` 从库内 TXT/Markdown 恢复 `# Source:` 边界并有界分段，返回 total/matched/items（最多60）。条目含 document_id、label、source_name、sha256、char_count；不读取原文中引用的路径。
- `evidence.readMaterialDocument(material_id,document_id)` 只返回服务器重新解析得到的同一文档片段原文与指纹。未知、已变化的标识返回 material_document_changed_or_missing。
- `evidence.generateDraft` 复用原参数并增加可选 source_document_id；目录/长材料要求明确选择，否则 material_document_selection_required。草稿增加 source_documents 单项引用（material_id/document_id/sha256/label），仍 candidate_pool_eligible=false；沿既有审核保存，不自动批准模型内容。
- `evidence.saveDraft` 增量重验 source_documents 原文和指纹，results 只能引用所选文档；保存 source_documents_json 作为证据卡来源元数据。旧未指定片段的人工材料稿继续按原材料审核契约处理。
- `run.quick.start` 的 resume_readiness 增加 missing_evidence_fields；缺少 context/role_scope/time_range/actions 或全部技能为空时保持 NEEDS_EVIDENCE，quality_passed=false。reasons 使用中文可读字段缺口，候选人正文不写内部 ID 或待补提示。
- `evidence.list` 增加真实 candidate_pool_eligible，旧 ready/pass 标记不再作为可进入生成池的依据。`evidence.get` 返回 source_documents。普通 update 保留来源/审核元信息，事实变更降为 needs_review/pending/eligible=false；仍按原片段校验结果。重新审核可在 saveDraft 传 evidence_id，但必须是存在卡且 source_material_ids/source_documents 与原卡一致，保留 created_at 和扩展来源字段；非法 ID、目标缺失、换源分别拒绝。前端重审目标独立固定，切卡清空且加载中不可保存。
- 慢模型提炼与渲染请求通过 Tauri 已有线程池发送，沿用原 SidecarManager 的完整请求互斥，不在主窗口事件线程阻塞；不会把串行协议改成并发读写。

### 完整职业档案与原投递审批的内容检查

- `profile.get` 保留原五字段及基础 completeness，新增 career、revision、career_status（reviewed/ready/missing/reviewed_at）。career 保存于原 personal_profile.yaml 的 career_json，不创建第二资料库；草稿与未知扩展字段均保留。
- `profile.update(patch,expected_revision)` 的 patch 新增 career；所有资料保存均须传表单加载时的 revision，陈旧表单返回 profile_changed。career schema_version=1，含 summary、work、skills、education_visibility（show/omit）、education、extras。工作/教育记录年月 YYYY-MM、current=true 时 end 为空；顺序错误拒绝。记录 ID 稳定，证据引用限定既有 ID，不接受路径。
- `profile.review(expected_revision,confirmed)` 在完整基础资料、工作/能力和教育（或明确 omit）及所有证据有效时确认职业档案；未明确确认/不完整/版本变化拒绝。确认指纹覆盖档案内容与关联证据，后续修改失效。保存草稿不确认事实、不启用投递。
- `material.readiness` 使用原接口增加 missing_career_profile；上传现成简历改为可选，不再发出 missing_uploaded_resume 阻断。资料就绪不表示某份生成简历已被批准。
- Quick Run 的 trace 增加 content_schema_version/career_revision；readiness 增加 missing_career_fields/content_ready，导出记录 artifacts.resume_pdf_sha256、resume_pdf_source_sha256、resume_pdf_trace_sha256，并核对导出过程中源文件未变。所选证据 trace 输入指纹必须匹配职业档案确认时的原卡版本；项目时间区间必须可解析、顺序正确且在关联任期内。完整职业档案与项目关联校验通过仍为 NEEDS_REVIEW，最终按目标审核；旧稿须重新生成，不沿用 DONE 或高分推断内容完整。
- `run.agent.prepareLiepinPdf` 复用原准备入口，新增完整内容校验；批准依据 content_basis 绑定 Markdown/PDF/trace/职业档案/岗位，进入原 ReviewSnapshotStore 候选身份。既有批准上传将 content_review 写入原队列（明确确认及 basis），不新增审核存储或页面。上传、沟通前、最终发送、daily 清单均复核，未批准/源变化/内容不完整拒绝。
- 复用 `daily.preview` 的既有快照 PDF 字节读取供投递页预览；预览是只读，历史成功不受当前档案变化影响。默认平台简历准备和最终 API POST 前核对确认档案与已批准正文覆盖，返回 CAREER_PROFILE_UNCONFIRMED/RESUME_CONTENT_INCOMPLETE 或对应明确阻断码。旧回执校验保持原契约。

### App 页面接续（2026-10-08，无新增 RPC）

- `/quick-run?job_profile_id=<id>` 只选择该已保存且 active、有 source_jd 的画像；不可用时显示目标错误且禁止启动，不回退他项。复用 profile.get.career_status.ready；确认缺失时显示原简历中心入口。
- QuickRunStartResult 显式消费既有 resume_readiness.content_ready、missing_profile_fields、missing_target_fields、missing_evidence_fields、missing_career_fields 与 traceability.resume_traceable。只有 DONE + content_ready + resume_traceable + resume_pdf 才展示下一步准备入口；它仍不等于后端批准或授权。
- `/submissions?quick_run_id=<id>` 仅预填合法编号。用户点击后才调用既有 run.agent.prepareLiepinPdf；前往 `/agent-run` 仅查看原候选清单。页面加载及查询参数不作为外部写权限。

- `run.agent.getPendingReview` 从原队列新增可选 `native_pdf_quick_run_id`。非空时 Agent Run 只显示原 PDF 审核入口；`run.agent.submitReview` 对具有 quick_run_id 的队列返回 `native_pdf_review_required`，不写决定、不执行通用投递。

### 每日批次进度与中断核验（2026-10-08）

- `daily.status.history[]` 复用原批次，增加 maximum、confirmed、unresolved、started_at、finished_at、items；items 只含 run_id、company、position、phase、quick_run_id、recovery_required，引用不可读时为 record_unavailable，不返回平台响应原文。
- 阶段为 not_started / uploading / binding_pending / attachment_verified / delivery_in_progress / awaiting_receipt / upload_unconfirmed / receipt_unknown / success / failed / record_unavailable。成功数以原 SQLite 业务结果为准，状态读回不升级成功。
- `daily.finish` 保留原请求，结束批次时协调原队列与尝试：上传 in_flight 转 unknown，在途投递占位转 unknown；成功和未开始项不变，保存 daily_interruption 作为原队列停止依据。重复结束已关闭批次拒绝；下次 claim 或恢复遇到未处理停止项返回 daily_recovery_required，禁止自动重试。
- 原 PDF 返回对象增加 recovery_only；为 true 时只支持原有只读检查/回执核验，can_confirm_send=false。每日历史入口只导航 `/submissions?quick_run_id=<id>`，不自动调用核验、上传或发送。

- `daily.status` 同时返回原队列投影的 recovery_required/recovery_items，覆盖旧授权与历史窗口外尚未核验的上传/中断项。启用和 claim 均全局检查，撤销或换清单不解除未决；已确认成功/明确失败的原尝试排除。此为原队列只读投影，不新增恢复存储。

- `run.agent.get` 对具有 daily_cycle 的原队列返回 delivery_batch=null，每日计数统一取所属 daily 历史，不借用当前手动验证批次的计数；普通手动运行不变。

### JD 提取可靠性（2026-10-08）

PDF 名称增量（2026-10-14 修正）：生成简历向目录导出和 Quick Run 自动导出返回 `姓名-公司全称-岗位全称-YYYYMMDD.序号.PDF` 的本地路径；仅按文件系统安全限制处理，不套用平台24字符限制。来源匿名描述原样保留，不猜雇主实名。本地名与平台附件名在原文件锁保护的命名记录中分别保持同版本稳定、名称冲突递增；旧记录不迁移。原 PDF 准备 RPC 与 DailyCandidate 的 `pdf_filename` 继续为上传短名，绑定原快照；旧快照无此字段保持兼容。平台短名采用原公司/岗位简称规则适配24字符上限，仍超限在 beginPdfUpload 或启用每日授权前返回 `daily_pdf_filename_too_long`，不改变批准状态或写入上传占位。`.PDF` 与 `.pdf` 仅扩展名兼容，主体名称、字节和平台身份仍严格检查。

原生附件检查继续返回原 attachment_view；在官方简历编辑页上，仅关闭已核实的唯一经历同步提示 Close 控件后读取附件入口。延迟回调重验页面边界，不在解析表单页操作或确认同步，不新增 RPC。

公开 JobPosting 的“职位描述”可作为已核实职责章节别名，其他身份与正文校验不变。原 jobs.generateProfileDraft 使用有界 schema（字符串和数组上限），本机 LM Studio 请求 max_tokens=1800；预算截断拒绝成稿，字段超限即使供应方忽略 schema 也拒绝。原 JD 与 source_url 由 App 保存，绑定官方线索时 target_role/company 取原线索。手工保存入口和既有审核要求不变。

2026-10-12 原生PDF准备/核验返回可选 `verification_error`；非空时界面显示未核验提示。无旧附件列表回执的新页面，必须当前附件与上传回执一致且实际下载字节SHA256/大小精确匹配，不能按上传成功直接发送。

2026-10-12 `run.agent.authorizeSinglePdfDelivery(run_id, confirmed:true)` 只为已批准且已核验附件的单个候选登记1次独立补充授权，返回 `single_delivery_authorized`；范围由服务端快照与岗位键绑定，旧批次已耗尽且无未决方可登记，重放不增加额度，其他岗位/运行/PDF不得消费。

### 引用式材料（2026-10-17）

材料可"引用"允许来源根内的外部文件/目录，不复制原件；清单冻结（逐文件 sha256），内容变更/删除使读取与校验统一报 `material_source_changed`，需刷新或重审；新增文件需刷新才纳入。

- `material.reference.scan(root_id, relpath)`：扫描预览（file_count/total_bytes/sample_files≤20/skipped/existing_materials）。来源根未配置报 `material_source_root_required`；无可用文件报 `material_source_empty`。安全规则：目标必须位于允许根内、拒绝符号链接穿越、只收 .md/.txt、跳过隐藏路径与敏感名（secret/token/密码等）及空文件。
- `material.reference.create(root_id, relpath, label)`：创建引用材料（meta 含 source_mode/source_root/source_relpath/manifest_sha256/file_count；清单与合并缓存存 `materials/.referenced/`）。
- `material.reference.status(material_id)`：重扫源 → `ok|changed`（changed/missing/added 摘要）。
- `material.reference.refresh(material_id, confirmed:true)`：重建清单与缓存；已绑定卡片因指纹失配进入"来源已变更，需重审"。
- `material.reference.remove(material_id, confirmed:true)`：仅删除本机 meta/清单/缓存，不触碰来源目录。
- `settings.get` 新增 `material_source_roots`；`settings.update` 新增 `section=material_source_roots`（payload 为 `[{id?,label,path}]`，路径必须为已存在目录，服务端按解析路径去重）。
- 材料列表项新增 `source_mode/source_root/source_relpath/manifest_sha256/file_count`；证据草稿、生成与职业档案校验在读取引用材料前重验清单与源文件哈希。
