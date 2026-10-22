# Tasks: strata-provider-integration

> 设计依据：`design.md`；验收依据：`specs/llm-provider-config/spec.md`
> TDD：每项先建立失败测试；测试不访问真实模型或用户真实凭据
> 边界：不改变当前生效 provider，不改变 P0-026 唯一 `next`，不新增平台写入
> 2026-10-22 注记：Phase A–E 与 C1 中的 8081 / q2_0 / 可编辑端点描述为历史口径；当前实现与验证见文末「Phase F」。

---

## Phase A - 请求层（后端）

- [x] A1 `LLMClient.build_headers()`：`api_key` 为空时不发 `Authorization`，非空行为不变
- [x] A2 `provider=strata` 注入顶层 `reasoning_effort`：默认 `none`、开启 `low/high`、`max→high`、`json_object` 强制 `none`、显式值不覆盖、不发 `thinking`
- [x] A3 回归 DeepSeek / LM Studio 既有适配与 `test_llm_client.py`

## Phase B - settings（后端）

- [x] B1 `_provider_label("strata") == "Strata"`
- [x] B2 `checkLlmConnection`：strata 无 Key 不返回 `BLOCKED_PROVIDER_CREDENTIAL`；失败/空模型列表返回 `BLOCKED_LOCAL_PROVIDER` 且消息为 Strata
- [x] B3 可选 Key：保存到 `llm-strata-api-key`，按 provider 隔离；无 Key 时 `settings.get` 为 `configured=false`/`source=none`
- [x] B4 测试：无 Key 连接成功/失败、可选 Key 保存与连接使用、provider 隔离

## Phase C - 页面

- [x] C1 `LLM_PROVIDER_DEFAULTS` 增加 strata（`http://127.0.0.1:8081/v1` / `qwen3.8-flash-next-q2_0`），`LLM_PROVIDER_OPTIONS` 增加 Strata（LM Studio 之后），provider 网格 5 列
- [x] C2 密钥状态：strata 无 Key 显示“本地服务，无需密钥（可选）”，卡片/状态点按可用处理；清除入口仍只看本机凭据
- [x] C3 思考开关：strata 与 deepseek 同样显示，strata 仅 low/high（切到 strata 时 `max→high`），保存 payload 对 strata 传 `thinking_enabled/effort`
- [x] C4 i18n：`providerStrataHint`、`keyLocalOptional`、`thinkingModeHintStrata`、`keyOptionalPlaceholder` 中英文键；思考提示与实现一致（关闭发 `reasoning_effort=none`）
- [x] C5 GUI 契约测试 + node-vm helper 行为测试；`npx tsc --noEmit`

## Phase D - keyless 管线接通（独立审查 B1 后补）

- [x] D1 `client` 共享判定：`KEYLESS_PROVIDERS` / `provider_is_keyless` / `llm_request_available`
- [x] D2 管线 gates：`run_pipeline.has_llm_env`、`run_matching_scoring`、`run_generation`、`run_evaluation`（2 处）、`extract_evidence_llm` 复用判定；不注入伪造 Key
- [x] D3 `extract_evidence_llm` keyless 且缺 base_url 时显式阻断，不落 OpenAI 默认地址
- [x] D4 回归测试：pipeline / matching / generation / evaluation / extract / agent env；真实本机 matching 阶段（`--use-llm --require-llm`，无 `LLM_API_KEY`）通过
- [x] D5 跨页面 keyless 状态：`ui/src/lib/llmConfig.ts` + Overview / Quick Run / Agent Run；系统设置 placeholder 修正

## Phase E - 文档与验收

- [x] E1 `ui/design/contracts/sidecar-rpc.md`：provider 规则、strata keyless 连接检查码、keyless 子进程 gate、`reasoning_effort` 与空 Key 头行为
- [x] E2 `ui/design/DESIGN.md`：System Settings LLM 段与 2026-10-21 变更说明增加 Strata、keyless 与思考开关
- [x] E3 `docs/execution-roadmap.md` / `docs/project-ledger.md`：记录本任务、独立审查两轮、真实本机验证与未完成项
- [ ] E4 `.pen` 同步：本机无 Pencil 工具，待用户在 Pencil 中补 Strata 选项、5 列 provider 卡与思考开关条件
- [x] E5 全量 pytest、`tsc`、项目门禁
- [x] E6 真实本机验收：`/models` keyless 探活、一次结构化 JSON 请求（线上载荷 `reasoning_effort=none`、无 Authorization）、settings handler 连接检查、keyless matching 阶段真实调用；证据 `outputs/acceptance/strata-local-20261021/`
- [ ] E7 真实 App 页面点击验收：用户在本机 Strata 运行时完成“选择 Strata → 检查连接 → 保存 → 运行一次实际任务”

## 独立审查记录

- 第 1 轮：发现阻断 B1（keyless Strata 在 Quick Run 子进程被当缺凭证）；已按 Phase D 修复并由真实 matching 阶段验证。
- 第 2 轮：确认 B1 已解决、无阻断；非阻断项已处理：gate 回归测试补齐、extract base_url 安全、跨页面 keyless 状态、`.pen`/任务文档同步；剩余 `isLlmSecretConfigured` 清理已完成。

## Phase F - 2026-10-22 方案修正（Strata App 统一推理后台）

- [x] F1 `client.py`：`STRATA_UNIFIED_BASE_URL = "http://127.0.0.1:47831/v1"`；strata 缺省地址回退统一入口，不落 OpenAI 默认地址
- [x] F2 settings：默认 provider=strata；读取/保存/连接检查把 strata base_url 归一为统一入口；空 `/v1/models` 返回 `BLOCKED_LOCAL_PROVIDER` 并提示先在 App 加载模型；切换 provider 清旧 model
- [x] F3 页面：Strata 预设改用共享常量、model 默认空、Base URL/Model 只读、提示文案与默认 provider=strata；其他 provider 预设不变
- [x] F4 i18n：`providerStrataHint` 更新为统一后台，新增 `strataBaseUrlHint` / `strataModelManagedHint` 中英文
- [x] F5 回归：settings 默认/固定端点/切换清 model/空模型提示、`LLMClient` 缺省地址、extract 回退、GUI 契约与 helper 测试；全量 1692 项通过、1 跳过、53 subtests，`tsc`/`pnpm --dir ui build`/三门禁通过
- [x] F6 文档：proposal/design/spec/tasks、DESIGN、RPC 契约、roadmap、ledger 同步当前口径
- [x] F7 真实页面验收（Chromium + 只读桥接 + 临时 policy，非 Tauri）：18 项检查字段（13 项硬断言）全部 PASS（默认 Strata、47831 只读、模型从 `/v1/models` 选 `iq3_s`、保存归一）；真实 `LLMClient` 最小 `json_object` 请求返回 `{"ok":true}`；证据 `outputs/acceptance/strata-unified-20261022/`
- [ ] F8 真实 App 页面验收：用户在 Strata App 加载模型后完成“选 Strata → 检查连接 → 选模型 → 保存 → 运行一次实际任务”
