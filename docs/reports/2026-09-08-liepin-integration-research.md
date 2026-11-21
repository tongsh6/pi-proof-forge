# 猎聘接入方案历史调研（应用契约摘要）

调研时间：2026-09-08 至 2026-09-27。本文保留应用接入方向、官方来源与错误处理边界；账号操作、凭据状态、搜索批次、个人简历及运行报告留在本机数据区。这里是当时的工程观察，未重新核实平台当前能力，也不代表当前 App 已完成相应验收。排期以 [执行路线图](../execution-roadmap.md) 和 [招聘平台接入方案](../../AIEF/docs/plans/2026-09-27-recruitment-platform-integration.md) 为准。

## 接入方向

官方 Token + HTTP 接口是岗位发现和在线简历读取的接入方向。浏览器用于用户自行登录与取得凭据；配置凭据不自动授予简历维护、上传或投递权限。接口定义、协议握手、只读调用、真实 App 行为和实际发送是不同层次的证据，不能互相代替。

官方投递模型只声明岗位 ID 与岗位类型，不能据此证明发送的是 PiProofForge 生成并审核的具体 PDF。附件的选择规则、上传副作用、发送字节身份与业务回执仍需由对应路线核验；不能默认为 API 与网页使用相同规则。

## 官方契约来源

- 官方入口：[猎聘 CLI 授权页面](https://www.liepin.com/mcp/server)。该页的授权和使用限制是当时调研依据；平台限制与项目自身每日确认成功上限分别约束。
- 官方 CLI 仓库：[liepin-tech-2026/liepin-cil](https://github.com/liepin-tech-2026/liepin-cil)。源码当时使用 `https://open-agent.liepin.com` 与 `x-user-token` 请求头，参见 [配置](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/core/config.py) 和 [HTTP 客户端](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/core/client.py)。
- 只读入口为 `GET /mcp/get-resume` 与 `POST /mcp/search-job`，投递入口为 `POST /mcp/apply-job`。参见 [职位命令](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/cli/job.py) 与 [简历命令](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/cli/resume.py)。MCP 定义与 CLI 是同一接入方向的不同封装，不需要在应用内并行维护两套投递流程。
- 投递 `jobKind` 应来自原始搜索记录的 `jobType`，按 [官方模型](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/models/job.py) 校验；不可从 URL 猜测，也不可根据某次样本把所有岗位硬编码为同一类型。

## 应用必须处理的边界

| 观察或契约 | 应用约束 |
| --- | --- |
| JSON-RPC 返回 `result` 时仍可包含 `isError=true` | 协议响应不等于业务成功，继续核对业务码与用途匹配的 payload |
| 无效或缺失凭据可能返回 HTTP 错误及非 JSON 正文 | 明确认证与传输错误，不将解析异常伪装为空结果；错误正文不回显敏感内容 |
| 简历结果可能是 `data.result` 中的文本 | 按真实类型消费，不假设已展开的结构对象或可选附件版本 |
| 搜索摘要可包含公司、规模、地区与详情链接 | 摘要不能替代完整 JD；详情来源、岗位身份、有效性和分页分别核验 |
| 业务码字段可因接口不同而变化 | 按具体接口归一化，保留成功、失败和未知，不能只看 HTTP 状态 |
| 官方投递只声明岗位身份参数 | 指定简历版本、附件选择和真实发送结果需要独立证据 |
| 上传说明可能包含平台解析及在线简历变更 | 上传是有副作用的动作，必须纳入明确授权，不能当作纯文件存储 |
| CLI 通用输出器与 Mock 测试可显示成功 | 退出码、空响应或字面“成功”不能成为真实平台回执 |

最后一项的来源是 [输出实现](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/core/output.py)、[公共调用](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/cli/common.py) 与 [投递命令测试](https://github.com/liepin-tech-2026/liepin-cil/blob/main/tests/test_cli_job.py)。

## 机制与复用归属

- 认证和 HTTP 错误落在既有 infra；领域渠道继续由 `tools/channels/liepin.py` 承责。更换传输不能绕开授权、岗位确认或回执约束。
- Job Lead、完整 JD、Reviewed Job Profile 与简历版本沿现有身份关联，不建立平行候选账本。
- `tools/submission/storage.py` 保存实际适用的步骤和结果。API 路线不伪造浏览器专属动作成功；不同路线的业务证据需明确定义。
- 浏览器调试连接造成页面异常的历史观察，只能支持诊断连接兼容性；短暂显示登录表单不证明登录、会话复用或投递链可用。不通过逆向私有接口或修改网站安全脚本补齐契约。
- 一次只读成功不证明完整 App 旅程、跨运行防重或每日调度已成立；认证方法迁移也不能继承旧浏览器路线的验收结论。

## 后续验证原则

先验证完整 JD、输入身份和来源，再验证指定版本与发送字节身份。写操作须在已授权范围内执行；超时或结果不明时保持未知，不自动重试。真实平台结果与授权记录只留本机，应用仓库保留可复现的合成测试和机制规范。
