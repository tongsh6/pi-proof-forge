# 猎聘接入方案重新调研

> 2026-09-27：猎聘/BOSS/智联复核及已确认的六平台整体规划已汇总到 [招聘平台接入方案](../../AIEF/docs/plans/2026-09-27-recruitment-platform-integration.md)，排期以 [执行路线图](../execution-roadmap.md) 为准。下文保留 9 月 8–9 日历史实证；旧 Token 的当前有效性、平台业务响应和附件规则未因本次公开资料复核而重新验证。

初次调研：2026-09-08；登录后补充：2026-09-09。范围：接入方式、认证、岗位读取、简历版本、投递与反馈；本轮不实施业务替换，不修改平台简历或发起投递。

## 结论

建议采用猎聘官方 Token + HTTP 接口作为岗位发现和在线简历读取的接入方向。2026-09-09 V2 实测已确认：两个只读接口均 HTTP 200、业务码为 0，返回 20 个不同岗位和含基本信息、经历等章节的简历文本。浏览器只需承担人工登录与取得授权凭据。该只读链路调研可收口；App 尚未接入，指定简历版本投递和成功回执仍未验收。

Firefox 和原生界面自动化暂不作为主线投入。它们最多是待验证的兼容性方案；此前对照已证明普通 Chrome 能显示登录表单，而建立调试连接后同一页面跳空白。

最重要的产品缺口仍是：官方投递接口公开参数只有岗位 ID 和岗位类型，不能据此证明发送的是 PiProofForge 生成并审核的具体 PDF。2026-09-09 已在登录后的网页核实多份附件与随在线简历发送的说明，但 API 是否沿用该规则、如何选择具体附件仍待确认。不能以官方接口可投递为由降低原定简历版本约束。

## 已取得的证据

| 证据 | 当前结果 | 结论边界 |
| --- | --- | --- |
| 普通 Chrome 与调试连接对照 | 同一官网页面在连接调试工具后跳 `about:blank`；隔离会话同样复现 | 定位了连接相关触发因素；没有隔离到唯一 CDP 命令或探针 |
| 官方授权页面 | 页面标题为“授权配置 — 猎聘 CLI”，直接链接官方 CLI 仓库；用户随后取得 Token 并通过本机隐藏输入调用只读接口 | 网站登录与首批只读响应已确认；未执行任何投递 |
| MCP `initialize` | 实际响应协议版本 `2024-11-05`、服务版本 `1.26.0` | 仅证明握手可用 |
| MCP `tools/list` | 实际取得 14 个工具定义 | 定义存在不等于对应业务调用成功 |
| 不带 Token 的通用岗位搜索 | 返回 `result.isError=true`，内部错误为 `401 Unauthorized` | 业务查询需要授权；不能只凭 JSON-RPC 返回了 result 就判成功 |
| 官方 CLI 源码对应的简历查询 URL | 未带 Token 实测 HTTP 401，响应正文为 HTML 错误页 | 错误处理必须兼容非 JSON 正文 |
| 带 Token 的只读调用 | V2 确认简历 `errCode=0`、搜索 `code=0`，均 HTTP 200；简历为非 JSON 文本，岗位 ID 共 20 个且无重复 | 只读查询已实证；不代表投递及完整 App 用户旅程通过 |
| 本机 `liepin-cli --help` | 命令未找到，用户确认尚未安装 | 未执行 CLI、未安装依赖 |

浏览器对照记录：`outputs/acceptance/login_entry_fix_20260907/chrome-connection-comparison.json`。

官方产品入口：[猎聘 CLI 授权页面](https://www.liepin.com/mcp/server)。本轮通过真实浏览器读取；联网检索工具直接抓取该页曾被安全页拦截，不能把检索工具的失败当作页面不存在。

## 官方接口与授权

实际连通的 MCP 服务为 `https://open-agent.liepin.com/mcp/user`，通过 HTTP JSON-RPC 进行初始化、工具发现和调用。本轮仅调用 `initialize`、`tools/list` 和不带账号信息的 `user-search-job`；未调用任何简历修改或投递工具。

官方页面链接的仓库是 [liepin-tech-2026/liepin-cil](https://github.com/liepin-tech-2026/liepin-cil)。已核对其源码：默认服务根地址为 `https://open-agent.liepin.com`，凭据使用 `x-user-token` 请求头；CLI 封装 HTTP 请求，并不依赖 Playwright 或 Chrome profile。[配置实现](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/core/config.py)、[HTTP 客户端](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/core/client.py)。

官方 CLI 的只读入口包括 `GET /mcp/get-resume`、`POST /mcp/search-job`；投递入口为 `POST /mcp/apply-job`。MCP 则公开对应工具名。二者是同一官方接入方向的不同封装，不需要在项目里并行实现两套投递流程。[职位命令实现](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/cli/job.py)、[简历命令实现](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/cli/resume.py)。

官网当前说明：Token 有效期 90 天，重新生成会使旧凭据失效；搜索、查看、简历更新和投递共用每分钟 60 次的 API 额度。这些平台限制不代替项目每日最多 3 次确认成功投递的业务限制。[授权与使用限制](https://www.liepin.com/mcp/server#faq)。

Token 授权范围包含简历维护和投递，不能因为配置了凭据就默认开放这些写操作。第一阶段仅开放读取和岗位搜索。用户在官方页面完成登录和授权；凭据不进入聊天、运行日志、版本库或前端回读。

## 能力与缺口

| 项目需求 | 官方公开能力 | 仍需验证 |
| --- | --- | --- |
| 岗位发现 | HTTP 接口返回 20 个不同岗位；全部记录字段并集为 14 项；`jobType` 均为 `"2"`，有 `jobDetailUrl` | 完整 JD、岗位有效性和分页稳定性；本批未覆盖类型 `"1"` |
| 读取平台简历 | HTTP 接口 `errCode=0`；`data.result` 为 2901 字符文本，包含五类常见简历章节 | 不提供已核实的附件版本信息；不能按已展开的结构化对象消费 |
| 维护平台简历 | 基础资料、自我评价、教育/工作/项目经历、求职期望的新增或更新工具 | 官网 FAQ 的“仅补缺失”说明与工具的更新语义需要核实，不能假定不会覆盖已有信息 |
| 发起投递 | `user-apply-job(jobId, jobKind)` | 使用哪份平台简历、成功/重复/失败回执语义、幂等边界 |
| 指定本地 PDF 或简历版本 | 本轮 14 个工具及官方 CLI 投递模型均未声明文件、附件或简历版本参数；已登录网页支持多份附件 | API 是否发送已有附件及具体选择规则待确认；不能猜测隐藏参数 |
| 投递进展与 HR 回复 | 官网说明当前通过 App 消息和短信触达，Agent 查询进展属于后续能力 | 不应把现有 MCP 当作已经具备反馈查询接口 |

14 个工具名称：`my-resume`、`user-search-job`、`search-jobs`、`user-apply-job`、`modify-resume-base-info`、`modify-self-assess`、`add-edu-exp`、`modify-edu-exp`、`add-work-exp`、`modify-work-exp`、`add-project-exp`、`modify-project-exp`、`add-job-want`、`modify-job-want`。这些来自本轮实际 `tools/list`，不是根据第三方目录推定。

投递模型只有 `jobId` 和 `jobKind`；官方 CLI 将后者限制为 `1` 或 `2`，必须使用搜索结果提供的值，不根据职位 URL 猜测。MCP 元数据仅将其声明为字符串，因此项目侧需要按真实结果与官方模型进行校验。[官方投递模型](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/models/job.py)。

## 路线比较

| 路线 | 收益 | 成本与限制 | 本轮建议 |
| --- | --- | --- | --- |
| 官方 MCP/HTTP 的项目内适配 | 只读 HTTP 查询已实证；去除业务调用对浏览器调试会话的依赖 | 自行维护少量参数与错误映射；写操作及附件语义仍未验证 | 建议先做项目内只读 HTTP 适配，MCP 工具定义用作契约参考 |
| 官方 CLI 的子进程适配 | 复用官方命令、参数校验与 JSON 输出 | 需安装及打包依赖；退出码不能替代业务成功判定 | 与直接接口比较后选一种，暂不安装 |
| 普通 Chrome 人工操作 | 当前机器已有浏览器，可用于官方授权及人工兜底 | 单独使用不能达到无人值守每日投递目标 | 作为人工授权入口 |
| 原生界面/AppleScript 自动化 | 不要求使用 CDP | macOS 权限、窗口与 DOM 维护成本；已有搜索 helper 不等于完整登录和投递实现 | 保留现有能力，不扩建新主线 |
| 更换 Firefox | 可能改变页面检测表现 | 未安装、未验证，无法证明整个投递链可用 | 暂缓 |

未把逆向站内私有接口、修改网站安全脚本或读取日常 Chrome Cookie 列为推荐路线。现在已找到官方的 Agent 接入入口，优先解决公开契约与项目需求的差距。

## 仓库复用点

- `tools/infra/browser/liepin_session.py`：现有登录、检查都经 Playwright；适用于保留旧路线，不能当作官方 Token 的认证实现。
- `tools/engines/discovery/liepin_search.py`、`tools/infra/browser/liepin_applescript.py`：已经有普通 Chrome 的岗位搜索和结果归一化；新增官方数据来源时复用领域输入，不再新建候选模型。
- `tools/channels/liepin.py`：继续作为领域投递接口；授权开关、岗位确认和错误映射需要沿原入口接入。
- `tools/submission/storage.py`：保留本次调用真实结果落盘要求。现有必需步骤含浏览器专属步骤，接 API 时要定义适用的证据契约，不能伪造 `chat_send_resume` 等步骤成功。
- 现有 Gate/Review、PDF exporter、Job Lead bridge、排除规则和日志继续保留。更换传输方式不等于已实现跨运行防重、每日成功计数或调度。
- 在 `README.md`、`docs/`、`AIEF/`、`openspec/`、`tools/`、`ui/src/`、`tests/` 范围内未检索到官方猎聘 MCP、`x-user-token` 或 CLI 的既有接入。

## 下一验证顺序

1. 人工登录、取得 Token 和只读成功返回的核查已完成，不再重复运行当前探针；App 认证实现尚未替换。
2. 如进入实施阶段，先在现有 infra 与渠道边界内接入 Token 配置、简历文本读取和岗位搜索；按接口分别校验业务码与 payload。完整 JD、分页和过期/撤销行为仍需另行验证，不能为测试自行撤销现有凭据。
3. 明确简历投递语义：若只能发送平台当前在线简历，需先确认其与项目定制版本目标如何衔接；不能自动将本地 PDF 要求降级，不能循环覆盖平台简历后盲投。
4. 在版本语义和成功回执可核验后，再按既有门禁完成一个明确授权岗位的真实投递；网络超时或结果不明时不得自动重试写请求。
5. 最后才推进跨运行防重、每日成功计数与定时入口，保持已有每日合计 3 个不同岗位目标。

当前只读查询的成功样本已核实，失败码枚举、完整 App 接入与写操作仍未验证；P0-011 的 App 登录/会话验收和 P0-017 的真实投递完成状态均不因本轮调研而提升。

## 本轮浏览器操作

用户反馈官方凭据入口的验证码页面也会延迟跳空白。经用户明确授权，已通过原生 Chrome 设置页将当前实例的远程调试从开启改为关闭，端口 `9222` 的运行提示随之消失；未再调用 Chrome DevTools MCP。原状态为开启，可通过 `chrome://inspect/#remote-debugging` 恢复。

随后已用普通原生窗口打开官网声明的登录入口，初次观察时间为 `2026-09-08T15:52:27.551Z`。在 `2026-09-08T15:54:56.558Z` 再次仅通过原生界面复核：仍为官方登录 URL，手机号与验证码输入框存在，当前标签页未跳空白，未出现可见的滑动安全验证提示。前后间隔约 149 秒。这证明该设置下登录页能保持可见，账号登录结果仍待用户操作验证；未输入凭据、短信或验证码，未生成或重置 Token。

## 2026-09-09 登录后的新增发现

### 网站登录与 API 授权状态

用户报告人工登录成功。原生界面已实际确认个人首页 `https://c.liepin.com/` 可访问，并进入本人简历管理页。当时官方授权页的登录链接已变为“立即生成凭证”按钮，Token 区域仍显示生成前提示。随后用户确认已获取 Token；当前检查进程尚未配置 `LIEPIN_USER_TOKEN`，也未发现官方 CLI 默认配置文件。网站登录、用户取得 Token 与 API 验证成功仍需分开记录。全程保持远程调试关闭。

### 附件简历的产品规则

通过个人首页“附件简历”入口进入 `https://c.liepin.com/resume/edit`，仅查看上传说明后关闭面板，没有选择或上传文件。页面明确展示：

- 支持多份附件简历。
- 允许 PDF、DOC、DOCX、JPG、PNG，单文件不超过 20M。
- 上传会授权平台解析文件并完善在线简历，不能把上传看作完全不影响在线资料的纯文件存储。
- 主动投简历、发简历或同意招聘方索要简历时，附件会随在线简历发送；其他情况下招聘方不可见附件。

上述为账号内实际页面说明，仅记录规则，不保存账号标识、简历正文或附件内容。它支持继续验证“预先准备平台附件，再走官方 API 投递”的候选流程，但不能证明 `user-apply-job` 已遵守同样规则。当前仍未知：多份附件是全发、默认发还是逐次选择；是否可锁定某个版本；API 回执是否包含实际简历/附件标识。

### 官方 CLI 的成功输出边界

继续核对官方 `core/output.py`、`cli/common.py` 与 `tests/test_cli_job.py`：通用输出器对空返回值可显示“成功”，调用层主要负责请求、参数校验和输出；投递测试中的 `{"ok": true}` 来自 Mock。它们都不能作为真实平台投递成功回执的契约证据。项目适配层仍需依据经过验证的业务结果判成功，不得只看退出码、空响应或字面提示。[输出实现](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/core/output.py)、[命令公共实现](https://github.com/liepin-tech-2026/liepin-cil/blob/main/liepin_cli/cli/common.py)、[投递命令测试](https://github.com/liepin-tech-2026/liepin-cil/blob/main/tests/test_cli_job.py)。

### 已准备的只读检查工件

`outputs/acceptance/liepin_official_api_20260909/read_only_probe.py` 仅允许向官方 HTTPS 来源调用 `GET /mcp/get-resume`、`POST /mcp/search-job`，拒绝重定向，不自动重试，不提供投递或简历修改入口。Token 通过本机终端隐藏输入，不保存；结果只保存字段结构、类型、数量、HTTP 状态及限定的业务码/岗位类型编码，不保留简历正文、岗位正文或岗位 ID 值。错误正文不回显。

已执行 `--self-test`，验证脱敏、重定向拒绝及写接口白名单阻断。用户随后通过本机终端隐藏输入 Token 执行探针，取得下述首批只读响应；Token 未粘贴到聊天或写入全局配置。该检查不依赖安装官方 CLI。

## 2026-09-09 首批带 Token 只读响应

证据：`outputs/acceptance/liepin_official_api_20260909/readonly-20260909T141232268064Z.json`；记录时间为 `2026-09-09T14:12:32.268064+00:00`。原始报告保持不变。

| 接口 | 本次实际响应结构 | 接入影响 |
| --- | --- | --- |
| `GET /mcp/get-resume` | HTTP 200；根字段为 `errCode` 和 `data`，内容在 `data.result` 字符串中，长度 2901 | 不能按已展开的结构化简历对象消费；格式和附件信息需进一步识别 |
| `POST /mcp/search-job` | HTTP 200；根字段为 `code` 和 `data`，`data.list` 含 20 条记录 | 两个接口的业务码键名不同，需要分别归一化 |
| 搜索采样的两条岗位 | 均有 `jobId`、`jobType`、`jobName`、`company`、`location`、`salary`、`education`、`workYears`、`industry`、`companyTags`、`financingStage`、`companySize`、`companyLogo`、`jobDetailUrl` | 岗位类型名称与投递入参 `jobKind` 不同；摘要具备候选岗位输入基础 |

两条采样中没有独立的职责或任职要求字段；不能把这些摘要当作完整 JD，也不能据此断言其余 18 条一定相同。必须沿返回的详情来源或其他明确的官方能力补齐 JD。

V1 探针把所有数值脱敏，导致 `errCode` / `code` 的实际值无法还原；这属于探针的证据采集缺口，不是用户操作失败。`business_success_verified=false` 是探针预设的保守标记，并非猎聘返回的失败字段。

已将临时探针升级为 V2：仅额外保留数值业务码、明确布尔标记及已知岗位类型编码；识别简历字符串的文本/JSON 形式，若为 JSON 则仅提取脱敏结构；遍历全部返回岗位，记录字段并集、ID 去重数量和未识别类型计数。依然不保存 Token、简历原文、岗位正文或岗位 ID 值。

先加入复现缺口的本地检查，再补齐采集逻辑；V2 的业务码保留、正文脱敏、字符串识别、全部岗位字段汇总、禁止重定向及禁止写请求检查均通过。用户随后执行 V2，补证据结果见下节；两个原始报告均保持不变。

## 2026-09-09 V2 只读验证收口

证据：`outputs/acceptance/liepin_official_api_20260909/readonly-20260909T142034159157Z.json`；记录时间 `2026-09-09T14:20:34.159157+00:00`（北京时间 22:20:34）。

| 核查项 | 结果 |
| --- | --- |
| 简历接口 | HTTP 200，`errCode=0`；`data.result` 长度 2901，不可直接解析为 JSON，按文本消费 |
| 简历章节 | 检测到基本信息、工作经历、项目经历、教育经历、求职期望；未命中预设的附件关键词 |
| 搜索接口 | HTTP 200，`code=0`；20 条对象记录，20 个不同岗位 ID |
| 岗位类型 | 全部为字符串 `"2"`，未识别类型计数为 0；与官方投递入参允许的编码范围一致 |
| 全部岗位字段 | 字段并集为前述 14 项，只有摘要与详情链接，没有独立的职责/任职要求正文 |
| 操作范围 | 未调用写接口，Token、简历/岗位原文和岗位 ID 值未保存 |

结合 0 业务码、符合用途的 payload 结构与非空数据，本次两个只读调用可判为成功样本。报告内的 `business_success_verified=false` 仍是探针固定标记，不是服务端失败结论；此处人工复核结论不回写或篡改原始记录。

字段映射可按本批实际数据确定为搜索 `jobType` → 投递 `jobKind`，值按原样传递并校验官方枚举；不得把所有岗位硬编码成 `"2"`。类型 `"1"`、跨页及跨运行去重、实际投递结果仍未验证。

未命中附件关键词只能说明本次简历文本没有被探针识别出的附件说明，不能据此断言平台不支持附件或其他账号一定返回相同内容。官方投递未暴露附件选择参数的缺口仍然存在。

本轮无需用户继续重复输入 Token。剩余工作应聚焦完整 JD 获取、具体简历/附件版本绑定和真实投递回执，之后再按既有阶段推进每日自动投递；本轮没有实施业务接入或解除投递阻断。
