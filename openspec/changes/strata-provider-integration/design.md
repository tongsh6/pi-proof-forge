# Design: strata-provider-integration

> 2026-10-22 方案修正（当前口径见 §10）：Strata 不再直连引擎端口，而是只连接
> Strata App 管理的统一推理后台 `http://127.0.0.1:47831/v1`；端点固定、模型由 App
> 管理并从 `/v1/models` 选择，Strata 也是默认推理后台。下文 §1–§9 保留 2026-10-21
> 首次接入的设计与历史事实，与 §10 冲突处以 §10 为准。

## 1. 总体思路

Strata App 在本机 `http://127.0.0.1:47831/v1` 暴露统一 OpenAI 兼容入口（App 负责加载/切换模型），现有 `LLMClient`、`/chat/completions`、`/models`、系统设置表单、按 provider 凭据文件与管线 env 注入都可直接复用。真正缺的是三件事：

1. `strata` provider 预设与显示名；
2. 本地 keyless 的连接检查语义（无 Key 不是错误，可选 Key 存在时正常携带）；
3. 请求层把 Qwen3.8 的思考控制适配为顶层 `reasoning_effort`。

不新增 SDK、不新增 HTTP 客户端、不新增 RPC 字段、不新建模型调用框架。

```
System Settings
  provider=strata（默认）→ base_url=http://127.0.0.1:47831/v1（固定，不提供编辑）
  model ← Strata App 当前已加载模型（GET /v1/models，页面刷新后选择）
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
| 本机 Strata App 实测 | 统一后台 `GET 127.0.0.1:47831/v1/models` 返回当前已加载模型（2026-10-22 为 `iq3_s`）；`reasoning_effort` 取 `none/low/medium/high` | 端点固定为统一后台；模型不写死，随 App 当前加载模型变化 |

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
- `extract_evidence_llm` 对 keyless provider 缺少 base_url 时显式报错，避免落到 OpenAI 默认地址；`provider=strata` 例外，缺省使用统一后台固定地址（2026-10-22 方案修正）。

## 4. settings 语义（`tools/sidecar/handlers/settings.py`）

- `_provider_label("strata") == "Strata App"`。
- 默认推理后台为 `strata`（新建/未配置时）：`_load_llm_config()` 返回固定
  `base_url=http://127.0.0.1:47831/v1`、`model=""`（由 App 的 `/v1/models` 选择）。
- `_load_llm_config()` 对无 Key 的 strata 自然返回 `api_key_for_request=""`、`source="none"`（同现状 else 分支），无需新字段。
- 旧配置或页面传入的 strata 其他端点（如直连引擎的 `8081`/`8082`）在读取与保存时都归一为统一后台地址；端点不接受页面编辑。
- `checkLlmConnection`：
  - `keyless_local = provider in {"lm_studio", "strata"}`；strata 无 Key 不返回 `BLOCKED_PROVIDER_CREDENTIAL`。
  - strata 的检查地址强制为统一后台；`/v1/models` 为空表示 App 尚未加载模型，返回 `code=BLOCKED_LOCAL_PROVIDER` 并明确提示先在 Strata App 加载模型。
  - 失败/空模型列表返回 `code=BLOCKED_LOCAL_PROVIDER`，消息使用 `Strata App`，不冒用 LM Studio。
  - 已保存的可选 Key 仍按 provider 隔离读取并传给 `LLMClient`；连接检查只证明 `/models` 可达，不代表推理质量。
- 保存/清除 Key 复用现有 `LLMApiKeyStore` 路径（`llm-strata-api-key`），无新 RPC、无新字段。
- 切换 provider 时清掉旧 provider 的 model，避免把旧模型 id 带给新 provider。

## 5. 页面（`ui/src/pages/system-settings/index.tsx`）

- Provider 选项顺序：LM Studio / Strata / OpenAI / DeepSeek / OpenAI Compatible；网格 `xl:grid-cols-5`；默认选中 Strata。
- Strata 预设：`base_url=http://127.0.0.1:47831/v1`（只读，共享常量 `STRATA_UNIFIED_BASE_URL`）、`model=""`（只读，需检查连接后从检测到的模型中选择）、`api_key=""`。
- 密钥状态：
  - 已保存：沿用“密钥已保存到本机凭据文件”；来自环境变量沿用现有提示；
  - 未保存：显示“本地服务，无需密钥（可选）”，provider 卡片与状态点按可用处理；
  - 清除入口仍只在本机确有凭据文件时显示。
- 思考开关：Strata 与 DeepSeek 一样显示；Strata 强度只显示 `low/high`（`max` 在切换到 Strata 时归一到 `high`），提示说明使用顶层 `reasoning_effort` 且默认关闭。
- 切换 provider 继续清空连接检查与模型列表，并套用预设；保存后重新读取设置、清空 Key 输入。
- 跨页面 keyless 一致性：`ui/src/lib/llmConfig.ts`（`isKeylessProvider` / `isLlmConfigured` / `isLlmSecretConfigured`）供 System Settings、Overview 安装清单、Quick Run、Agent Run 共用；keyless Strata 有 model 即视为已配置，密钥状态显示“本地服务，无需密钥（可选）”而非“未配置”。仅当确有本机凭据文件时提供清除入口。

## 6. 契约

不新增 RPC 字段，仅扩展 provider 取值与行为说明：

- `settings.get.llm_config.provider` 默认/可为 `strata`；strata 的 `base_url` 恒为 `http://127.0.0.1:47831/v1`，`model` 可为空（等待从 App 模型列表选择）；无 Key 时 `api_key.configured=false`、`source="none"`，UI 依据 provider 语义显示“无需密钥”。
- `settings.checkLlmConnection`：无 Key 的 strata 不返回 `BLOCKED_PROVIDER_CREDENTIAL`；失败/空模型为 `BLOCKED_LOCAL_PROVIDER`；端点强制统一后台。
- `settings.update` / `settings.clearLlmApiKey`：`provider=strata` 走既有按 provider 凭据逻辑；保存时 base_url 归一为统一后台，切换 provider 清除旧 model。

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

- 不改变当前 `policy.local.yaml` 的 provider（2026-10-22 本机仍为 DeepSeek），不自动切换；新安装/未配置时默认 Strata App。
- 不改 `.pen` 以外的页面结构；`.pen` 同步若 Pencil 工具不可用，按既有做法在台账注明待补，不以源码测试代替设计画布。
- 不改变 P0-026 唯一 `next`，不新增平台写入。

## 10. 2026-10-22 方案修正：Strata App 统一推理后台

作者指令：「修改方案 只一套由 Strata App 管理的推理后台统一连接 `http://127.0.0.1:47831/v1`」。

背景：早期的 `8081` / `q2_0` 是直接启动的 strata-engine 端口与模型；现在由 Strata App
统一管理模型加载与推理服务，在 `http://127.0.0.1:47831/v1` 暴露唯一的 OpenAI 兼容入口
（本机多次重启均稳定为 47831）。产品侧不再自行假设引擎端口或模型名。

### 当前实现（SSOT）

- **Contract**：`provider=strata` 只连接 Strata App 管理的唯一统一推理后台
  `http://127.0.0.1:47831/v1`；后端在读取、保存、连接检查时都把 base_url 归一为该固定
  地址（`tools/infra/llm/client.py::STRATA_UNIFIED_BASE_URL`），页面 Base URL 只读。
- **模型**：由 Strata App 管理。`GET /v1/models` 返回 App 当前已加载模型（如 `iq3_s`）；
  设置页「检查连接」后从真实列表选择并保存显式模型 id；不写死模型。模型切换在 App 侧
  完成后，产品侧刷新/重选即可；陈旧模型 id 由统一后台如实拒绝。
- **默认**：`strata` 成为默认推理后台（后端 `_DEFAULT_LLM_PROVIDER="strata"`；新建配置
  `model=""` 待选择，页面默认选中 Strata）。其他 provider（LM Studio / OpenAI / DeepSeek /
  OpenAI Compatible）保留为可切换 fallback，预设与行为不变。
- **连接检查**：无 Key 不返回 `BLOCKED_PROVIDER_CREDENTIAL`；端点不可达返回
  `BLOCKED_LOCAL_PROVIDER`；`/v1/models` 为空时明确提示先在 Strata App 加载模型。
- **管线**：`agent._persisted_llm_runtime_context()` 把统一地址/模型/思考参数注入子进程；
  `extract_evidence_llm` 在 `provider=strata` 且缺 base_url 时回退统一后台地址，不再落
  OpenAI 默认地址；keyless gate、`reasoning_effort` 适配保持既有语义。
- **手工 CLI/管线**：matching / generation / evaluation 与 agent CLI 的缺省 `--base-url` 按
  provider 选择（strata 落统一入口，其他 provider 保持各自默认），避免直接以
  `LLM_PROVIDER=strata` 且不设 `LLM_BASE_URL` 时误请求 OpenAI/LM Studio。
- **历史配置**：无 `llm_provider` 键的旧配置会按新默认解释为 strata 并归一 47831
  （本机 `policy.local.yaml` 有 provider，不受影响）；如需保留旧端点，应在设置页显式
  切换回对应 provider 并填写地址。
- **边界**：不改动当前生效 provider（本机 `policy.local.yaml` 仍为 DeepSeek）；不新增 RPC
  字段/SDK；不改变其他 provider 行为；不新增平台写入。

### 验证（2026-10-22）

- 单元：settings 默认 provider/固定端点/保存归一/切换 provider 清旧 model/空模型提示；
  `LLMClient` 无地址时回退统一入口；`extract_evidence_llm` strata 回退统一地址；
  GUI 契约与 i18n 键。全量 **1692 项通过、1 跳过、53 subtests**，`tsc --noEmit`、
  `pnpm --dir ui build`、roadmap/v2/AIEF 门禁通过。
- 真实本机：Strata App 运行时 `GET http://127.0.0.1:47831/v1/models` 返回 `["iq3_s"]`；
  真实 `LLMClient` 最小结构化请求返回 `{"ok":true}`（response model `iq3_s`）。
- 真实页面（Chromium + 只读桥接 + 临时 policy，非 Tauri 窗口）18 项检查字段（13 项硬断言）全部 PASS：默认
  Strata、47831 只读、模型从 `/v1/models` 选 `iq3_s`、切 provider 复位、保存归一；
  证据 `outputs/acceptance/strata-unified-20261022/`。App 未加载模型时连接检查如实
  blocked 并提示加载模型（不冒充可用）。
