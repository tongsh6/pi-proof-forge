# Proposal: deepseek-provider-integration

## Problem

系统设置当前只提供 `lm_studio`、`openai`、`openai_compatible` 三个 provider 预设。用户要在 App 内使用 DeepSeek，只能把它当作 `openai_compatible` 手工填写，缺少 DeepSeek 的默认地址、默认模型、模型发现和 provider 专属提示。

更关键的是凭据链路不完整：页面保存 `api_key` 时只记录“已配置”状态，实际请求只读取环境变量 `LLM_API_KEY`。因此即使增加 DeepSeek 选项，页面内保存的 Key 也不会生效，用户无法在 App 内完成配置闭环。

同时，DeepSeek 当前模型默认开启思考模式（thinking），而本项目大量任务要求结构化 JSON 输出；若不做请求适配，推理内容可能挤占输出预算并拖慢 Quick Run。用户明确要求默认 `deepseek-flash` 非思考，并在页面提供思考模式开关。

## Goals

1. 增加一等 `deepseek` provider：默认 `https://api.deepseek.com`、`deepseek-flash`，支持 `/models` 发现与连接检查。
2. API Key 按 provider 分别保存到本机受限权限文件，保存后重启仍可用；页面只回读掩码状态。
3. 提供清除指定 provider 密钥的入口，不改变 model/base_url 配置。
4. DeepSeek 请求支持思考模式开关：默认关闭；开启时发送 `thinking.enabled` 与 `reasoning_effort=high`。
5. 所有现有 LLM 入口（Quick Run、证据推断、语义匹配、岗位解析等）共用同一份配置与 `LLMClient`，不新建第二套调用框架。
6. 保持 `LLM_API_KEY` 环境变量回退与 LM Studio 既有行为。

## Non-Goals

1. 不接入系统钥匙串；沿用本机 0600 权限文件。
2. 不增加 DeepSeek Anthropic 协议、Responses API、FIM、工具调用等能力。
3. 不实现模型级参数面板（top_p、max_tokens 等），仅增加思考模式开关。
4. 不改变 P0-026、简历质量、投递与证据流程。
5. 不做 provider 自动故障转移或跨 provider 密钥共享。

## Scope

- `tools/infra/liepin_token_file.py`：抽取通用本机凭据文件能力，保留猎聘行为。
- `tools/infra/llm_credentials.py`：按 provider 的密钥仓库。
- `tools/sidecar/handlers/settings.py`：配置读取/保存/清除、provider-aware 连接检查。
- `tools/infra/llm/client.py`：DeepSeek thinking 适配。
- `tools/sidecar/handlers/{agent,evidence,jobs,job_preferences}.py`：运行时传递 provider/thinking。
- `ui/src/pages/system-settings/`、`ui/src/lib/sidecar/{api,types}.ts`、i18n：页面与契约。
- `ui/design/contracts/sidecar-rpc.md`、`ui/design/DESIGN.md`、路线图与台账。

## Expected Outcomes

1. 用户在系统设置选择 DeepSeek，填入自己的 Key，点击“检查连接”能看到模型列表，保存后重启仍显示已配置。
2. Quick Run、证据推断等真实入口在 DeepSeek 下可以发起请求；默认非思考，开启开关后请求带 thinking 参数。
3. `settings.get` 与日志中不出现密钥明文；测试不读写用户真实凭据。
4. 切换 OpenAI / DeepSeek 时，各自密钥状态独立，无需重复输入。
5. 既有 LM Studio / OpenAI 配置、投递流程与 P0-026 不受影响。

## Risks

- DeepSeek JSON 模式官方提示偶发空正文；本变更依赖现有阶段纠错，不新增通用重试。
- 真实 App 验收需要用户自己的 DeepSeek Key；不以 mock 或单元测试替代页面验收。
- 思考模式与温度参数互斥（DeepSeek 在 thinking 下忽略 temperature）；页面需明确提示。
