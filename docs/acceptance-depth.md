# 自动化深度验收规范

本规范用于判断自动化验收是否足以证明一个用户目标已经真实闭环。

## 判定标准

一个验收脚本只有同时满足以下条件，才算深度验收：

1. 有明确用户目标，不只检查页面或字段存在。
2. 执行真实动作链，覆盖用户会触发的关键状态变化。
3. 穿过真实系统边界，例如 Tauri bridge、sidecar、持久化或真实协议 stub。
4. 断言结果能被后续系统环节读取或消费。
5. 覆盖至少一个失败路径，且失败原因结构化。
6. 覆盖安全边界，尤其是 secret 不回显、不误用。
7. 失败时能定位到具体断裂点。

## System Settings LLM 口径

`pnpm --dir ui run e2e:system-settings` 必须验证：

- 真实 Tauri 桌面壳加载 System Settings。
- 真实 sidecar 返回 `settings.get`。
- Provider 默认值联动会填充 LM Studio 本地默认配置。
- 脚本启动 OpenAI-compatible `/v1/models` stub，并通过真实 `settings.checkLlmConnection` 读取模型列表。
- 页面选择检测到的模型，并通过 `settings.update` 保存。
- 重新 `settings.get` 后可读回 provider、base_url、model 和 masked API key 状态。
- 明文 API key 不出现在读回配置中。
- 未配置 base_url 的连接检查返回结构化 `BLOCKED_LOCAL_PROVIDER`。

只检查源码 marker、按钮存在或页面加载，不满足 System Settings LLM 深度验收。
