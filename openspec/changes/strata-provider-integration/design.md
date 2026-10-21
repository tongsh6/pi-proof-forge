# Design: strata-provider-integration

## 1. 总体思路

Strata 桌面应用（strata-engine）在本机 `http://127.0.0.1:8081/v1` 暴露 OpenAI 兼容接口，现有 `LLMClient`、`/chat/completions`、`/models`、系统设置表单、按 provider 凭据文件与管线 env 注入都可直接复用。真正缺的是三件事：

1. `strata` provider 预设与显示名；
2. 本地 keyless 的连接检查语义（无 Key 不是错误，可选 Key 存在时正常携带）；
3. 请求层把 Qwen3.8 的思考控制适配为顶层 `reasoning_effort`。

不新增 SDK、不新增 HTTP 客户端、不新增 RPC 字段、不新建模型调用框架。

```
System Settings
  provider=strata → base_url=http://127.0.0.1:8081/v1, model=qwen3.8-flash-next-q2_0
  api_key 可选 → credentials/llm-strata-api-key (0600, 已存在则携带)
  thinking → policy.local.yaml: llm_thinking_enabled / llm_thinking_effort
        │
        ▼
settings.get / checkLlmConnection / update / clearLlmApiKey（复用现状）
        │
        ▼
LLMClient(provider=strata, thinking_enabled, reasoning_effort)
        ├─ Quick Run / Agent Run（子进程 env：LLM_PROVIDER/LLM_THINKING/...）
        └─ Evidence / Jobs / Job Preferences（in-process 传参）
        │
        ▼
POST {base_url}/chat/completions
  headers: 无 Key 时不发 Authorization；有 Key 时 Bearer
  body: 顶层 reasoning_effort
```

## 2. 现有能力与复用

| 需要 | 现状 | 处理 |
| --- | --- | --- |
| OpenAI 兼容调用 | `tools/infra/llm/client.py` 唯一 HTTP 入口 | 复用，增加 strata 分支 |
| 模型列表 / 连接检查 | `LLMClient.list_models()` + `settings.checkLlmConnection` | 复用，调整 keyless 判定与文案 |
| 按 provider 凭据 | `LLMApiKeyStore`（`llm-<provider>-api-key`，0600） | 复用，无需改动 |
| provider id 校验 | `normalize_provider` 正则已接受 `strata` | 复用，无需白名单改动 |
| 管线 provider/thinking 传递 | `agent._persisted_llm_runtime_context()` 已注入 env | 复用 env；额外把「无 Key 是否可发起 LLM」收敛为 `client.llm_request_available` / `provider_is_keyless`，供 `run_pipeline`、`run_matching_scoring`、`run_generation`、`run_evaluation`、`extract_evidence_llm` 的 gate 复用，避免把 keyless Strata 当缺凭证 |
| in-process 调用 | evidence/jobs/job_preferences 已传 provider/thinking | 复用，无需改动 |
| 页面 provider 卡片 | `LLM_PROVIDER_DEFAULTS` / `LLM_PROVIDER_OPTIONS` / 思考开关 | 扩展 strata 预设与条件显示；新增 `ui/src/lib/llmConfig.ts` 供 Overview / Quick Run / Agent Run / System Settings 共用 keyless 判定 |
| 本机 Strata 实测 | `GET 127.0.0.1:8081/v1/models` 返回 `qwen3.8-flash-next-q2_0`；`reasoning_effort` 取 `none/low/medium/high` | 作为默认值与验收依据，不写死为唯一可用模型 |

## 3. 请求适配（`tools/infra/llm/client.py`）

### 3.1 Keyless 头

`build_headers()`：`api_key` 非空时才返回 `Authorization: Bearer <key>`，否则只返回 `Content-Type`。本地 Strata 默认无鉴权；在线 provider 缺 Key 时本来也会 401，语义不变。

### 3.2 `reasoning_effort`

`provider=strata` 且 payload 未显式带 `reasoning_effort` 时：

| 场景 | 发送 |
| --- | --- |
| `response_format={"type":"json_object"}` | `reasoning_effort="none"`（结构化输出不把预算耗在推理上） |
| `thinking_enabled=False` | `reasoning_effort="none"` |
| `thinking_enabled=True` + `low` | `reasoning_effort="low"` |
| `thinking_enabled=True` + `high` | `reasoning_effort="high"` |
| `thinking_enabled=True` + `max` | `reasoning_effort="high"`（Qwen3.8 支持到 high，避免改口径发送非法值） |

- 永远不向 Strata 发送 `thinking` 对象。
- 调用方显式传入 `reasoning_effort`（如现有 localhost 判项代码传 `none`）时不覆盖。
- 其他 provider 分支不变；LM Studio 的 `json_schema` 与型号特定 `none`、DeepSeek 的 `thinking` 适配保持原顺序与原行为。

### 3.3 keyless 子进程 gate

sidecar 只在 `api_key_for_request` 非空时向管线子进程注入 `LLM_API_KEY`；Strata 默认无 Key 时该 env 不存在。因此「能否发起 LLM 请求」不能继续只判断 `LLM_API_KEY`，否则 Quick Run（默认 `use_llm + require_llm`）会在 matching 等阶段被误判为缺凭证。

- `tools/infra/llm/client.py` 提供唯一判定：`KEYLESS_PROVIDERS = {"lm_studio", "strata"}`、`provider_is_keyless(provider="")`（空值时读 `LLM_PROVIDER` env）、`llm_request_available(provider="", api_key="", model="")`（model 必填；Key 非空或 keyless 本地 provider）。
- `run_pipeline.has_llm_env`、`run_matching_scoring`、`run_generation`、`run_evaluation`（判项与解释两处）、`extract_evidence_llm` 均改用该 helper；在线 provider 无 Key 仍阻断，keyless Strata 继续走 LLM 路径。
- 不注入伪造占位 Key：请求头仍由 `build_headers()` 决定（空 Key 不发 `Authorization`），`agent._persisted_llm_runtime_context()` 不新增 `LLM_API_KEY`。
- `extract_evidence_llm` 在 keyless 且缺少 base_url 时显式报错，避免落到 OpenAI 默认地址。

## 4. settings 语义（`tools/sidecar/handlers/settings.py`）

- `_provider_label("strata") == "Strata"`。
- `_load_llm_config()` 对无 Key 的 strata 自然返回 `api_key_for_request=""`、`source="none"`（同现状 else 分支），无需新字段。
- `checkLlmConnection`：
  - `keyless_local = provider in {"lm_studio", "strata"}`；strata 无 Key 不返回 `BLOCKED_PROVIDER_CREDENTIAL`。
  - 失败/空模型列表返回 `code=BLOCKED_LOCAL_PROVIDER`，消息使用 `Strata`，不冒用 LM Studio。
  - 已保存的可选 Key 仍按 provider 隔离读取并传给 `LLMClient`；连接检查只证明 `/models` 可达，不代表推理质量。
- 保存/清除 Key 复用现有 `LLMApiKeyStore` 路径（`llm-strata-api-key`），无新 RPC、无新字段。

## 5. 页面（`ui/src/pages/system-settings/index.tsx`）

- Provider 选项顺序：LM Studio / Strata / OpenAI / DeepSeek / OpenAI Compatible；网格 `xl:grid-cols-5`。
- Strata 预设：`base_url=http://127.0.0.1:8081/v1`、`model=qwen3.8-flash-next-q2_0`、`api_key=""`。
- 密钥状态：
  - 已保存：沿用“密钥已保存到本机凭据文件”；来自环境变量沿用现有提示；
  - 未保存：显示“本地服务，无需密钥（可选）”，provider 卡片与状态点按可用处理；
  - 清除入口仍只在本机确有凭据文件时显示。
- 思考开关：Strata 与 DeepSeek 一样显示；Strata 强度只显示 `low/high`（`max` 在切换到 Strata 时归一到 `high`），提示说明使用顶层 `reasoning_effort` 且默认关闭。
- 切换 provider 继续清空连接检查与模型列表，并套用预设；保存后重新读取设置、清空 Key 输入。
- 跨页面 keyless 一致性：新增 `ui/src/lib/llmConfig.ts`（`isKeylessProvider` / `isLlmConfigured` / `isLlmSecretConfigured`），System Settings、Overview 安装清单、Quick Run、Agent Run 共用；keyless Strata 有 model 即视为已配置，密钥状态显示“本地服务，无需密钥（可选）”而非“未配置”。仅当确有本机凭据文件时提供清除入口。

## 6. 契约

不新增 RPC 字段，仅扩展 provider 取值与行为说明：

- `settings.get.llm_config.provider` 可为 `strata`；无 Key 时 `api_key.configured=false`、`source="none"`，UI 依据 provider 语义显示“无需密钥”。
- `settings.checkLlmConnection`：无 Key 的 strata 不返回 `BLOCKED_PROVIDER_CREDENTIAL`；失败为 `BLOCKED_LOCAL_PROVIDER`。
- `settings.update` / `settings.clearLlmApiKey`：`provider=strata` 走既有按 provider 凭据逻辑。

## 7. 安全与错误

- 不新增密钥落盘位置；可选 Key 仍只写入本机 0600 凭据文件，不进入 `policy.local.yaml`、日志或 GUI 状态。
- 错误消息不泄露 Key、路径或底层异常；测试使用临时凭据根，不读写用户真实凭据。
- 不访问真实 Strata 之外的网络；真实推理验收只在本机回环进行。

## 8. 测试策略

- 先失败后实现：
  - `LLMClient`：strata 默认 `none`、开启 `low/high`、`max→high`、`json_object` 强制 `none`、显式值不覆盖、不发 `thinking`、无 Key 不发 Authorization、其他 provider 不受影响。
  - settings：无 Key 连接检查可用且消息为 Strata、失败码 `BLOCKED_LOCAL_PROVIDER`、可选 Key 保存/读取/隔离、`_provider_label`。
  - GUI 契约：Strata 预设、选项、思考开关条件、low/high、keyless 文案、i18n 键完整。
- 回归：`python3 -m pytest tests/unit -q`、受影响模块、全量 `python3 -m pytest tests -q`、`cd ui && npx tsc --noEmit`、项目门禁。
- 真实本机验收（不计入自动化）：本机 Strata 运行中时，`GET /models` 与一次 `reasoning_effort=none` 的 JSON 结构化请求；App 页面点击验收由用户执行。

## 9. 边界

- 不改变当前 `policy.local.yaml` 的 provider（仍为 DeepSeek），不自动切换。
- 不改 `.pen` 以外的页面结构；`.pen` 同步若 Pencil 工具不可用，按既有做法在台账注明待补，不以源码测试代替设计画布。
- 不改变 P0-026 唯一 `next`，不新增平台写入。
