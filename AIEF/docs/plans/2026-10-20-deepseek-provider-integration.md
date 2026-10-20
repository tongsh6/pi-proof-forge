# DeepSeek Provider 接入设计与实施计划

> 设计日期：2026-10-20 ｜ 状态：用户已确认 ｜ 范围：系统设置 LLM Config + LLMClient 请求适配
>
> 目标：让 App 在系统设置内完成 DeepSeek 的 provider 选择、密钥保存/清除、连接检查与模型发现，并让 Quick Run、证据推断、语义匹配等现有入口直接使用 DeepSeek；不新增第二套模型调用框架。

## 1. 现状与复用

| 需要 | 现状 | 处理 |
| --- | --- | --- |
| Provider 选择 | `ui/src/pages/system-settings/index.tsx` 已有 `lm_studio` / `openai` / `openai_compatible` 预设 | 增加 `deepseek` 预设 |
| 请求协议 | DeepSeek 提供 OpenAI 兼容协议，现有 `LLMClient` 已统一 `chat/completions` 与 `/models` | 复用，仅增加 DeepSeek thinking 适配 |
| 连接检查 | `settings.checkLlmConnection` 已能读取 `/models`，但文案固定为 LM Studio | 改为 provider-aware，缺密钥时明确 blocked |
| 凭据存储 | 猎聘 Token 已有本机 0600 权限文件；LLM API Key 只记录“已配置”，实际只读环境变量 | 复用安全文件能力，按 provider 保存 |
| 思考模式 | 无 | 新增布尔开关，默认关闭；仅 DeepSeek 生效 |
| 管线传递 | sidecar 通过 `LLM_PROVIDER` / `LLM_MODEL` / `LLM_BASE_URL` / `LLM_API_KEY` 注入子进程 | 增加 `LLM_THINKING` |

关键结论：DeepSeek 不需要新的 SDK 或第二套客户端；缺口是 provider 预设、密钥持久化、页面状态和 thinking 参数。

## 2. 架构与数据流

```
System Settings UI
  ├─ 选择 provider=deepseek → 默认 base_url=https://api.deepseek.com, model=deepseek-flash
  ├─ 检查连接 → settings.checkLlmConnection → GET /models（使用已保存或本次输入的 key）
  ├─ 保存 → settings.update(llm_config) → policy.local.yaml + credentials/llm-deepseek-api-key
  └─ 清除 → settings.clearLlmApiKey → 删除对应凭据文件
                         │
sidecar / pipeline ──────┴─→ _load_llm_config()
                              ├─ 文件（saved）→ 环境变量（environment）→ lm-studio 占位（legacy）
                              └─ LLMClient(provider, thinking_enabled)
                                    └─ DeepSeek: thinking.enabled/disabled + reasoning_effort=low|high|max
```

## 3. 契约变更

### 3.1 `settings.get.llm_config`

新增：

```json
{
  "thinking_enabled": false,
  "thinking_effort": "high",
  "api_key": {
    "configured": true,
    "masked": true,
    "updated_at": "2026-10-20T10:00:00Z",
    "source": "saved"
  },
  "configured_providers": ["deepseek", "lm_studio"]
}
```

- `source`: `saved | environment | legacy | none`
- `configured_providers`: 已有本机凭据文件的 provider；`lm_studio` 占位密钥不计入
- 永不返回密钥明文

### 3.2 `settings.update`（section=`llm_config`）

- 支持字段增加 `thinking_enabled`（布尔）与 `thinking_effort`（`low|high|max`，默认 `high`）
- `api_key` 写入当前/传入 provider 的凭据文件；provider 必须匹配 `^[a-z][a-z0-9_]{0,31}$`
- `lm_studio` + `api_key="lm-studio"` 保持占位语义，不强制写文件
- 其他 provider 的 key 不进入 `policy.local.yaml`

### 3.3 新 RPC `settings.clearLlmApiKey`

```json
{ "meta": { "correlation_id": "corr_001" }, "provider": "deepseek" }
```

返回 `{meta, provider, cleared, configured_providers}`；删除失败返回固定错误，不泄露路径。

### 3.4 `settings.checkLlmConnection`

- 缺少在线 provider 密钥时返回 `status=blocked`、`code=BLOCKED_PROVIDER_CREDENTIAL`
- 消息使用 provider 名称，不再固定 LM Studio
- `models` 仍来自 `/models`，只证明端点与凭证可读，不代表推理质量

### 3.5 `LLMClient`

```python
LLMClient(base_url, api_key, timeout=120, *, provider="", thinking_enabled=None)
```

- `provider` 为空时回退 `LLM_PROVIDER` 环境变量
- `thinking_enabled` 为 None 时回退 `LLM_THINKING=on/off`，默认 `off`
- `reasoning_effort` 默认 `high`，可传 `low|high|max`，并回退 `LLM_THINKING_EFFORT`
- `provider=deepseek` 且 payload 未显式带 `thinking` 时：
  - 关闭：`{"thinking": {"type": "disabled"}}`
  - 开启：`{"thinking": {"type": "enabled"}, "reasoning_effort": "low|high|max"}`
- 不修改其他 provider 的请求

## 4. 安全设计

- 凭据根目录：`~/Library/Application Support/PiProofForge/credentials`（0700）
- 文件：`llm-<provider>-api-key`（0600），原子替换，拒绝符号链接与不安全权限
- 复用现有 `LocalCredentialFile` 的逐级目录校验；不新增依赖
- 测试通过 `PPF_CREDENTIAL_DIR` + autouse fixture 隔离，绝不读写用户真实凭据
- 错误只返回固定文案，不包含密钥、路径或底层异常

## 5. 页面行为

- Provider 下拉新增 DeepSeek
- 选择 DeepSeek 自动填充 `https://api.deepseek.com` / `deepseek-flash`
- 显示当前 provider 的密钥状态：已保存 / 来自环境变量 / LM Studio 占位 / 未配置
- “清除密钥”仅对已有本机凭据文件的 provider 显示，带确认
- DeepSeek 显示“思考模式”开关与说明；其他 provider 不显示
- 切换 provider 时清空连接检查结果和模型列表
- 保存后重新读取设置，密钥输入框清空

## 6. TDD 实施任务

### Task 1：通用本地凭据文件

**Files**
- Modify: `tools/infra/liepin_token_file.py`
- Test: `tests/unit/infra/test_liepin_token_file.py`

**Steps**
1. 先加失败测试：`LocalCredentialFile(path)` 写入任意文件名后权限为 0600、临时文件名以目标文件名开头、`LiepinTokenFile` 行为不变。
2. `python3 -m pytest tests/unit/infra/test_liepin_token_file.py -q` → 失败（类不存在）。
3. 抽取 `LocalCredentialFile`，保留 `LiepinTokenFile` 子类与默认猎聘路径；临时文件改为 `.{path.name}.{hex}.tmp`。
4. 同命令 → 通过；再跑 `test_liepin_credential_persistence.py`。

### Task 2：按 provider 的 LLM 密钥仓库

**Files**
- Create: `tools/infra/llm_credentials.py`
- Test: `tests/unit/infra/test_llm_credentials.py`
- Modify: `tests/conftest.py`

**Steps**
1. 写失败测试：保存/读取/删除；provider 名非法被拒绝；两个 provider 互不影响；`configured_providers()` 列出已保存项；文件权限 0600；符号链接被拒绝。
2. 运行 → 失败（模块不存在）。
3. 实现 `LLMApiKeyStore`：`path_for/load/save/delete/status/configured_providers`，根目录支持 `PPF_CREDENTIAL_DIR`。
4. 在 `tests/conftest.py` 增加 autouse fixture，把默认凭据根指向临时目录并清空 `LLM_API_KEY`/`LLM_THINKING`。
5. 运行通过。

### Task 3：settings 读取、保存、清除与连接检查

**Files**
- Modify: `tools/sidecar/handlers/settings.py`
- Modify: `tools/sidecar/server.py`
- Test: `tests/unit/sidecar/test_settings_handler.py`
- Test: `tests/unit/sidecar/test_agent_handler.py`

**Steps**
1. 先写失败测试：
   - 保存 `deepseek` key 后 `settings.get` 显示 `configured=true`、`source=saved`、`configured_providers=["deepseek"]`，响应与 policy 文件都不含明文。
   - 切换 provider 后各自密钥状态独立。
   - `settings.clearLlmApiKey` 删除后 `configured=false`。
   - 缺 DeepSeek key 时连接检查返回 `BLOCKED_PROVIDER_CREDENTIAL`。
   - legacy `llm_api_key_configured` + `lm-studio` 仍兼容。
2. 运行 → 失败。
3. 实现 `_load_llm_config` 的密钥解析、`_save_llm_config` 的凭据写入、`handle_settings_clear_llm_api_key`、provider-aware 连接检查。
4. 注册 RPC；运行通过。

### Task 4：LLMClient DeepSeek 适配

**Files**
- Modify: `tools/infra/llm/client.py`
- Test: `tests/unit/infra/test_llm_client.py`

**Steps**
1. 先写失败测试：
   - `provider="deepseek"` + 默认 → payload 含 `thinking.disabled`。
   - `thinking_enabled=True` → `thinking.enabled` + 所选 `reasoning_effort`。
   - 显式 `thinking` / `reasoning_effort` 不被覆盖。
   - 其他 provider 不受影响。
   - `provider` 空时读取 `LLM_PROVIDER`，`thinking_enabled=None` 时读取 `LLM_THINKING`；`reasoning_effort=None` 时读取 `LLM_THINKING_EFFORT`。
2. 运行 → 失败。
3. 实现最小注入逻辑；不改变 LM Studio 分支。
4. 运行通过。

### Task 5：运行时传递 provider/thinking

**Files**
- Modify: `tools/sidecar/handlers/agent.py`
- Modify: `tools/sidecar/handlers/evidence.py`
- Modify: `tools/sidecar/handlers/jobs.py`
- Modify: `tools/sidecar/handlers/job_preferences.py`
- Test: `tests/unit/sidecar/test_agent_handler.py`

**Steps**
1. 先写失败测试：`_persisted_llm_runtime_context()` 返回 `thinking_enabled` / `thinking_effort` 并设置 `LLM_THINKING=on/off`、`LLM_THINKING_EFFORT`。
2. 运行 → 失败。
3. 在 summary/env 中传递；4 处直接构造 `LLMClient` 的 handler 传入 `thinking_enabled` / `reasoning_effort`。
4. 运行通过。

### Task 6：页面与 i18n

**Files**
- Modify: `ui/src/pages/system-settings/index.tsx`
- Modify: `ui/src/lib/sidecar/api.ts`
- Modify: `ui/src/lib/sidecar/types.ts`
- Modify: `ui/src/i18n/zh.json`
- Modify: `ui/src/i18n/en.json`
- Test: `tests/unit/gui/test_system_settings_page_contract.py`

**Steps**
1. 先写失败契约测试：DeepSeek 选项、默认 URL/模型、`thinking_enabled`、`thinking_effort`、`clearLlmApiKey`、按 provider 密钥状态、切换时清空检测结果。
2. 运行 → 失败。
3. 实现 UI 与 API/类型；补齐中英文文案。
4. `tsc --noEmit` 与 GUI 契约测试通过。

### Task 7：文档与契约

**Files**
- Modify: `ui/design/contracts/sidecar-rpc.md`
- Modify: `ui/design/DESIGN.md`
- Modify: `docs/execution-roadmap.md`
- Modify: `docs/project-ledger.md`
- Modify: OpenSpec `openspec/changes/deepseek-provider-integration/*`

**Steps**
1. 按实际实现更新契约与设计说明。
2. `.pen` 画布已更新 System Settings 的 DeepSeek 预设、密钥状态/清除、思考开关与 low/high/max 强度选择；截图核对无裁切。Pencil 无保存 API，磁盘文件需在编辑器中 Cmd+S 落盘。

### Task 8：回归与真实 App 验收

1. 相关测试 → 全量 `python3 -m pytest -q`
2. `cd ui && npx tsc --noEmit`（使用本机已有依赖，不安装）
3. 项目门禁（roadmap / v2 架构 / AIEF / diff）
4. 用户在真实 App：选择 DeepSeek → 填 key → 检查连接 → 保存 → 切换思考模式 → 运行一次实际模型任务
5. 台账记录：真实页面观察、调用结果、未完成项；不把页面跑通等同于 DeepSeek 全链路深度验收

## 7. 验收标准

- 页面可完成 DeepSeek 配置，保存后重启仍显示已配置。
- 连接检查能列出 DeepSeek 模型；错误信息可读且不含密钥。
- Quick Run / 证据推断等入口在 DeepSeek 下真实返回结果。
- 思考模式开关确实改变请求参数（用测试与本机日志/假服务验证），默认关闭。
- 其他 provider、既有 LM Studio 路径、投递与 P0-026 不受影响。

## 8. 风险与边界

- DeepSeek JSON 模式偶发空正文：沿用现有阶段纠错；若实测频繁，另立切片，不在本变更内加通用重试。
- `thinking` 参数仅 DeepSeek 支持，不能注入其他 provider。
- 真实 App 验收需要用户提供自己的 DeepSeek API Key；不接受把密钥写入仓库或日志。
- 本变更不改变 P0-026 唯一 `next`，不新增平台写入。
