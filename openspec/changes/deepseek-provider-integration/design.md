# Design: deepseek-provider-integration

## 1. 总体思路

DeepSeek 使用 OpenAI 兼容协议，现有 `LLMClient`、`/chat/completions`、`/models` 与设置页表单都可以复用。真正缺的是四件事：

1. provider 元数据（默认地址、默认模型、显示名）；
2. 能真正生效的按 provider 凭据存储；
3. DeepSeek thinking 参数的请求适配；
4. 页面上的密钥状态、清除入口与思考开关。

不新增 SDK、不新增 HTTP 客户端、不新建模型调用框架。

```
System Settings
  provider=deepseek → base_url/model 预设
  api_key → credentials/llm-deepseek-api-key (0600)
  thinking → policy.local.yaml
        │
        ▼
settings.get / checkLlmConnection / update / clearLlmApiKey
        │
        ▼
_load_llm_config() → LLMClient(provider, thinking_enabled)
        │
        ├─ Quick Run / Agent Run（子进程 env）
        └─ Evidence / Jobs / Job Preferences（in-process）
```

## 2. 现有能力与复用

| 需要 | 现状 | 处理 |
| --- | --- | --- |
| OpenAI 兼容调用 | `tools/infra/llm/client.py` 唯一 HTTP 入口 | 复用，增加 DeepSeek 分支 |
| 模型列表 | `LLMClient.list_models()` + `settings.checkLlmConnection` | 复用，文案 provider-aware |
| 本机凭据文件 | `LiepinTokenFile` 已有逐级目录校验、0600、原子替换、拒绝符号链接 | 抽取 `LocalCredentialFile`，猎聘保持兼容 |
| 设置页表单 | `LLM_PROVIDER_DEFAULTS`、检测模型、连接测试 | 扩展 DeepSeek 预设与状态 |
| 管线配置注入 | `agent.py` 已注入 `LLM_PROVIDER/MODEL/BASE_URL/API_KEY/TIMEOUT` | 增加 `LLM_THINKING` |
| 现有 provider | LM Studio 的 JSON schema 与 reasoning 适配 | 保持原分支不变 |

## 3. 凭据存储

- 根目录：`~/Library/Application Support/PiProofForge/credentials`，可用 `PPF_CREDENTIAL_DIR` 覆盖（测试隔离）。
- 文件名：`llm-<provider>-api-key`。
- provider 校验：`^[a-z][a-z0-9_]{0,31}$`，非法值拒绝保存与读取。
- 复用 `LocalCredentialFile`：0700 目录、0600 文件、逐级 `O_NOFOLLOW`、原子 `os.replace`。
- `lm_studio` 的 `lm-studio` 视为占位密钥，不要求写文件；用户自定义 LM Studio key 仍可保存。
- 不回读明文；`settings.get` 只返回 `configured/masked/updated_at/source`。

### 密钥优先级

```
本机 provider 凭据文件（saved）
  > 环境变量 LLM_API_KEY（environment）
  > lm_studio 占位（legacy）
  > 无（none）
```

旧 policy 中的 `llm_api_key_configured` / `llm_api_key_placeholder` 只作为 LM Studio 兼容回退；在线 provider 没有真实密钥时不再宣称可用。

## 4. 请求适配

```python
LLMClient(base_url, api_key, timeout=120, *, provider="", thinking_enabled=None)
```

- `provider` 为空时读取 `LLM_PROVIDER`；`thinking_enabled=None` 时读取 `LLM_THINKING`（默认 off）。
- 仅 `provider=deepseek`：
  - 未显式传 `thinking` 时，关闭：`{"thinking": {"type": "disabled"}}`
  - 开启：`{"thinking": {"type": "enabled"}, "reasoning_effort": "high"}`
  - 调用方显式传 `thinking` 或 `reasoning_effort` 时不覆盖。
- 其他 provider 的 payload 不变；LM Studio 的 `json_schema` / reasoning 兼容分支保持原顺序。
- 思考模式下 DeepSeek 忽略 `temperature`；页面提示，不删除该字段，避免影响非思考模式。

## 5. 页面

- Provider 下拉：LM Studio / OpenAI / DeepSeek / OpenAI Compatible。
- DeepSeek 预设：`model=deepseek-flash`、`base_url=https://api.deepseek.com`。
- 密钥状态：
  - 当前 provider 已保存：显示“已保存到本机凭据文件”
  - 来自环境变量：显示“来自环境变量 LLM_API_KEY”
  - LM Studio：显示占位密钥
  - 未配置：显示“未配置”
- “清除密钥”按钮：仅当 `configured_providers` 包含当前 provider 且不是 LM Studio 占位时显示；带确认。
- 思考模式：仅 DeepSeek 显示；默认关闭；开启时说明使用 high effort 且温度不生效。
- 切换 provider：清空连接检查结果与模型列表，避免上一 provider 的模型串入。
- 保存：沿用现有流程；重新读取设置后清空密钥输入框。

## 6. 契约

`settings.get.llm_config` 新增 `thinking_enabled`、`api_key.source`、`configured_providers`。

`settings.update` 的 `llm_config` 新增 `thinking_enabled`；`api_key` 写入 provider 凭据文件。

新增 `settings.clearLlmApiKey`：

```json
{ "meta": { "correlation_id": "corr_001" }, "provider": "deepseek" }
```

返回 `{meta, provider, cleared, configured_providers}`。

`settings.checkLlmConnection` 对在线 provider 缺密钥返回 `BLOCKED_PROVIDER_CREDENTIAL`；LM Studio 既有 `BLOCKED_LOCAL_PROVIDER` 保持不变。

## 7. 安全与错误

- 凭据文件读写失败统一返回固定文案；不泄露路径、密钥或底层异常。
- 测试使用临时凭据根；`tests/conftest.py` autouse fixture 隔离。
- 不把密钥写入 `policy.local.yaml`、日志、run payload 或 GUI 状态。
- DeepSeek 401/403、超时、`/models` 不可达分别返回可读消息；不把连接成功等同于推理成功。

## 8. 测试策略

- 先失败后实现：凭据文件、密钥仓库、settings 读写/清除、连接检查、LLMClient 适配、agent env、GUI 契约。
- 回归：相关单测、全量 pytest、`tsc --noEmit`、项目门禁。
- 真实 App：用户填自己的 Key，走“检查连接 → 保存 → 重启 → 运行一次实际任务”；记录页面观察与调用结果。
- 不在测试中访问真实 DeepSeek API；真实调用只在用户授权的 App 验收中进行。

## 9. 边界

- 不实现思考强度选择（固定 high）、不实现模型能力探测、不做通用重试。
- 不改变 P0-026 唯一 `next`，不新增平台写入。
- `.pen` 同步在工具不可用时明确记录待补。
