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

`result.items[]`

```json
{
  "job_profile_id": "jp_001",
  "title": "Senior Backend Engineer",
  "status": "active",
  "match_score": 82,
  "evidence_count": 5,
  "resume_count": 2,
  "updated_at": "2026-03-07T10:00:00Z"
}
```

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
    "gate_mode": "strict"
  },
  "exclusion_list": [],
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
  "section": "llm_config",
  "payload": {
    "provider": "openai",
    "model": "gpt-5",
    "api_key": {
      "action": "replace",
      "value": "secret-value"
    }
  }
}
```

规则：

- `section`: `gate_policy | exclusion_list | channels | llm_config`
- 对于 secret 字段，仅允许：
  - `{ "action": "replace", "value": "<secret>" }`
  - `{ "action": "clear" }`
- `settings.get` 永不返回 secret 明文

`result`

```json
{
  "meta": { "correlation_id": "corr_001" },
  "section": "llm_config",
  "saved": true
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
