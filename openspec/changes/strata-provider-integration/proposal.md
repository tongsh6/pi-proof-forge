# Proposal: strata-provider-integration

## Problem

系统设置当前提供 `lm_studio`、`openai`、`deepseek`、`openai_compatible` 预设，但没有 `strata`。用户已在本机运行 Strata 桌面应用（strata-engine），它通过 OpenAI 兼容接口在 `http://127.0.0.1:8081/v1` 提供本地推理（当前模型 `qwen3.8-flash-next-q2_0`），但 App 内没有对应 preset：

- 只能选择 `openai_compatible` 手工填写地址与模型，缺少默认值与专属文案；
- 连接检查按“在线 provider”语义处理，缺密钥会返回 `BLOCKED_PROVIDER_CREDENTIAL`，与 Strata 本地默认免鉴权不符；
- 现有 LM Studio 分支的 JSON schema / 型号特定 `reasoning_effort` 适配不适用于 Strata；
- Qwen3.8 的思考开关走请求顶层 `reasoning_effort`（`none` 关闭），需要集中适配，避免各请求点各写一套。

同一请求已在姊妹项目 novel-studio 中按同一设计落地（`provider/strata.ex`：keyless + `reasoning_effort` + `/models` 真探活），本变更是 PiProofForge 侧的等价接入。

## Goals

1. 增加一等 `strata` provider 预设：默认 `http://127.0.0.1:8081/v1`、`qwen3.8-flash-next-q2_0`，支持 `/models` 发现与真实连接检查。
2. 本地免鉴权：无密钥可用；保存的 `llm-strata-api-key` 作为可选 Key，存在时请求携带 `Authorization: Bearer`。
3. `LLMClient` 仅对 `provider=strata` 注入顶层 `reasoning_effort`：默认 `none`，开启思考后 `low|high`（`max` 映射为 `high`），结构化 JSON 请求默认关思考；绝不发送 `thinking` 对象。
4. 页面展示 provider 卡片、密钥“无需/已保存/环境变量”状态与思考开关（复用现有 low/high/max 控件，Strata 只显示 low/high）。
5. 复用现有 settings RPC、按 provider 凭据文件、管线 env 注入与 `LLMClient`；不新增 SDK、第二套客户端或字段。

## Non-Goals

1. 不改变当前生效 provider（用户当前仍使用 DeepSeek），不自动切换配置。
2. 不做 Strata 模型下载、引擎管理、model 自动切换或多实例发现。
3. 不新增 provider 能力矩阵字段、SDK、通用重试或自动故障转移。
4. 不改变 P0-026、简历质量、投递与证据流程；不新增平台写入。
5. 不在自动化测试中调用真实模型；真实调用只作为本机验收证据单独记录。

## Scope

- `tools/infra/llm/client.py`：Strata keyless 头、`reasoning_effort` 适配、`llm_request_available` / `provider_is_keyless` 共享 keyless 判定。
- `tools/sidecar/handlers/settings.py`：provider label、Strata keyless 连接检查语义。
- `tools/run_pipeline.py`、`tools/run_matching_scoring.py`、`tools/run_generation.py`、`tools/run_evaluation.py`、`tools/extract_evidence_llm.py`：子进程管线使用同一 keyless 判定，无 Key 不再被当作缺凭证；不注入伪造 Key。
- `ui/src/pages/system-settings/index.tsx`、`ui/src/pages/{overview,quick-run,agent-run}/index.tsx`、`ui/src/lib/llmConfig.ts`、`ui/src/i18n/{zh,en}.json`：provider 预设、密钥状态、思考开关与跨页面 keyless 状态一致。
- `tests/unit/{infra/sidecar/pipeline/matching/gui}` 相关测试；`tests/unit/gui/test_llm_config_helper_ui.py` 以 node-vm 真实执行 helper。
- `openspec/changes/strata-provider-integration/`、`ui/design/contracts/sidecar-rpc.md`、`ui/design/DESIGN.md`、`docs/execution-roadmap.md`、`docs/project-ledger.md`。

## Expected Outcomes

1. 系统设置出现 Strata 选项，切换后自动填充本地地址与当前模型；检查连接可列出 `/models`，无 Key 不再被当作凭证缺失。
2. 保存配置后 Quick Run（含子进程 quick-run 管线）、证据推断、语义匹配、岗位解析等现有入口通过同一 `LLMClient` 使用 Strata，无 Key 时也无需伪造占位 Key；默认不思考，开启后按 `reasoning_effort` 推理。
3. 已保存的 Strata 可选 Key 按 provider 隔离，切换 provider 不丢失；响应、日志不出现明文。
4. 其他 provider 请求完全不变；LM Studio 的 JSON schema 与型号适配保持原行为。

## Risks

- Qwen 推理模型在结构化输出时会耗尽小输出预算；本变更对 Strata 的 `json_object` 请求默认 `reasoning_effort=none`，沿用既有阶段纠错，不新增通用重试。
- 本机 Strata 端口/模型可能变化：页面保留可编辑 base_url/model 与 `/models` 检测，不把默认值写死为唯一事实。
- 真实 App 页面验收需用户在本机 Strata 运行时执行；未完成前不标记深度验收通过。
