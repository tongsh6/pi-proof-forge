# Spec: llm-provider-config

## 定位

本规范定义 App 内 LLM provider 的配置、凭据、连接检查与 DeepSeek 请求适配。目标不是做一个通用模型平台，而是让现有 evidence-first 流程可以在本机 LM Studio、OpenAI、DeepSeek 与自定义 OpenAI 兼容端点之间切换，同时保证密钥不泄露、失败可解释。

## 1. Provider 目录

### R1.1 DeepSeek provider

系统设置与后端必须识别 `deepseek`，并提供以下默认值：

- base_url: `https://api.deepseek.com`
- model: `deepseek-flash`

不得把 DeepSeek 建模为新的 HTTP 客户端；请求仍走 `LLMClient` 的 OpenAI 兼容路径。

#### Scenario: 选择 DeepSeek 自动填充

- Given 用户位于系统设置「模型配置」
- When 用户把 Provider 从其他值切换为 DeepSeek
- Then Base URL 自动填为 `https://api.deepseek.com`
- And Model 自动填为 `deepseek-flash`
- And 上一次连接检查结果与模型列表被清空

## 2. 凭据

### R2.1 按 provider 保存

API Key 必须按 provider 分别保存到本机受限权限文件，目录 0700、文件 0600；不得写入 `policy.local.yaml`、日志或 GUI 持久化状态。

#### Scenario: 保存后重启仍可用

- Given 用户选择 DeepSeek 并输入有效 Key
- When 用户保存配置并重启 App
- Then `settings.get.llm_config.api_key.configured` 为 true
- And `source` 为 `saved`
- And `configured_providers` 包含 `deepseek`
- And 响应中不出现 Key 明文

### R2.2 Provider 隔离

不同 provider 的密钥互不覆盖；切换到另一个 provider 时，页面显示该 provider 自己的状态。

#### Scenario: 切换不丢密钥

- Given OpenAI 与 DeepSeek 都已保存 Key
- When 用户在两者之间切换
- Then 两个 provider 均显示已配置
- And 不需要重新输入 Key

### R2.3 清除密钥

必须提供 `settings.clearLlmApiKey`，按 provider 删除凭据文件，不修改 model/base_url/timeout/temperature。

#### Scenario: 清除只影响密钥

- Given DeepSeek 已保存 Key 与模型配置
- When 用户清除 DeepSeek 密钥
- Then `api_key.configured` 变为 false
- And provider/model/base_url 保持不变

### R2.4 环境变量回退

当本机没有对应 provider 的凭据文件时，`LLM_API_KEY` 环境变量可作为回退；页面必须标明 `source=environment`，不得让用户误以为已保存到本机。

## 3. 连接检查

### R3.1 Provider-aware 检查

`settings.checkLlmConnection` 必须使用传入或已保存的 provider 配置请求 `/models`，返回模型列表；消息不得固定为 LM Studio。

#### Scenario: DeepSeek 缺密钥

- Given 用户选择 DeepSeek 且没有保存 Key、没有环境变量
- When 用户点击检查连接
- Then 返回 `status=blocked` 与 `code=BLOCKED_PROVIDER_CREDENTIAL`
- And 消息明确提示 DeepSeek 密钥未配置

#### Scenario: DeepSeek 连接成功

- Given 用户提供有效 DeepSeek Key
- When 检查连接成功
- Then 返回 `status=pass`、`code=OK` 与 `models`
- And 不写入配置、不返回 Key

## 4. DeepSeek 请求适配

### R4.1 思考模式

DeepSeek 沿现有 `llm_thinking_enabled` 保存默认/明确关闭/明确开启（null/false/true）；provider 默认仍为关闭。公共字段与部署切换、环境优先级见 core 的 L3b 配置合同，不新增 DeepSeek 专用开关。

- 关闭：请求包含 `{"thinking": {"type": "disabled"}}`
- 明确开启：普通与结构化 JSON 请求均包含 `{"thinking": {"type": "enabled"}}` 与 `reasoning_effort=low|high|max`，不得被 JSON 默认覆盖
- 思考强度由页面选择，持久化到 `llm_thinking_effort`，默认 `high`
- 调用方显式传入 `thinking` 或 `reasoning_effort` 时不得覆盖
- 本配置适配不为其他 provider 生成 `thinking`；调用方显式 payload 继续沿统一优先级保留

#### Scenario: 默认非思考

- Given 用户未开启思考模式
- When Quick Run 向 DeepSeek 发起结构化请求
- Then 请求体包含 `thinking.type=disabled`
- And 不包含由本功能新增的 `reasoning_effort`

#### Scenario: 开启思考

- Given 用户开启思考模式、选择 `max` 并保存
- When 直接 App 调用或管线子进程向 DeepSeek 发起普通或结构化 JSON 请求
- Then 请求体包含 `thinking.type=enabled` 与 `reasoning_effort=max`

### R4.2 运行时传播

sidecar 必须把 provider、model、base_url、api_key、timeout 与完整三态 thinking 配置传给真实消费者。App 缺省/null 不继承父进程思考环境；Quick Run 使用原 LLM_THINKING 的 on/off/default 覆盖父环境。直接构造传递 null/false/true，不用 bool 转换；CLI 未提供构造参数才读环境。

## 5. 安全与错误

### R5.1 不泄露

`settings.get`、连接检查结果、错误消息与日志不得包含 API Key 明文；凭据文件错误只返回固定文案。

### R5.2 测试隔离

自动化测试不得读写用户真实凭据；测试必须使用临时凭据根。

### R5.3 兼容

- 既有 `lm_studio` 的 JSON schema 适配保留；思考控制沿 core L3b 的统一配置，不保留按模型名称设置默认值的分支。
- 既有 `LLM_API_KEY` 环境变量仍可用。
- 旧 policy 的 `llm_api_key_configured` / `llm_api_key_placeholder` 不得导致在线 provider 在没有真实密钥时被误判为可用。

## 6. 验收

- 单元测试覆盖凭据保存/读取/删除、provider 隔离、权限、符号链接、settings 掩码、连接检查、DeepSeek 请求注入、thinking 环境传播。
- GUI 契约测试覆盖 DeepSeek 选项、默认值、密钥状态、清除按钮、思考开关、切换清空。
- 真实 App 由用户使用自己的 Key 完成“检查连接 → 保存 → 重启 → 运行一次实际模型任务”；未完成前不得标记为深度验收通过。
