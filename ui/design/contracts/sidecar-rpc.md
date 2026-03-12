# PiProofForge Sidecar RPC Contract

> 状态：active
> 用途：冻结 Tauri host / React frontend / Python sidecar 之间的字段级 JSON-RPC contract，避免 UI 与 sidecar 并行开发时发生漂移。
> 裁决关系：若本文件与 `ui/design/DESIGN.md` 的 JSON-RPC 摘要冲突，以本文件为准；若与更高层产品约束冲突，以 `ui/design/DESIGN.md` 与 `AIEF/context/tech/GUI_ARCHITECTURE.md` 回收修正。

## 1. 总则

- 传输模型固定为 `JSON-RPC 2.0 over stdio`
- request / response 使用 `id` 做单次配对
- 跨 request / response / event / log 的动作关联统一使用 `meta.correlation_id`
- 所有 `id`、`run_id`、`evidence_id`、`submission_id`、`resume_id`、`job_profile_id`、`job_lead_id` 均为字符串
- 时间字段统一使用 ISO-8601 UTC string，例如 `2026-03-07T10:00:00Z`

## 2. Envelope

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
  "status": "queued"
}
```

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
    "max_rounds": 5
  }
}
```

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
  "status": "done",
  "submitted_at": "2026-03-07T10:00:00Z"
}
```

### 6.18 submission.retry

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

### 6.19 settings.get

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
    "provider": "openai",
    "model": "gpt-5",
    "base_url": null,
    "api_key": {
      "configured": true,
      "masked": true,
      "updated_at": "2026-03-07T10:00:00Z"
    },
    "timeout": 60,
    "temperature": 0.2
  }
}
```

### 6.20 settings.update

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

- `section`: `gate_policy | exclusion_list | excluded_legal_entities`
- `gate_policy` payload 当前支持更新字段：`delivery_mode`、`batch_review`；为部分更新，未传字段保持原值
- `delivery_mode` 枚举：`auto | manual`；`batch_review` 为布尔值，仅 `delivery_mode=manual` 时生效
- `channels` 与 `llm_config` 当前为 `settings.get` 只读返回字段，不支持 `settings.update`
- `settings.get` 永不返回 secret 明文

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "section": "gate_policy",
  "saved": true
}
```

### 6.21 evidence.create

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

### 6.22 evidence.update

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

### 6.23 evidence.delete

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

### 6.24 overview.get

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

### 6.25 resume.upload

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

### 6.26 resume.getPreview

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

### 6.27 profile.get

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

### 6.28 profile.update

用途：保存用户个人资料编辑结果，对应 Resumes 页面 "Edit Info / 编辑资料" 操作提交。

`params`

```json
{
  "meta": { "correlation_id": "corr_001" },
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

### 6.29 jobs.createProfile

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

### 6.30 jobs.updateProfile

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

### 6.31 jobs.deleteProfile

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

- secret 必须由 sidecar 写入 OS credential store，不得进入前端持久化 state
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

### 6.15 run.agent.getPendingReview

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

### 6.16 run.agent.submitReview

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

### 6.17 run.agent.createReviewCandidates

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
