# 招聘平台接入方案与迁移计划

初版日期：2026-09-27；六平台规划更新：2026-09-28。范围：猎聘、BOSS直聘、智联招聘、前程无忧 51job、脉脉、拉勾。状态：用户已确认六平台目标与分层顺序，P0-011 官方只读已完成真实原生验收，其余迁移待实施；执行顺序唯一来源为 [执行路线图](../../../docs/execution-roadmap.md)。

2026-09-28 实施状态补充：真实 App 已完成凭据验证、简历临时预览、19 条岗位摘要入库/刷新和清理后 AUTH_REQUIRED 阻断，详见 ledger 与原生动作证据。以下来源调研和路线取舍保留历史依据，不把已完成的只读工作重复列为待实施。

2026-09-28 P0-017A 首片：公开详情的 JobPosting/DOM 交叉验证已接入真实 App（294 字样本）；原岗位绑定、审核失效/重搜保留、CLI/App 画像一致性与严格平台路由已完成本地验证。当前模型未配置，真实解析/审核受阻；指定发送版本/回执及后续投递执行契约尚未收口，P0-017A 仍未完成。

2026-10-01 当前状态：P0-017A 与 P0-017 已完成默认简历/PDF 的共同结果追踪、人工反馈来源绑定和原生重启读回；11 条既有成功记录通过只读 External L3 验收，本轮未发新请求。唯一 next 转为 P0-018，BOSS 等后续平台仍按既定顺序待实施。前面的日期记录保留历史阶段，不作为当前 blocker。

## 1. 决策与范围

六平台均为正式规划范围，采用“猎聘官方 HTTP 优先、BOSS 社区 CLI 按版本适配、智联与 51job 后续只读接入、脉脉与拉勾先完成链接/JD 导入”的路线。保留 evidence-first 核心、Tauri → Python sidecar、现有领域模型、Gate/Review、PDF exporter、SubmissionRecorder 和反馈迭代。只调整外部输入与投递适配，不引入通用 MCP 宿主或第二套求职编排。

- 猎聘：首批仅 Token 认证、搜索和简历读取；官方 CLI/MCP 作为契约参考，不同时实现三套传输。
- BOSS：现有 adapter 有复用价值，但命令、字段、错误处理均需修复；先只读，未验收前继续默认关闭。
- 智联：不能继续依赖“boss-agent 最新版同时支持智联”的假设。2.0.0 是历史候选版本，不是当前可用性承诺；优先保留人工 JD/Job Lead，维护路线在多平台批次重新选择。
- 51job：纳入核心平台后续只读接入任务；先核对实际认证、搜索与详情契约，现有 URL 识别不能算接入完成。
- 脉脉、拉勾：均纳入补充来源任务，首版实现平台标识、职位链接与完整 JD 导入，接通现有画像/生成/追踪；“补充”不表示可从范围删除。
- 原目标保留：先猎聘单平台每天一个批次；扩展后按上海自然日，所有启用平台合计最多 3 次确认成功投递；定制简历版本与真实结果必须可追溯。
- 本轮不实施业务接入、不安装或升级工具、不读取账号凭据、不修改平台简历、不发消息或投递。公开源码、官方声明、协议元数据和账号业务实测分别记录。

### 六平台目标与最低交付

| 平台 | 定位与批次 | 目标交付 | 当前依据与缺口 |
| --- | --- | --- | --- |
| 猎聘 | 核心 / S1–S4 | 官方只读搜索/简历读取、完整 JD、审核版本绑定、单次投递及每日目标 | 已有官方契约与历史只读实证；App 接入、完整 JD/版本/回执仍待验收 |
| BOSS直聘 | 核心 / S5 | 固定版本只读搜索→详情→完整 JD→画像/生成/追踪；再验投递 | 已有 adapter 骨架，上游兼容问题已定位 |
| 智联招聘 | 核心 / S6 | 独立确认维护路线，完成只读搜索、详情及下游闭环 | 历史社区包有源码，当前主线已移除；在线可用性待验证 |
| 前程无忧 51job | 核心 / S6 | 核实契约并完成只读岗位发现、完整 JD 与下游闭环 | [官方产品](https://app.51job.com/) 的覆盖价值已核对；求职者接入契约未验证 |
| 脉脉 | 补充 / S7 | 职位链接与完整 JD 导入、审核、匹配/生成、手工结果追踪 | [官网](https://maimai.cn/) 的求职定位已核对；当前未验证在线接口 |
| 拉勾 | 补充 / S7 | 职位链接与完整 JD 导入、审核、匹配/生成、手工结果追踪 | [官方求职入口](https://s.lagou.com/) 已核对；当前未验证在线接口 |

验收分开统计：六平台来源覆盖目标为 6/6，每平台至少 1 个真实来源的完整 JD 样本贯通现有用户旅程；四家核心平台另验在线搜索/详情与失败处理；投递和反馈自动同步再按平台单独验收。人工来源覆盖可独立通过，但不得据此把核心平台在线接入任务标为完成。尚无稳定契约时保留缺口/阻断和人工入口，不移除该平台目标。网页链接或平台名称枚举本身不构成覆盖。

## 2. 来源与时效

此次在线核查覆盖平台官网入口、官方/社区上游仓库、GitHub 提交与发布包；搜索关键词包括平台名、CLI、MCP、API、求职者集成。未取得 BOSS/智联面向求职者的新官方接口的可核实入口；这是检索边界，不是“官方接口不存在”的断言。

| 来源 | 本轮核对结果 | 能证明什么 |
| --- | --- | --- |
| 猎聘官方 CLI [固定源码](https://github.com/liepin-tech-2026/liepin-cil/tree/858a62bd839d490e8745b7503961e4676a54b9d7) | HEAD `858a62b`，提交 2026-04-13，版本 0.1.0 | 未发现相对 9 月 9 日调研新增的公开 CLI 契约，不代表服务端内部没有变化 |
| 猎聘官方 [MCP 说明](https://github.com/liepin-tech-2026/liepin-job-mcp/blob/26f04e67a35744c69946c6bd70dc5d230b5a7cf2/README.md) | HEAD `26f04e6`，2026-04-03 | 本轮补充找到的官方来源；其发布日期早于本轮调研 |
| 猎聘 [MCP 服务](https://open-agent.liepin.com/mcp/user) | 无凭据实际执行 initialize / tools/list；HTTP 200，协议 2024-11-05，服务 1.26.0，14 个工具，无 outputSchema | 协议和工具发现可用；没有执行账号业务调用 |
| 猎聘 [授权页](https://www.liepin.com/mcp/server) | 本轮抓取遇安全页/404，未重新核实登录后的页面 | 不能据此判定服务下线；9 月 9 日登录、附件规则与业务样本保持历史证据身份 |
| 社区 boss-agent-cli [PyPI 2.0.0](https://pypi.org/project/boss-agent-cli/2.0.0/) / [固定 tag](https://github.com/can4hou6joeng4/boss-agent-cli/tree/c3f1a7ed92dde3f9828f7354c59c86ae36a77c86) | 发布 2026-09-15 06:02:13 UTC；实际读取源码包，未安装/执行 | 包内注册 `zhipin`、`zhilian`；不证明招聘网站现时可用 |
| 社区 CLI [主线变更记录](https://github.com/can4hou6joeng4/boss-agent-cli/blob/cf38175d11a100a8a9e906d272dac716b8f9c934/CHANGELOG.md) / [平台注册表](https://github.com/can4hou6joeng4/boss-agent-cli/blob/cf38175d11a100a8a9e906d272dac716b8f9c934/src/boss_agent_cli/platforms/__init__.py) | HEAD `cf38175`，2026-09-27 03:44:00 UTC | 主线已移除智联，仅注册 `zhipin`；不可把 master 与 2.0.0 混为同一能力集合 |

2.0.0 源码包 SHA256：`6f055ca3930adb4d161bd6c9f2219c942bd655b255d1d9cf989a917a3db81bce`。检索缓存曾返回旧版 master 文档，因此以固定提交和实际发布包核对结果为准；进入实施时须重新确认选定版本，而非盲用浮动最新版。

猎聘 9 月 9 日带 Token 的只读成功证据保留在 [原调研](../../../docs/reports/2026-09-08-liepin-integration-research.md)：两个接口 HTTP 200、业务码 0，简历文本与 20 个不同岗位；本轮未重新使用 Token，不推断旧凭据当前仍有效。

## 3. 已核实接入能力与六平台限制

以下猎聘、BOSS、智联有源码/协议层调研；新增三家目前只核对产品定位，未声明其具有可直接使用的官方 API/CLI/MCP，具体交付范围见上表。

### 猎聘：官方服务可作为主线，投递版本仍未闭合

- 官方 CLI [HTTP 客户端](https://github.com/liepin-tech-2026/liepin-cil/blob/858a62bd839d490e8745b7503961e4676a54b9d7/liepin_cli/core/client.py) 与 [职位命令](https://github.com/liepin-tech-2026/liepin-cil/blob/858a62bd839d490e8745b7503961e4676a54b9d7/liepin_cli/cli/job.py) 封装 `open-agent.liepin.com`，使用 `x-user-token`；已有 `GET /mcp/get-resume`、`POST /mcp/search-job`、`POST /mcp/apply-job`，不依赖本地浏览器调试。根地址见 [配置](https://github.com/liepin-tech-2026/liepin-cil/blob/858a62bd839d490e8745b7503961e4676a54b9d7/liepin_cli/core/config.py)，简历读取见 [简历命令](https://github.com/liepin-tech-2026/liepin-cil/blob/858a62bd839d490e8745b7503961e4676a54b9d7/liepin_cli/cli/resume.py)。
- 官方 MCP 说明仍声明 Token 有效期 90 天、读写共享每分钟 60 次额度。该额度与项目每日 3 次成功上限分别执行；重新生成旧 Token 的失效规则本轮未重验，不主动撤销凭据做测试。
- 历史只读样本：简历为 `errCode=0`、`data.result` 文本；搜索为 `code=0`、`data.list`，只有摘要/详情链接。搜索 `jobType` 应原值校验后映射投递 `jobKind`；样本全为 `"2"` 不代表只支持类型 2。
- 官方 README 宣称有岗位详情能力，但本轮 14 个工具中没有独立详情工具，CLI 也没有 detail 命令；目前未定位完整 JD 的可调用契约。`user-search-job` 第一页为 0，`search-jobs` 未声明分页；不得在这两个工具之间套用相同分页假设。
- [投递输入](https://github.com/liepin-tech-2026/liepin-cil/blob/858a62bd839d490e8745b7503961e4676a54b9d7/schemas/apply-job-input.json) 仍只有 `jobId` / `jobKind`，无附件/PDF/版本选择；CLI 枚举为 `"1"|"2"`，MCP 仅声明字符串。网页支持多附件不能证明 API 发送了选中的本地版本。
- 未取得投递成功、重复与未知结果的输出 schema；[输出器](https://github.com/liepin-tech-2026/liepin-cil/blob/858a62bd839d490e8745b7503961e4676a54b9d7/liepin_cli/core/output.py) 的“成功”显示和 Mock 投递测试不能代替业务回执。当前工具集合未发现进度/HR 回复查询，先复用人工反馈入口。

### BOSS：社区工具的新接口需要适配

`can4hou6joeng4/boss-agent-cli` 是第三方项目。CLI、MCP、Python API 是其不同调用入口；MCP 封装不构成招聘平台官方授权或更强的成功保证。

2.0.0 的固定 [入口](https://github.com/can4hou6joeng4/boss-agent-cli/blob/c3f1a7ed92dde3f9828f7354c59c86ae36a77c86/src/boss_agent_cli/main.py)、[搜索](https://github.com/can4hou6joeng4/boss-agent-cli/blob/c3f1a7ed92dde3f9828f7354c59c86ae36a77c86/src/boss_agent_cli/commands/search.py)、[详情](https://github.com/can4hou6joeng4/boss-agent-cli/blob/c3f1a7ed92dde3f9828f7354c59c86ae36a77c86/src/boss_agent_cli/commands/detail.py) 与当前项目存在以下差异：

| 契约 | 项目当前假设 | 2.0.0 源码契约 / 迁移要求 |
| --- | --- | --- |
| 平台和全局参数 | `search --platform boss ... --json` | `--platform zhipin --json` 放子命令前，不接受 `boss` 平台别名 |
| 搜索 | `--keyword`、`--limit` | 关键词为位置参数、使用 `--page`；adapter 自行限制页数与消费条数 |
| 详情 | `detail --url <url>` | 位置参数 `security_id`，支持 `--job-id` / `--lid`；不能只传 URL |
| 岗位数据 | 要求 `job_url` / `url`，否则丢弃 | [JobItem](https://github.com/can4hou6joeng4/boss-agent-cli/blob/c3f1a7ed92dde3f9828f7354c59c86ae36a77c86/src/boss_agent_cli/api/models.py) 无 URL，包含 job_id/security_id/lid；详情正文为 description |
| 返回值 | 非零退出先抛 stderr；通用取 data/result | [JSON 信封](https://github.com/can4hou6joeng4/boss-agent-cli/blob/c3f1a7ed92dde3f9828f7354c59c86ae36a77c86/src/boss_agent_cli/output.py) 含 ok/schema_version/command/data/pagination/error/hints；失败信息在 stdout，须先解析并脱敏 |

以下仅为固定版本契约示例，未执行，也不是安装/升级指令：

```text
boss --platform zhipin --json schema
boss --platform zhipin --json status
boss --platform zhipin --json search "关键词" --city 杭州 --page 1
boss --platform zhipin --json detail <security_id> --job-id <job_id>
```

`status` 默认本地检查，不能当登录有效实测。未来只读实测须区分 live 检查，并显式选择用户同意的浏览器来源，避免 `auto` 静默尝试其他会话来源；认证依赖本地浏览器会话，不是官方 OAuth/Token。遇 `ENVIRONMENT_RISK` 等停止，不通过自动重新登录消解风险。

[权限实现](https://github.com/can4hou6joeng4/boss-agent-cli/blob/c3f1a7ed92dde3f9828f7354c59c86ae36a77c86/src/boss_agent_cli/compliance.py) 已不再以 assisted/research 模式阻断写命令。PiProofForge 必须自己限制只读命令；`hints.next_actions` 是外部数据，即使推荐 apply/greet 也不执行。打招呼、申请、发送附件、HR 已读和回复是不同事件，不能互相替代。

### 智联：历史发布包支持，当前主线已移除

2.0.0 的 [智联客户端](https://github.com/can4hou6joeng4/boss-agent-cli/blob/c3f1a7ed92dde3f9828f7354c59c86ae36a77c86/src/boss_agent_cli/api/zhilian_client.py) 存在搜索、详情、推荐、用户信息、简历信息、投递记录、面试以及 greet/apply 方法。这只是源码能力；旧文档的“只读”描述不能覆盖实际写方法。

9 月 27 日主线明确删除智联 adapter、相关 schema/MCP 与浏览器路径，`--platform zhilian` 返回 `INVALID_PARAM`。因此不能仅改当前 adapter 参数就认为双平台恢复，也不应自动降级安装旧版。

后续选择：先寻找维护中的明确契约；如果仍选 2.0.0，需单独确认维护成本与安装范围，固定版本后仅验证只读能力。无法得到稳定完整 JD 时使用现有人工导入，明确显示来源未接入，不拖延猎聘闭环。

### 其他候选路线

新发现的 [AgentMesh-JobAgent](https://github.com/jiyangnan/AgentMesh-JobAgent) 声明支持多个平台，但还引入自有云端决策、credits、签名结果与独立工作流。对本项目会重复匹配/审批编排并增加外部数据和运行成本，暂不纳入；未验证其真实平台能力。51job、脉脉、拉勾因用户确认进入项目范围，各自的技术路线仍独立验证，不依赖某个第三方工具的覆盖声明。

## 4. 首轮仓库能力定位（后续实施见上方进展与 ledger）

检索范围：`PLAN.md`、`docs/`、核心 OpenSpec 与 Agent change、`AIEF/`、`tools/`、`ui/src/`、测试、验收矩阵和未提交改动。当前大量生成、PDF、浏览器会话与 Job Lead bridge WIP 保留；不清理、覆盖或提交它们。

| 分类 | 定位与事实 | 本次取舍 |
| --- | --- | --- |
| 已有可复用 | Evidence/Job Profile/生成/评测、共享 PDF exporter；`agent_loop.py` 已按投递尝试保存 PDF 与指纹 | 延续事实保真和定制版本目标，不要求用户另做成品 PDF；存量候选 NEEDS_REVIEW 不自动批准 |
| 已有但需接通 | `infra/discovery/boss_agent_cli.py` 只读骨架与 `read_detail`；生产 discovery 未消费详情 | 修命令/信封/字段，接完整 JD，不新建另一候选体系 |
| 已有但需修复 | `engines/discovery/job_leads_loader.py` 静默吞外部失败，成功结果优先返回；`jobs.convertLead` 以 URL 填 source_jd | 保留显式 leads 优先规则，外部失败可见；区分摘要/正文，避免空列表或草稿被报告为在线发现成功 |
| 已有模型有缺口 | `domain/models.py` JobLead、`domain/value_objects.py` Candidate 缺平台原始身份/类型；BOSS JobItem 没 URL | 增量保存平台原始引用与 provenance；已有 URL 输入兼容，不臆造动态 security_id |
| 仅历史实证 | 猎聘官方只读探针；`infra/browser/liepin_session.py` 是旧浏览器实现 | 官方 HTTP 尚需进入 infra/sidecar；浏览器 profile 不能充当 Token readiness |
| 已有但需接通 | `sidecar/handlers/agent.py` 审批只更新队列，guided batch 仍 dry-run | 在授权契约覆盖后接 approved→受控 delivery，不把 UI 审批当真实续跑 |
| 已有路由需修复 | `AgentLoop._run_delivery` 默认 Liepin/Email，request.channel 填 candidate.direction | 显式按平台选已支持通道，BOSS/智联候选不得送入猎聘；来源开关与投递开关分离 |
| 已有验收需迁移 | `submission/storage.py`、`acceptance/external_l3.py` 和 runbook 要求 browser profile、chat_send_resume | API 使用等价认证/目标/版本/回执证据；不伪造浏览器步骤；日志仍脱敏并绑定输入指纹 |
| 仅有设计/部分实现 | Agent design 10.3 幂等、`submission/rate_limit.py` 操作频控、run store | 原键含 run_id/版本，当前频控按 UTC 且操作前计数；都不能直接承担跨运行去重及上海日界成功上限 |
| 当前未找到完整实现 | 持续授权、每日单触发入口、平台反馈同步 | 按单次闭环后的批次补齐；反馈先复用现有人工来源 |
| 已有通用入口、专属接入未找到 | 在 tools/engines、infra、channels、sidecar、domain、ui/src 和 tests/unit 范围检索，新增三家仅命中 `job_leads_loader.py` 的 51job URL 规则；现有 Jobs 手工 JD/Lead 入口可复用 | 为 51job 核实并补只读 adapter；脉脉/拉勾补来源映射、导入审核和追踪。URL 识别和通用导入不等于逐平台真实验收已通过 |

## 5. 最小架构与契约增量

### 输入与认证

外部 IO 留在 infra；领域对象不持有 Token、Cookie 或 CLI 进程。复用设置页 Channels 与 sidecar，分别表达未配置、未验证、有效、失效、暂时错误。首批曾采用仅内存会话；2026-09-28 用户明确不接入钥匙串、接受本机明文权限文件，现改为固定用户目录的 `credentials/liepin-token`（目录 `0700`、文件 `0600`），重启恢复为未验证，正常退出不删除，用户主动删除才移除保存项。无新增依赖，不把 Token 放进普通 YAML、命令行、日志、仓库或 L3 env 模板；实际平台凭据是否有效仍须只读验证。

岗位增量数据至少涵盖 platform、稳定岗位 ID、原始类型/详情引用、抓取时间、JD 状态与来源；BOSS 的 security_id/lid 是请求上下文，不作为稳定去重主键。敏感请求上下文只进入必要的受控业务数据，审计报告保留脱敏引用。不得把搜索出来的岗位事实与用户经历事实混为同一 Evidence Card。

猎聘完整 JD 获取按公开契约核实 → 官方返回详情来源 → 用户粘贴并审核的顺序推进。无法取得正文就标记 incomplete；列表摘要不能自动生成“完整画像”。简历读取作为对照输入，不自动覆盖 Personal Profile/Evidence Cards。

### 投递与结果

继续使用 DeliveryRequest/Channel/SubmissionRecorder，在现有字段或最小增量中传递平台岗位身份、审批版本、PDF 指纹与实际发送版本绑定。传输错误、业务失败、重复、结果未知、确认成功分别表示；HTTP 200、CLI exit 0、聊天成功均不是充分条件。

指定版本的可行路径须有证据：若官方 API 能绑定既有平台附件，则验证附件 ID/版本与本地 PDF 的关系；若只能发送当前在线简历，则记录这一限制，完成具体差异和产品方案后再取得用户对改变发送形式的确认。不能先改在线简历或用默认版本试投。

API 迁移同步调整 recorder、L3 readiness、禁止输入处理与 runbook，保留相同授权与证据强度；原始 Token 仅从后端凭据引用取得。必要的请求/响应摘要只记录业务码、状态与指纹，不记录简历原文、密钥或招聘方私人信息。没有可用反馈 API 时，手动反馈须标记来源，不编造远程状态。

结果未知立即暂停，禁止自动重试或降级 Email。发送前保存稳定岗位键与 in-flight 尝试；已成功或未核对的未知结果阻止重启/换版本再次投递。稳定业务键为账号作用域 + 平台 + 岗位身份；旧 Agent design 10.3 的 run_id/candidate_id/channel/resume_version 组合只作 attempt 追溯键，本节和核心规范覆盖其跨运行防重语义。

后续每日阶段在同一持久化记录上增加上海自然日成功数和未决占位，所有启用平台合计成功数最多 3；未知未决不计成功但保留额度并停止本批。操作频控保留独立计数。持续授权包含渠道、岗位范围、审核版本、上限、有效期、暂停/撤销；单次上限不能代替每日限制。扩展平台不增加总额度，也不自动扩展已批准的渠道范围。

## 6. 分批实施与验证

具体顺序、状态和退出条件维护在 [路线图 S1–S8](../../../docs/execution-roadmap.md) 与既有验收矩阵，不另设平行任务台账。P0-011、P0-017A、P0-017 已 deep_verified；P0-018 为唯一 next，其他后续平台任务仍为 not_started。

- S1：先以失败契约测试覆盖猎聘响应/认证/脱敏，再完成只读 infra、sidecar 和 App 配置/搜索链。不重复历史临时探针；新 App 的真实只读验收是不同验收目标。复用现有页面职责，不增加页面；如果 UI 结构发生变化，同步 DESIGN.md、RPC 契约与 .pen。
- S2：补充原始岗位身份与完整 JD，建立最小稳定岗位键、提交前 in-flight 记录与重启后的成功/未知阻断；这些是首次真实提交前置，S4 再扩大每日及并发验证。版本绑定、回执协议是外部依赖。对审批续跑、平台路由和 API recorder/L3 做 TDD，测试未知结果、不可绑定版本、未授权以及不得跨平台投递。契约无法闭合时记录具体缺口，不以实现量换取放行。
- S3：只对已审核、明确授权的目标进行单次真实验证；真实 Tauri 用户动作、业务结果与脱敏日志共同证明完成。模拟调用通过或 blocker 落盘不等于投递成功。
- S4：验证重启防重、跨日/换版本、并发触发或进程中断、未知结果、授权过期/撤销；使用单入口和最小文件锁/原子写，不引入调度平台。连续多日真实验证后才宣称每日目标可用。
- S5：BOSS 固定版本契约测试覆盖搜索/详情/错误/无 URL 数据、分页有界消费与只读白名单；真实只读及下游生成/追踪完成后才评估投递。
- S6：智联与 51job 分别核实接入契约、认证、搜索/详情/错误映射与完整 JD，通过各自真实只读和下游闭环。单个平台外部阻塞不代表另一平台完成；可记录 blocker 后重排唯一 next，人工导入不抵消在线接入缺口。
- S7：脉脉与拉勾分别验证真实职位链接、完整 JD 导入、来源/获取时间、草稿审核、匹配和定制版本关联，再完成标明人工来源的结果追踪。仅粘贴链接不算完成；不要求为覆盖验收自动发消息或投递。汇总六家至少各 1 个真实样本，覆盖结果与在线/投递能力状态分别展示。

- S8：复用各平台已有真实页面/业务验收证据汇总 6/6 来源覆盖与 4/4 核心在线只读。猎聘即使通过人工 JD 完成受控投递，在线详情项仍须独立补验；未完成就保留 blocker，不以所有平台已有入口代替目标达成。此任务只汇总和补验实际缺口，不新增审计框架。

初次规划阶段仅做文档检查；后续 P0-011 和 P0-017A 首片的真实/本地验证已分别记入 ledger，不回写为初次调研已完成的能力。后续工期在 S1 接入与 S2 外部契约验证后估算，不把未知平台能力换算为确定完成日期。


### 2026-09-30 PDF 额外单笔授权与兼容性切片

最新结果：用户明确允许平台解析/后续附带影响后，App 已完成指定 PDF 真实发送。已授权测试 目标采用同一批准快照；平台上传、保存和列表应答与唯一附件 ID 对应，App 会话回读 PDF 完整 SHA256 一致。确认框唯一选中该 fileId，最终 `im.c.chat.send-resume` 请求带同一 attachmentId，HTTP 200 / flag 1 业务确认，经 App 本地核验后持久化为 success。原十岗加额外 PDF 一笔分别为 10/10、1/1；不重复发送。保留下面的历史探索过程，后续仅收口通用 API L3/反馈契约及既定后续阶段，不重做已通过的 PDF 验证。

十岗默认简历批次已结束，用户额外授权 1 次生成 PDF 实投。先复用 Tauri 自有 WebView 做登录兼容性验证，解决当前 Playwright/CDP 连接后页面跳空白的问题；不改变网站脚本或浏览器指纹，不放开远程页访问本机 IPC。复用现有主窗口、凭据策略、快照和防重，不另建常驻浏览器控制服务。此切片仅开放登录/只读观测，实际附件探测、批准 PDF 上传和真实发送待绑定契约验证后接入。

实测进展：用户手动登录后 App 可确认认证，重启仍保留；附件只读检查已接通。页面支持 PDF/DOC/DOCX/JPG/PNG，20M 上限，但明确提示上传授权自动解析并完善在线简历、后续主动投递会一并发送附件。因此不能将“上传至账号附件库”直接当作隔离的单次 PDF 测试。新额外影响需用户决定；不自动上传、不修改在线简历、不增加默认简历名额。App 已从真实工作材料生成已授权测试 岗位本地候选 PDF（匹配 23/100、仍为 NEEDS_REVIEW），完成字体可复制文本修复；上传身份绑定、发送与回执适配仍待实施。

### 2026-10-11 官方渠道复核：BOSS/智联/51job 改人工导入

用户要求在实施 S5 前先核查三家平台的官方接入渠道。本轮用网络搜索加内置浏览器未登录实测，结论与 9 月 27 日一致但证据更具体：

| 平台 | 官方渠道 | 未登录公开页面实测 | 社区方案与风险 |
| --- | --- | --- | --- |
| BOSS直聘 | 仅"企业雇主开放平台"面向企业 ATS（白名单，日均活跃岗位约 50 以上）；官方 AI 产品直闪闪、DeepHire、职决均为封闭产品，无 API/MCP/SDK | 未实测（需登录） | boss-agent-cli、boss-zhipin-mcp、boss-cli 等全部依赖浏览器会话或逆向接口；BOSS HI 协议禁止第三方工具获取服务；公开报道平台单季封禁约 2 万个抓取/欺诈账号 |
| 智联招聘 | 无求职者接口；"AI 版"与"职悟空·AI求职搭子"为自家产品；设安全应急响应中心 | 搜索列表可见但薪资打码为 `**-**元`，列表提示"登录查看更多"，职位描述截断并提示"登录查看完整内容" | 历史 boss-agent-cli 2.0.0 智联客户端已被上游主线移除；其余为浏览器插件 |
| 前程无忧 51job | 无求职者接口；仅企业 ehire/ehro 系统；隐私条款禁止爬虫抓取平台简历信息 | 搜索列表完整可见（职位、薪资、地点、技能、公司）；直接打开职位详情页触发"访问验证"滑块，未继续 | 爬虫须绕 acw_sc__v2 反爬；ai-job-search-cn 明确三平台"没有可用的免登录接口"并提示封号风险 |

决定（用户 2026-10-11 确认）：三家在线只读任务标为 `blocked` 并记录原因，改为人工导入职位链接与完整 JD，复用现有 Jobs 手工 JD/线索入口，走审核、匹配、定制版本与人工结果追踪；样本在 S8 计入来源覆盖，不冒充在线接入。接下来按 S7 做脉脉、拉勾来源导入，S7 依赖改为已验收的 Jobs 手工入口。本轮未安装社区 CLI，未修改代码，未发生平台写入。

来源：[ai-job-search-cn 访问说明](https://github.com/rockbenben/ai-job-search-cn/blob/main/SETUP.md)、[BOSS HI 用户协议](https://hi.zhipin.com/protocol/)、[BOSS直聘 DeepHire 报道](https://www.21jingji.com/article/20260527/herald/bdcfb21945b50311762860eac946df54.html)、[职决报道](https://zhuanlan.zhihu.com/p/2056839044450062578)、[封禁账号报道](https://m.jiemian.com/article/13552109.html)、[智联 AI 版报道](https://readhub.cn/topic/8lPpVm5tFCJ)、[智联安全应急响应中心](https://src.zhaopin.com/page/view?id=10001)、[51job 隐私条款摘要](https://we.51job.com/service?type=14)、[51job 企业版服务声明](https://ehire.51job.com/HTML/Agreement_c.htm?y=2016)。

同日复核脉脉与拉勾（S7 两家补充来源）：

| 平台 | 官方渠道 | 未登录公开页面实测 | 协议 |
| --- | --- | --- | --- |
| 脉脉 | 未找到开发者平台或 API；open.maimai.cn 无法打开；搜索到的"开放平台/接入 API"文章均为泛泛的产品或 SEO 内容，非脉脉官方开发者文档 | 职位搜索页直接跳转手机号/扫码登录，未登录看不到任何岗位 | 服务协议第二条（三）禁止"通过自研、授权代理、默认其他任何第三方登录……对脉脉产品和/或服务等进行任何非正常访问或对其中数据资料进行获取、下载"；第五条禁止"蜘蛛程序、爬虫程序、拟人程序"抓取；第六条可封禁账号、禁止重新注册 |
| 拉勾 | open.lagou.com 仅一个"拉勾开放平台"存根页，api.lagou.com 无文档端点；第三方核查结论为"未发布公开 API，无 SDK/CLI/MCP/webhook" | 职位搜索页未登录直接触发"访问验证"滑块，未继续 | 用户协议第三条（二）禁止"使用任何机器人软件、脚本等其他方式，自动访问或登录本网站"及"通过其他第三方工具或运营平台如外挂、插件、第三方招聘管理系统（ATS）等接入"，并禁止爬虫与批量检索；违规可封禁账号 |

对 S7 的含义：两家都不能由 App 在线取页面，连职位链接的服务器端校验都会碰到登录或验证。S7 的"真实职位链接 + 完整 JD 导入"只能完全由用户粘贴，App 负责按域名识别来源、标记人工导入与导入时间、做语法层链接校验与 JD 完整性检查，不发起任何平台请求；在线接入与投递能力单独保持未接入。

补充来源：[拉勾公开 API 面第三方核查](https://github.com/api-evangelist/lagou)、[拉勾网用户协议](https://help.lagou.com/staticpage/app/statement/statement.html)、[脉脉服务协议](https://maimai.cn/n/platform/rich-text/maimai_license)。
