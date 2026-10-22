# Spec: llm-provider-config（strata-provider-integration delta）

> 2026-10-22 方案修正：Strata 由直连引擎改为只连接 Strata App 管理的统一推理后台
> `http://127.0.0.1:47831/v1`，端点固定、模型由 App 管理；Strata 成为默认 provider。
> 其他 provider 规范不变。

本 delta 扩展既有 `llm-provider-config` 能力：新增 `strata` 本地推理 provider，定义其可选密钥、连接检查与 `reasoning_effort` 请求适配。既有 LM Studio / OpenAI / DeepSeek / OpenAI Compatible 规范保持不变。

## 1. Provider 目录

### R1.2 Strata provider

系统设置与后端必须识别 `strata`，并提供以下默认值：

- base_url: `http://127.0.0.1:47831/v1`（Strata App 统一推理后台，固定不可编辑）
- model: 空，由 `GET {base_url}/models` 返回的 App 当前已加载模型决定，不写死模型名

不得把 Strata 建模为新的 HTTP 客户端；请求仍走 `LLMClient` 的 OpenAI 兼容路径。
`/models` 返回当前已加载模型；页面不允许修改 Strata 的 base_url，model 只读且需从检测到的
模型列表选择。后端读取/保存/连接检查时都必须把 `provider=strata` 的 base_url 归一为该
固定地址，旧配置里的直连引擎地址不再生效。

#### Scenario: 选择 Strata 自动填充

- Given 用户位于系统设置「模型配置」
- When 用户把 Provider 切换到 Strata
- Then Base URL 自动填为 `http://127.0.0.1:47831/v1` 且只读
- And Model 为空且只读；点击「检查连接」后从 `/v1/models` 返回的真实模型中选择
- And 上一次连接检查结果与模型列表被清空

### R1.3 默认推理后台

- 新建/未配置 LLM 配置时，默认 `provider=strata`、`base_url=http://127.0.0.1:47831/v1`、`model=""`。
- 用户已保存的其他 provider 配置不得被自动改写；LM Studio / OpenAI / DeepSeek /
  OpenAI Compatible 保留为可切换 fallback，行为不变。
- 从其他 provider 切换到 Strata 时，不得沿用旧 provider 的 model。

## 2. 凭据

### R2.5 可选密钥

Strata 本地回环服务默认无鉴权，密钥必须是可选项：

- 未保存密钥时，连接检查与推理请求照常发起，不返回凭证缺失阻断；
- Quick Run 等子进程管线必须使用同一 keyless 判定：没有 `LLM_API_KEY` 时仍以 Strata 发起 LLM 阶段，不得注入伪造占位 Key，也不得因此返回 FAILED；
- 页面必须明确显示“本地服务，无需密钥（可选）”，不得显示为“未配置”错误态；Overview / Quick Run / Agent Run 等页面按同一语义展示；
- 用户仍可保存 `llm-strata-api-key`（0600）作为 serving API Key；存在时请求携带 `Authorization: Bearer`；
- 密钥按 provider 隔离，保存/清除不影响其他 provider，也不改变 model/base_url/timeout/temperature。

#### Scenario: 无密钥连接检查

- Given 用户选择 Strata 且没有保存 Key、没有环境变量
- When 用户点击检查连接且本机 Strata 服务可达
- Then 返回 `status=pass`、`code=OK` 与模型列表
- And 不返回 `BLOCKED_PROVIDER_CREDENTIAL`
- And 请求不携带 `Authorization` 头

#### Scenario: 无密钥 Quick Run 子进程

- Given 当前 provider 为 Strata 且没有保存 Key
- When 用户以默认 `use_llm=true, require_llm=true` 启动 Quick Run
- Then 子进程 env 不包含 `LLM_API_KEY`，但 matching / generation / evaluation 的 LLM gate 放行
- And 管线不因缺少 Key 返回 FAILED
- And 请求头不包含 `Authorization`

#### Scenario: 可选密钥生效

- Given 用户保存了 Strata 可选 Key
- When 用户检查连接或运行一次模型任务
- Then 请求携带 `Authorization: Bearer <key>`
- And 页面显示 `source=saved`，响应与日志不出现明文

## 3. 连接检查

### R3.2 Strata 本地语义

`settings.checkLlmConnection` 对 `provider=strata`：

- 检查地址必须是统一后台 `http://127.0.0.1:47831/v1`，忽略页面/旧配置传入的其他地址；
- 本地端点不可达或未配置 base_url 时，返回 `status=blocked`、`code=BLOCKED_LOCAL_PROVIDER`，消息使用 `Strata App`，不得冒用 LM Studio；
- `/v1/models` 为空时同样返回 `BLOCKED_LOCAL_PROVIDER`，消息明确提示先在 Strata App 加载模型；
- 不因缺少密钥返回 `BLOCKED_PROVIDER_CREDENTIAL`；
- 检查只证明 `/models` 可读，不代表推理质量；不写入配置、不返回 Key。

#### Scenario: Strata App 未启动

- Given 用户选择 Strata 且本机 `47831` 端口未监听
- When 用户点击检查连接
- Then 返回 `code=BLOCKED_LOCAL_PROVIDER`
- And 消息包含 `Strata` 且不包含 `LM Studio`

#### Scenario: Strata App 未加载模型

- Given Strata App 在 `47831` 运行但当前没有已加载模型
- When 用户点击检查连接
- Then 返回 `status=blocked`、`code=BLOCKED_LOCAL_PROVIDER`
- And 消息提示先在 Strata App 加载模型

## 4. Strata 请求适配

### R4.3 reasoning_effort

`provider=strata` 时必须使用请求顶层 `reasoning_effort` 控制思考，不得发送 `thinking` 对象：

- 结构化 JSON 请求（`response_format.type=json_object`）：默认 `reasoning_effort=none`；
- 思考关闭：`reasoning_effort=none`；
- 思考开启：`low` 或 `high`；页面 `max` 映射为 `high`（Qwen3.8 不发送非法值）；
- 调用方显式传入 `reasoning_effort` 时不覆盖；
- 其他 provider 不注入该字段，LM Studio / DeepSeek 既有适配不变。

#### Scenario: 默认非思考

- Given 用户未开启思考模式
- When App 向 Strata 发起普通请求
- Then 请求体包含 `reasoning_effort=none`
- And 请求体不包含 `thinking`

#### Scenario: 开启思考

- Given 用户开启思考模式并选择 `low`
- When 管线子进程请求 Strata
- Then 请求体包含 `reasoning_effort=low`
- And 不包含 `thinking`

#### Scenario: 结构化输出不思考

- Given 用户开启了思考模式
- When App 发起 `response_format.type=json_object` 请求
- Then 请求体 `reasoning_effort=none`

## 5. 安全与错误

### R5.1 不泄露

`settings.get`、连接检查结果、错误消息与日志不得包含 API Key 明文；凭据文件错误只返回固定文案。

### R5.2 测试隔离

自动化测试不得读写用户真实凭据、不得请求真实模型；真实推理验收只在本机回环单独执行并记录。

### R5.3 兼容

- 既有 `lm_studio` / `openai` / `deepseek` / `openai_compatible` 配置、凭据与请求适配保持不变。
- 当前已保存的其他 provider 与 `policy.local.yaml` 不被本变更自动改写；仅新建/未配置时默认 Strata。
- 无 `llm_provider` 键的历史配置按新默认解释为 `strata`（端点归一 47831）；如需保留旧端点，由用户在设置页显式切换 provider 并填写地址。

## 6. 验收

- 单元测试覆盖 keyless 头、strata `reasoning_effort` 六类载荷、其他 provider 不变、settings keyless 连接检查与可选密钥隔离。
- 单元测试覆盖统一后台语义：默认 provider=strata、固定 base_url 归一（读取/保存/检查）、空模型提示、切换 provider 清旧 model、`LLMClient` 缺省地址回退统一入口。
- GUI 契约测试覆盖 Strata 选项/统一端点/只读字段/思考开关与 effort 选项、i18n 键完整。
- 本机 Strata App 运行时完成真实 `/models` 与一次结构化请求验证（不计入自动化）；
  App 未加载模型时连接检查如实 blocked。
- 真实 App 页面由用户完成“选择 Strata → 检查连接 → 加载/选择模型 → 保存 → 运行一次实际模型任务”后，方可标记深度验收通过。
