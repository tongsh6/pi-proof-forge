# Tasks: deepseek-provider-integration

> 设计依据：`design.md`；验收依据：`specs/llm-provider-config/spec.md`
> TDD：每项先建立失败测试；测试不得访问用户真实凭据或真实 DeepSeek API
> 边界：不改变 P0-026 唯一 `next`，不新增平台写入

---

## Phase A - 凭据基础设施

- [x] A1 `tools/infra/liepin_token_file.py`：抽取 `LocalCredentialFile`，保留 `LiepinTokenFile` 兼容默认路径与行为；临时文件名按目标文件名生成
  - 测试：任意文件名写入后 0600；目录 0700；既有猎聘测试全部通过
- [x] A2 新增 `tools/infra/llm_credentials.py`：`LLMApiKeyStore` 按 provider 存取删
  - 文件：`llm-<provider>-api-key`；provider 校验 `^[a-z][a-z0-9_]{0,31}$`
  - `configured_providers()` 只列出真实可读的凭据文件
  - 支持 `PPF_CREDENTIAL_DIR` 覆盖
- [x] A3 `tests/conftest.py`：autouse fixture 指向临时凭据根，清空 `LLM_API_KEY` / `LLM_THINKING`

## Phase B - settings 后端

- [x] B1 `_load_llm_config`：解析 saved / environment / legacy / none，返回 `api_key_source`、`configured_providers`、`thinking_enabled`
  - 在线 provider 无真实密钥时 `configured=false`，不得回退到字符串 `"configured"`
- [x] B2 `_save_llm_config`：保存 `api_key` 到对应 provider 文件；`thinking_enabled` 持久化；不把密钥写入 policy
- [x] B3 新 RPC `settings.clearLlmApiKey`：删除 provider 密钥，返回 `configured_providers`；注册到 `server.py`
- [x] B4 `settings.checkLlmConnection`：provider-aware 消息与缺密钥错误码；LM Studio 既有错误码保持
- [x] B5 `settings.get` 返回新增字段；旧 `lm_studio` 占位配置兼容
- [x] B6 测试：DeepSeek/OpenAI 密钥隔离、重启回读、清除、缺密钥、连接成功/失败、无明文

## Phase C - 请求与运行时

- [x] C1 `LLMClient`：`provider` 空值回退 `LLM_PROVIDER`；`thinking_enabled=None` 回退 `LLM_THINKING`
- [x] C2 DeepSeek 注入 `thinking.disabled` / `thinking.enabled + reasoning_effort=high`；显式参数不覆盖；其他 provider 不变
- [x] C3 `agent._persisted_llm_runtime_context`：summary 增加 `thinking_enabled`，env 增加 `LLM_THINKING`
- [x] C4 `evidence.py` / `jobs.py` / `job_preferences.py`：构造 `LLMClient` 时传入 `thinking_enabled`
- [x] C5 测试：默认关闭、开启、显式覆盖、环境回退、agent env

## Phase D - 页面

- [x] D1 `types.ts` / `api.ts`：`LlmConfig` 新增 `thinking_enabled`、`api_key.source`、`configured_providers`；新增 `clearLlmApiKey`
- [x] D2 设置页：DeepSeek provider 预设、密钥状态、清除按钮、思考开关、切换时清空检测结果
- [x] D3 i18n：中英文新增密钥状态、清除确认、思考模式与提示
- [x] D4 GUI 契约测试先失败后通过；`tsc --noEmit`

## Phase E - 文档与验收

- [x] E1 `ui/design/contracts/sidecar-rpc.md`：新增字段、`settings.clearLlmApiKey`、DeepSeek 适配说明
- [x] E2 `ui/design/DESIGN.md`：System Settings LLM 段补充 DeepSeek、按 provider 密钥与思考开关
- [x] E3 `docs/execution-roadmap.md` / `docs/project-ledger.md`：记录本任务与真实 App 验收结果
- [ ] E4 `.pen` 同步；工具不可用时明确标注待补
- [x] E5 全量 pytest、`tsc`、项目门禁
- [ ] E6 真实 App：用户用自己的 DeepSeek Key 完成“检查连接 → 保存 → 重启 → 运行一次实际任务”，记录观察与未完成项
