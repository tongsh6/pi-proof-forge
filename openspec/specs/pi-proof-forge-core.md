# PiProofForge 核心 Pipeline 规范

**状态**: active  
**版本**: v1.0  
**创建日期**: 2026-03-02  
**所有者**: pi-proof-forge team

---

## 概述

PiProofForge 是一个 evidence-first 框架，将原始工作材料（日志、PR、报告、截图等）转为结构化证据（Evidence Cards），再通过可解释匹配生成事实保真的目标文档（简历等）。

系统目标不是维护一份所有岗位通用的静态简历，而是基于用户真实个人资料、工作经历和 Evidence Cards，结合目标公司、岗位 JD、must-have、seniority signal、业务场景和简历定位，生成可投递的候选人简历版本。同一版本可以复用于同类岗位或同一目标岗位簇，但不得被定义为“一份简历投所有公司/岗位”。

---

## 核心实体规范

### Evidence Card

```yaml
schema: evidence_card_v1
required_fields:
  - id          # 唯一标识，格式：ec-YYYY-MM-DD-NNN
  - title       # 简短描述
  - raw_source  # 原始材料路径或引用
  - results     # 可量化的成果（必填，否则不进入候选池）
  - artifacts   # 关联产出物（必填，否则不进入候选池）
optional_fields:
  - tags        # 技能标签
  - period      # 时间范围
  - context     # 背景说明
```

**约束**：`results` 或 `artifacts` 任意一项缺失，该 Evidence Card 不进入匹配候选池。

### Job Profile

```yaml
schema: job_profile_v1
required_fields:
  - id          # 格式：jp-YYYY-NNN
  - title       # 岗位名称
  - keywords    # 关键词列表
  - level       # 级别信号（junior/mid/senior/staff）
optional_fields:
  - tone        # 语气偏好
  - must_have   # 硬性要求
  - nice_to_have # 加分项
```

### Matching Report

```yaml
schema: matching_report_v1
required_fields:
  - job_profile_id    # 关联岗位
  - evidence_cards    # 入选证据卡列表（含分项得分）
  - gap_tasks         # 缺口任务列表
  - score_breakdown   # 各维度得分（必须可解释）
```

---

## Pipeline 阶段规范

### 阶段 1：证据提炼（Evidence Extraction）

**输入**: 原始材料文件（txt/md/pdf）  
**输出**: Evidence Cards（YAML 格式）  
**工具**: `tools/run_evidence_extraction.py`（推荐入口） / `tools/extract_evidence.py`（底层规则脚本）  
**约束**:
- 不得推断或补充原材料中没有的信息
- 每个 Evidence Card 必须有明确的 `raw_source` 引用

工作目录材料接通（2026-10-05）：复用材料库已有 `# Source:` 文档边界，为已导入的 TXT/Markdown 提供按名称筛选、选择原文片段和预览；只读取库内已有材料，不追踪原文里的本机路径或指令。模型提炼使用选中的有界文档（单次最多 24000 字符），过大时明确要求选择较小片段，不静默截断全文，不把 998 文件目录直接塞给模型。继续复用现有提炼草稿、人工审核、results/artifacts 来源校验和保存入口；新草稿记录所选文档标识/指纹，保存时重验内容未变且结果确实来自该文档。未审核卡不得进入生成。文档中的任务指令仅为数据，不能成为执行指令。

### 阶段 2：匹配评分（Matching & Scoring）

**输入**: Evidence Cards + Job Profile  
**输出**: Matching Report  
**工具**: pipeline 内部逻辑  
**约束**:
- 所有评分维度必须有对应证据支撑
- 缺口任务必须明确列出（不得静默忽略）

### 阶段 3：文档生成（Generation）

完整职业简历实施（2026-10-05，用户已确认开工）：
- 沿用 `personal_profile.yaml` 作为唯一职业档案，保留原五个基础字段与未知扩展字段；新增有版本的 career_json 结构，包含可编辑职业摘要、工作/合作经历、教育背景及展示选择、分组能力和可验证补充成果。工作条目包含稳定 ID、实际公司/部门/职务、年月起止/至今、业务与职责范围、具体贡献及关联证据 ID；客户品牌不自动用作任职公司。
- 草稿允许信息不全，保存仅持久化事实，不自动确认。确认档案需完整基础资料、至少一段完整工作经历及教育资料或显式选择不展示；关联证据必须已审核且存在。年月必须有效且顺序正确，空值与不展示区分。确认绑定档案内容指纹；后续事实修改使确认失效，乐观并发检查阻止旧表单覆盖新内容。
- 生成沿现有 CLI/Quick Run 组织：基本资料与目标 → 职业概述（用户摘要或已确认职位/工作范围归纳）→ 分组能力 → 工作履历 → 与履历关联的代表项目 → 教育 → 可选补充成果。保留按 JD 选材的 A/B 与字段级追溯；未关联、未审核或缺职责/时间的经历明确缺证据，不能生成虚构年限、管理规模、学历或业绩。不为凑一页删履历，允许自然续页。
- Quick Run 持久化实际导出 PDF 及导出时正文/trace 指纹，暂存证据须与档案已确认版本一致；复用投递记录页已有的固定快照、预览及批准上传入口完成内容确认，不新增审批页或审批队列。完整职业档案确认、当前源指纹与目标完整性、正文结构及项目关联通过后才可准备，批准绑定 Markdown/PDF/trace/职业档案和目标版本，记入原审批队列。资料或文件变化、旧稿缺新内容记录须重新生成/审核。
- App 准备新的 PDF 投递、上传、最终发送及每日清单均复核上述内容批准；仅生成 DONE、规则高分或人工上传同意不足以绕过。旧成功日志/快照及只读回执、附件移除保持可读，不重写历史。默认平台简历的新投递同样要求确认职业档案且批准正文覆盖完整履历，防止绕过内容要求；本轮不新增实际投递。

App 内岗位定制与候选准备衔接（2026-10-08）：
- Jobs 已保存且 active、包含完整 JD 原文的画像提供“生成定制简历”，仅导航并带入该画像；不自动生成。Quick Run 显示原 profile.get 的档案就绪状态，缺确认时引导简历中心；链接目标不存在、已归档或 JD 缺失不得静默回退到其他岗位。
- Quick Run 完成后，仅内容完整、追溯有效且已导出 PDF 的本次结果提供“查看并准备 PDF”；将精确 Quick Run 编号带入原 Submissions 页面。切换岗位、材料、证据或定位清空旧结果；运行中禁改输入，晚到响应不能覆盖新选择。
- 原生 PDF 候选进入 Agent Run 后只提供返回其原 PDF 审核页的入口；通用 submitReview 拒绝修改该队列或调用通用投递，避免混用审批路径。getPendingReview 从原队列提供 native_pdf_quick_run_id，不另存路由状态。
- Submissions 链接参数仅预填运行编号，仍须用户点击原固定按钮，复用后端完整内容/岗位/重复投递门禁。不得因页面加载、导航或带参自动准备、批准、上传或发送。固定成功且仍 prepared 时提供前往原每日候选清单入口，不自动勾选候选或启用授权；空清单提供回 Jobs 的入口。

**输入**: Personal Profile + Matching Report + Job Profile/JD + 选定的 Evidence Cards + resume positioning
**输出**: 候选人简历文档（markdown/pdf）+ 独立追溯记录
**约束**:
- 严禁生成无证据支撑的内容
- 语气调整不改变事实
- 候选人可见简历必须包含姓名、联系方式、城市、当前定位、目标岗位定位、核心技能和结构化经历；缺少 Personal Profile 或经历结构时不得标记为可投递
- 简历内容必须围绕目标公司/岗位要求组织，覆盖 Job Profile/JD 中的 must-have、关键词、seniority signal 和业务场景；允许同一版本复用于同类目标岗位簇，但必须记录适用范围
- 审计追溯信息必须写入 `resume_trace` / run record / scorecard，不得把 `Evidence trace`、本机路径、source report、内部 evidence id 或系统版本标题写入候选人 PDF 正文
- Scorecard 未达可投递阈值或仍有必需 gap tasks 时，生成结果必须进入 `NEEDS_REVIEW` / `NEEDS_EVIDENCE` 状态，而不是作为可投递简历

本轮 Quick Run 增量（2026-09-05）：
- 复用现有 generation CLI，增加 Personal Profile、Job Profile/JD 和定位输入；默认个人资料取自简历中心的 `personal_profile.yaml`，不另建资料库。
- 模板正文仅拼装个人资料及选中证据字段；目标公司/岗位以求职意向呈现。LLM 首版仅返回候选证据 ID 的选材/排序结果，拒绝未知 ID 和自由生成的无依据正文；不依赖提示词保证事实保真。
- 每份 Markdown 同目录保存 `.trace.json`，记录输入指纹、字段级来源、正文 SHA256 和待补信息。追溯从该文件读取，禁止通过向简历正文塞入 evidence id 来通过检查。
- Quick Run 返回独立的 `resume_readiness`：缺资料、缺目标上下文或缺证据为 `NEEDS_EVIDENCE`；生成完成但待人工审核、评分不足或存在缺口为 `NEEDS_REVIEW`。pipeline 的 `DONE` 仅表示执行结束。

生成质量验收补齐（2026-10-05）：
- App 的交付目标是基于真实个人资料与完整目标 JD，自动选材、组织为可审核的定制简历，并形成 A/B 版本、PDF、质量结果和独立追溯；必须通过 App 实际生成验证，人工另写一份 PDF 不能替代产品能力。
- 经历应表达业务场景、本人角色/时间、具体行动及已有结果/产出。方案设计、测试环境验收与生产上线必须保持原有证据级别，需求预期不能改写为已达成业绩。A/B 的差异由已有事实的选取与排序体现，资料不足时允许相同，不编造差异。
- 场景字段进入正文，行动按目标关键词与既有定位排序，完整保留选中事实句子并避免重复；技能只来自已审核证据。内部追溯与待补清单留在 App 质量区，不写进候选人正文。
- 缺少技能依据，或所选经历缺场景、本人角色、起止时间、具体行动时，记录 `missing_evidence_fields` 并保持 `NEEDS_EVIDENCE`。App 指出具体待补项，不能因 PDF 成功、字数增加或规则高分将其升级为质量通过。工作/教育背景没有资料时不补写，不用项目文档日期冒充任职时间。
- 一页优先，以完整可读为准；长经历允许自然续页，禁止为塞入一页缩成难读小字或截断正文。标题不孤悬、日期与项目标题清晰分层、正文可复制无乱码；章节顺序与源 Markdown 一致，预览/PDF 使用同一模板。
- 低匹配岗位用于闭环验证的授权独立于简历质量验收；发送成功不证明成品质量合格，也不允许把目标 JD 中未掌握的技术写为本人经验。新增授权清单准备优先使用本次改进版本，旧已发送快照不覆盖。

正式排版增量：
- 预览与 PDF 共用受控的 HTML/CSS 模板，复用现有 Markdown 预览解析器；用户文本必须转义，不执行脚本或加载远程资源，未识别的附加章节不得静默丢失。
- 默认优先使用本机已有 Chromium Headless Shell / Chrome，保留已安装 WeasyPrint 的可用路径；不自动安装依赖，不静默降级为纯文本 PDF。
- 缺少渲染器、超时或输出损坏必须明确失败且保留已有 PDF；渲染使用隔离临时目录、有界超时和进程清理，完成后原子替换目标文件。
- `resume.getPreview` 增量返回 `preview_html`，旧结构化 `preview` 保持兼容；GUI 在现有预览区显示同一 HTML，限制脚本、导航和远程资源。

### 阶段 4：质量评估（Evaluation）

**输入**: 生成文档 + 原始证据  
**输出**: 质量评分报告  
**约束**:
- 每项质量分必须可追溯到具体检查点

### Agent Loop 扩展阶段（用于 Autonomous Agent）

以下阶段属于 Agent 编排扩展，不改变核心 pipeline 的 evidence-first 约束：

- `DISCOVER`：从 `job_leads` / `jd_inputs` / `evidence_cards` 推导候选方向与 JD
- `GATE`：联合判定 matching / evaluation / channel readiness
- `REVIEW`：投递前审批（auto 模式 pass-through；manual 模式暂停展示 TopN 候选，等待用户 approve/reject/skip）
- `DELIVER`：通过通道执行投递
- `LEARN`：根据本轮失败原因调整下一轮输入与策略

约束：
- 扩展阶段不得绕过 Evidence Card 校验与事实保真约束
- 所有投递与门禁结论必须写入可追溯 run log
- policy 必须支持企业例外清单（company exclusion list），用于排除不应进入投递链路的目标企业
- 企业例外清单应在 `DISCOVER` 阶段主过滤，在 `GATE` 阶段做兜底校验
- REVIEW 阶段在 auto 模式下为 pass-through，不影响既有行为；manual 模式下暂停等待用户决策

---

## CLI 接口规范

### 招聘平台接入契约（2026-09-27，待实施增量）

本节定义新接入的目标契约；2026-09-28 官方只读 P0-011 已接入并通过真实原生验收，投递及多平台增量仍待实施，旧浏览器/CLI 路线保留兼容。实施次序以 `docs/execution-roadmap.md` 为准，依据见 `AIEF/docs/plans/2026-09-27-recruitment-platform-integration.md`。

- 正式覆盖六平台：猎聘、BOSS直聘、智联招聘、前程无忧 51job 为核心来源，脉脉、拉勾为补充来源。六家均进入计划与验收范围，后续按平台单独记录进度，技术阻塞不自动删除目标。
- 六平台共同最低能力为可追溯岗位输入、完整 JD、画像审核、可解释匹配、定制简历版本关联和结果追踪；每平台至少 1 个真实来源样本验证。入口复用现有 Jobs/Quick Run/Submissions，不因平台扩展增加独立业务流水线。
- 四家核心平台目标包括在线只读搜索与详情；脉脉、拉勾首版采用职位链接和完整 JD 导入。来源覆盖、在线只读、真实投递、平台反馈同步分别验收；人工导入/手工反馈须标明来源，不能满足在线接口或投递成功验收。
- 猎聘官方 HTTP 为首选传输；CLI/MCP 不与 HTTP 平行实现第二套业务流程。第三方 BOSS/智联工具须固定经核对的版本，并以该版本能力清单决定可用平台；不假设最新版保留旧平台。
- 认证 readiness 按实际传输验证：官方 Token 由后端只读调用确认；浏览器由真实会话确认。不得用浏览器 profile 存在代替 Token 有效，也不得伪造浏览器步骤满足 API 通道验收。
- 官方岗位摘要导入须保留上游 `salary` 与 `location` 原文并在岗位线索中展示，供本批低匹配/高待遇筛选使用；缺失显示未提供，不推算工资或将薪资上限当保证收入。重新搜索更新这两项，同时保留既有完整 JD、审核和画像关联；未知字段类型明确拒绝导入，不把结构化对象转成伪薪资文本。
- Token 仅进入后端受控凭据通道，并仅向核实的官方 HTTPS 请求注入认证头；前端回读只显示配置/验证状态，日志/审计中的请求头副本必须脱敏，子进程参数、产物与版本库不含密钥。首个切片仅允许岗位搜索和简历读取，不开放简历修改、聊天、投递或反馈写操作。
- 2026-09-28 用户指定猎聘 Token 不接入钥匙串，接受本地明文权限文件。macOS 固定保存到 `~/Library/Application Support/PiProofForge/credentials/liepin-token`，凭据目录 `0700`、文件 `0600`，不随工作目录或调试 App 标识变化；不写入仓库、普通配置、前端持久化或日志。拒绝符号链接、非普通文件及不安全权限；写入须原子替换，失败明确返回且不得假报成功。
- 凭据在后端首次使用时从本地文件恢复为 `unverified`，只有真实只读请求通过才为 `valid`；正常退出只释放内存，用户主动删除才删除文件。保存/读取/删除失败返回 `CREDENTIAL_STORAGE_ERROR` 固定安全信息，删除失败不得显示已删除；非法新输入不得销毁原有保存项。测试必须使用隔离目录与合成 Token，禁止读取或清理用户真实凭据。
- 复用 Job Lead/Candidate/Job Profile；补齐平台、稳定岗位 ID、平台原始岗位类型、详情引用、获取时间与 JD 完整性。猎聘 `jobType` 按原值校验后映射到 `jobKind`，不得硬编码；列表摘要不能当完整 JD，无法获取正文时走人工补齐和审核。
- 适配器校验 HTTP/CLI 传输结果、业务码/`ok`、payload 三层。`ok=false`、非 JSON、认证失效、空数据和平台不支持分别表达；不得将错误对象映射为岗位，也不得静默降级为“在线查询成功”。
- `DeliveryRequest` 必须使用明确的平台路由，业务方向不能充当渠道。仅配置读取来源不启用该平台投递。结果未知时不自动重试写请求、不切换邮件补投；其他跨渠道发送也必须在授权范围内。
- PDF 版本/指纹、平台实际发送的附件或在线简历身份、审批记录须可关联。接口只有岗位参数不构成版本绑定证据；无法核验时保持阻断，不自动覆盖在线简历或降低为默认平台简历。
- 复用 `SubmissionRecorder` 与 External L3，新增适合 API 的认证、目标、版本绑定、提交和回执证据契约；未知/失败/重复/成功分别记录。无权威业务成功依据时 `DeliveryResult.success=false`。Token 接入不得沿用“原始密钥 env 进入 L3 模板”的做法，应通过后端凭据引用解决。

#### 真实投递结果与反馈收口（2026-10-01）

- Submissions 详情统一展示两条 App 路线的审批运行、岗位、简历版本/指纹、回执来源与本地证据完整性。完整性检查只读已有批准快照、业务回执和 SQLite 尝试记录；缺失、被改动、结果未知或仅外部观察时不得显示核验通过，也不得改变原投递状态或补发。
- External L3 增加显式的已存 App 投递验收入口，复用相同证据检查及原真实页面证据。该入口只接收提交编号，始终禁止新网络提交；旧浏览器实时执行入口保留独立适用范围，不能以其 session/PDF 门禁阻断官方 API 历史记录。报告保存原日志、快照与回执指纹，不复制凭据、招聘者标识或签名 URL，不改写原日志来制造反向链接。
- 真实发送结果使用 `submission_receipt` 反馈来源，不冒充 check-mode 结果。用户在选定投递记录后可填写人工招聘反馈或个人复盘，明确标记来源；系统不得自动编造招聘者评价、回复或已读事实。反馈记录从服务端绑定原提交/审批/岗位/版本/回执，重新进入页面可读回；客户端提供的其他提交反馈不得混入当前记录。
- 对受控真实投递，反馈动作记录为下一轮计划，可指向原岗位画像、证据补全或 Quick Run；不复制同一 PDF 冒充重新生成版本，不更改旧简历、审批、回执或额度。实际再生成仍使用现有 Quick Run 与审核链，反馈保存不会自动发起生成或投递。原检查模式兼容入口保留。

#### 生成 PDF 补充授权与原生登录兼容性（2026-09-30）

- 2026-09-30 用户明确“允许”平台上传自动解析补全在线简历，并接受附件随后续投递附带。沿用额外 1 次 PDF 实投授权；默认十岗不得重开。此次可将已展示的已授权测试 目标 PDF 固定为只读快照，经 App 明确批准上传后执行一次账号附件上传。
- 原生上传适配只接收受审核运行引用；后端验证真实生成追溯、Lead/Profile 和文件指纹，不能由前端提供任意本机文件/脚本。上传开始前持久化 in-flight 状态，未知不自动重传；上传成功与岗位投递成功分别记录。平台附件标识及内容绑定无法核验时，不调用岗位发送。所有观察由 App 执行并保存有界脱敏证据，不以开发者网页点击或人工填成功回执替代。
- 当前真实前端限制文件名（含后缀）不超过 24 字符。旧适配器生成 27 字符名称且没有上传响应时，只有 App 观测到同一官方资源版本，并只读核实其 SHA256 与上传前拒绝规则，才可把该次未知归类为客户端未发送；保留原观测和版本依据。修正短文件名后沿同一批准快照继续，不重新批准内容、不把校验恢复算成功。
- 附件绑定以发送前本机字节 SHA256、浏览器上传成功响应的 filePath/长度、附件保存成功和当前唯一附件记录的 fileId/encryAttachmentId/文件名/长度共同证明。回读下载是额外核验，403/CORS 不冒充字节回读成功；若成功回读却 hash 不同必须阻断。岗位投递仍须核对目标、具体附件及独立业务回执，上传成功不能代替。
- 目标页仅提供“聊一聊”时，App 在进入沟通前核对最新 JD/审批快照/附件绑定并取得既有 SQLite 的 generated_pdf 单次占位；进入沟通可能包含平台自动招呼，属于同一次已授权流程。阶段观测与最终附件发送分开记录，打开沟通不算 PDF 成功；跨重启不得再次点击开始沟通，未知占用名额且不得换岗重试。
- 最终发出请求时绑定随发送历史冻结，`final_send_pending` 与 `success` 阶段的当前附件检查不得覆盖或删除它；历史回执核验只读既有证据。签名附件 URL 仅可在 WebView 下载内存中保留，序列化和后端落盘均去 query/fragment，包含嵌套 JSON 字符串；不将签名写入审批/运行产物。
- 2026-10-01 新增多岗位真实验证：账号可保留多份附件。绑定须在上传成功所指 fileId、批准文件名/长度和当前附件卡片之间唯一匹配，再核对下载字节；不得依赖账号仅有一份附件，也不得选账号默认项代替目标文件。进入发送确认框后，App 仅可选择唯一匹配已批准 fileId 的单选项；最终发送仍重新检查该选择、岗位和会话。重复身份、缺失或内容不符保持阻断，历史已发送绑定不变。
- 平台上传后可自动转到 `/resume/parse-result`。App 检查会话时仅在这个固定官方页面且没有登录表单/安全验证时，正常导航回 `/resume/edit` 并重新检查正向登录信号；不确认、跳过或补写解析表单字段，不把原解析页 URL 当认证成功。其他未知页面、空白、登录与安全验证保持原阻断。
- 用户单独确认后，App 可移除自己已成功投递并留存完整证据的某份平台附件。前端只传批准运行编号和明确确认；后端重验原 PDF/回执、当前唯一卡片及下载指纹，开始前持久化占位。App 只打开该 fileId/encryAttachmentId 卡片的删除菜单及已核实的不可恢复确认框。只有精确移除接口的业务成功回执和“仅目标文件消失、其他文件保留”同时成立才记为 removed；未知不重试。删除仅影响平台附件，原简历快照、投递回执、成功状态及额度保持不变。
- 移除的发送前守卫须在任何菜单点击前安装：仅最终确认之后、固定移除端点、单一批准 encryAttachmentId 的一次 POST 可放行；错误 ID、重复参数、重复请求和其他简历写端点不得交给原网络发送函数。不能仅在错误请求已经发出后才把结果标为 unknown。
- 官方 JSON 请求库会封装 `{data:{encryAttachmentId}}`；守卫只识别此单一字段封装或已验证的等价平面参数，拒绝重复 data/身份键及冲突字段。若结果未知，仅在保存的守卫记录明确 `allowed_requests=0`、有被拦截请求、无网络回执、附件集合原样，且新检查证明同一附件/原字节仍在时，允许只读核验为 not_submitted；保留原 unknown 事件。任何已放行请求、附件缺失/变化或证据不完整仍未知，不能重删。

- 用户在十岗批次结束后明确“授权”，本次范围为新增 1 次生成 PDF 的真实发送验证。只有具体岗位和批准 PDF 的身份绑定成立后才执行；独立保存补充授权，不能重置原十岗批次，不能将该名额用于默认平台简历。
- 既有对照显示建立浏览器调试连接与登录页跳空白相关。允许复用 App 自带 Tauri WebView 验证普通网页登录兼容性，不安装/更换浏览器、不使用指纹伪装、不屏蔽网站验证或重定向。初始入口只负责登录与只读页面观测，不能上传、聊天或投递。
- 猎聘远程窗口必须与主业务界面隔离；所有本机敏感 host command 仅主窗口可调用，远程网页不得调用 sidecar、访问文件或取得 Token。网页观测只返回固定字段和无 query/fragment 的官方来源，不能接收前端自报登录、任意脚本、任意 URL 或凭据。
- 登录、密码、短信和验证码由用户在 App 独立窗口手动完成。程序只有取得官方页面正向登录信号才能认定有效；空白、安全验证、只看到职位 URL 都不能升级会话。
- 附件只读检查允许由 App 打开已观察到的“附件简历”管理入口、关闭对应功能介绍；只返回文件控件格式和有限操作提示，不读取文件内容或网站凭据。导航至管理页面后再次检查；不把支持 PDF 格式视为已上传或已绑定版本。
- `/resume/edit` 上已核实的“经历可同步至在线简历中 / 无需手动填写，可直接添加到在线简历中”提示可由 App 关闭其唯一 Close 控件，再继续附件只读检查；不点击“立即查看”、不确认同步、不填改在线经历。未知、歧义弹窗及解析表单页不适用。
- 现有工作目录导入生成 `.txt` 汇总材料时，允许在 Evidence 页显式手动整理证据草稿，引用同一上传材料及其可核实原文；`.md` 模型提炼路线保持原约束。手工稿必须经原审核保存和 results/artifacts 来源校验后才能进入候选池，不能把旧未审核卡或没有依据的数字直接升级为可用证据。
- PDF 生成复用现有材料/简历 pipeline、exporter 和不可变审核快照。只有文件内容与平台实际上传附件、目标岗位、发送回执可追溯时才能记录此路线成功；兼容性登录试验通过不等于 PDF 路线完成。
- PDF 文件名（2026-10-08）：Quick Run 自动 PDF 与简历中心向目录导出的生成简历，统一使用 `姓名-公司-岗位-YYYYMMDD.序号.PDF`。姓名与目标取该版本正文/追溯，日期为首次命名的上海日期，序号从 1 开始；同名目标同日的新版本在工作区内递增，同一版本重复导出/重启沿用原名。复用原导出器与文件锁，非法路径字符清理、超长组件按文件系统限制缩短；缺项使用“未填写姓名/未指定公司/未指定岗位”，不猜事实。显式指定的导出文件路径仍尊重用户输入。
- 用户确认公司和岗位可用简称：优先保留姓名、日期和序号；名称超出猎聘 24 个 UTF-16 单元时，公司可去常见地域前缀/公司后缀、岗位可去级别前缀/工程师后缀，再按剩余长度保留两者可读前缀。简称碰撞仍递增序号，正文与岗位身份不改。无法容纳姓名、最少各一字的公司/岗位和日期序号时保留本地名并在启用/上传前明确阻断，不退回指纹名。
- 新准备的 PDF 将可读文件名与原批准快照绑定，上传继续使用此名称；仍超限时在批准/上传占位前给出明确错误，不重复上传。已准备/批准的旧快照、已上传附件、回执和持续授权范围不迁移，保留原命名兼容；内部快照路径和防重标识不作为用户文件名。
- Quick Run 显式选择实际材料，并复用已有 `material_id`、`use_llm`、`require_llm` 参数；默认模板拼装，用户可选择模型润色。不得把列表首项验收样例显示为实际工作材料，也不得在仅需模板时强制等待模型。只有审核可用证据进入生成。
- PDF 验证须同时检查视觉和可复制文字；中文姓名/正文不得因字体 ToUnicode 映射退化为偏旁字符。优先使用本机已有且经验证的字体，不为此安装或修改系统字体配置。

#### 审批快照与恢复执行（P0-017A 增量）

- 近期 10 岗位测试授权按实际外部尝试累计，不按 App 验收通过数重新计算。已有 2 次真实投递（含 1 次外部观察确认）占用同一批次，最多再发送 8 次；默认简历与 PDF 共用持久化批次上限。未经新授权不得因某次未达到 App 验收标准而追加第 11 次。
- 沿既有 SQLite 防重库保存批次授权上限、已发生尝试引用与占用数，发送前在同一事务内检查批次剩余额度并占位，跨运行/并发/重启保持约束。未知占用名额且暂停批次；明确未发送的前置失败释放新占位，实际发送的成功/失败保留。批次配置重复应用必须幂等，不能自动重置或提高上限。
- 2026-09-29 用户纠偏：目标是 App 产品自身完成选岗、准备、审批、发送、回执与追踪；外部电脑控制仅可用于操作 App 做验收，不得代替产品去操作招聘网站、发送消息/附件或补写成功。既有外部观察可保留为人工来源事实，但不计 App 自动确认或闭环验收；真实已投递的防重记录仍须保留。
- JD 模型提取采用有界结构化输出：LM Studio 单次输出预算、各供应方共同的字段长度和条数上限，保持岗位原文语言，不重复输出 App 已持有的 JD/来源 URL。预算截断或超限拒绝作为可审核稿，不自动重试。原 JD 与来源由 App 保存；绑定官方线索时岗位名称/公司以该线索为准，模型不得擅自增加 Senior 等资历或改写公司身份。
- 完整 JD 已取得而模型解析不可用时，Jobs 提供显式“手动整理画像”入口，复用原来源绑定与审核保存；只预填来源职位名称，摘要、必备要求和关键词由审核者填写，不编造模型结果或绕过完整性校验。模型稿也可在同一审核区修正这些字段。
- 默认简历准备必须由职位页经 App RPC 发起：后端读取已审核 Lead/Profile、检查排除名单与历史投递、读取当前平台简历并建立保护快照和待审批运行；准备本身不投递。前端只传 Lead ID，不接收/注入 Token、平台岗位 ID 或快照正文；同一未变化的待审批项可复用，进入审批页必须绑定返回的明确 run_id。
- 结果分别展示真实确认数、App 自动确认数与外部观察确认数。外部来源的确认不能显示为 App 自动完成；缺乏程序可核验回执仍作为产品缺口，不以手工写 JSON 或网页观察替代。

- 2026-09-28 用户明确“都试下”：允许分别验证平台默认简历与项目生成 PDF，先前指定的既定测试岗位作为平台默认简历首笔；两条路线不得向同一岗位重复发送。平台默认简历使用显式 `delivery_kind=platform_default`，保存发送前观测文本与指纹并即时重读核对；该快照不冒充平台端锁定版本，也不声称发送了生成 PDF。生成 PDF 路线保留原附件绑定要求，不静默降级。
- 2026-09-29 回执收口：App 在每次已授权的单次发送中保留可重新解析的业务响应证据，单独存于该次 submission 目录的受保护文件（目录 0700 / 文件 0600），绑定运行、岗位、简历指纹和响应指纹。只保留回执相关字段，排除请求头/凭据，普通日志、RPC 与 UI 不回显原始响应；业务摘要记录解析版本、判定原因与证据指纹。旧响应只有 hash 时不得凭空重建成功。
- 旧 API 尝试仅有完整响应 SHA256 时，可引用 App 后续实际接收且已保护落盘、完整响应 SHA256 完全相同的业务响应作为解析证据；必须验证双方日志/回执指纹、旧请求的审批快照和尝试身份，只引用已有文件，不伪造旧接收文件，不再次发送。自身证据存在但损坏时不能以引用方式绕过。找不到精确匹配、响应包含不同岗位身份或只是外部网页观察时保持原结果。该程序确认与原人工观察分别留痕，真实尝试计数不增加。
- 回执解析允许有界解包 `data.result` 内 JSON 字符串，明确业务成功语句可容纳句末标点；HTTP/外层零码、通用 success/ok、重复投递提示、冲突或未识别内容均不得作为新成功。保留失败与未知区别，未知继续占位且不自动重发。
- App 审批结果提供 `run.agent.recheckReceipt({run_id, job_lead_id})`，只读取本机已保存的 API 响应并重新判定，绝不发送、访问网站或接受前端上传的成功结论。校验受保护证据指纹及快照/岗位/尝试绑定后，才允许把 unknown 更新为明确 success/failed；原始未知事件保留，重核记录追加且重复核验幂等。外部网站观察不能走该入口升级为 App 回执。
- 默认简历官方写客户端仅允许固定 HTTPS `POST /mcp/apply-job`，只发送原始 `jobId/jobKind`；拒绝重定向、无自动重试。只读客户端白名单保持不变。凭据仅从本机受控保存项取得；真实写调用仍使用已批准快照和持久化防重。
- 官方 HTTP/业务失败、明确成功及无法确认的响应分别记录；仅 HTTP 成功或通用 `success` 文案不足以算作投递成功。日志保存安全响应摘要/指纹、对应岗位和观测简历指纹，不保存 Token、请求头或简历正文。API 回执使用独立步骤契约，不伪造浏览器登录/截图步骤；无明确业务回执则结果 unknown 并暂停后续发送。

- 手动 REVIEW 入队前沿既有 exporter 固化 Markdown/PDF 和目标清单，记录 run/candidate/原平台 ID/type/JD 指纹、简历版本、文件指纹及 dry-run 标记；审批界面展示该 Markdown 正文和版本校验状态。文件或目标与快照不符时拒绝批准和执行，不能审批后重新生成替代内容；只读文件权限配合哈希验证防止无声覆盖。
- 复用 `run.agent.submitReview`：严格校验整批决策、精确候选、当前 pending 状态；重复同意为幂等，已拒绝/跳过不得被同一队列重新批准。审批决定先持久化，再从快照恢复执行前校验并记录结果；异常或进程退出后重复同意可恢复尚未执行的已批准项，无须重新生成。旧队列缺快照仅可拒绝/跳过，不可提交。
- 检查批次始终返回 `checked_not_submitted`、`success=false`；禁止审批操作把 dry-run 升级为真实发送。官方来源的生成 PDF 路线仍受 `official_delivery_contract_unverified` 阻断；显式 platform_default 按上方独立授权与观测契约执行，不能把该路线当作生成 PDF 版本绑定。
- 真正调用已核实渠道前，以平台及稳定岗位身份（原始 ID/type，旧来源用规范化 HTTPS URL）原子记录 `in_flight`。键不包含 run_id 或简历版本；重启、换版本、重复批准不得重复调用。成功、明确失败和未知分别落盘；异常/不确定结果记为 unknown，已有记录一律不自动重试或切换渠道。检查/前置阻断不占真实发送记录。
- 审批结果与运行记录同步展示，批准数、检查通过数、真实成功数分别计数。UI 的“已批准”不代表“已投递”；快照/文件错误、未核实契约及未知结果须可见。
- 业务防重键使用账号作用域 + 平台 + 稳定岗位身份；`run_id`、日期、简历版本仅用于尝试追溯，不解除重复限制。提交前持久化 in-flight 状态，结果未知须先核对，不能靠重启重新发送。
- 每日上限按 `Asia/Shanghai` 自然日累计确认成功数，所有启用平台合计最多 3 次；请求频控与成功计数分离，新增平台不放大额度、不自动扩展授权渠道。未知结果保留额度并暂停后续自动发送，防止潜在成功突破上限；dry-run/check-mode 不计成功。持续授权与定时入口在单次闭环后实施。

#### P0-018 每日受控投递

中断恢复增量（2026-10-08）：复用 daily_runs.items、原 PDF 审批队列及 SQLite 尝试，不新增恢复队列或发送引擎。每日历史须显示每项岗位的当前可核验阶段、该批成功/未决数量和返回原 PDF 核验页的入口；按批次身份读回，不把后续批次进度写成旧批结果。结束中断批次时，已成功记录不变、未开始项保持未开始、在途投递转 unknown 并保留占位；上传中的项转上传未确认，保留原观测，不允许重传。已开始但中断的原运行只允许核验，不继续发送；未知上传或未决投递须先处理，不因跨日/重启重新开始。关闭中断批次仍受原生执行锁保护；页面导航和只读状态查询不得启动网络写入。

- 复用现有 SQLite 尝试库、批准快照及原生 PDF 链。首版持续授权只支持猎聘 `generated_pdf`，由用户从已准备的固定岗位/PDF 中选择有限清单（最多 30 项），明确上海时区每日执行时间、1–3 次上限和到期时间。新岗位、新文件、其他平台和附件删除不自动加入授权。保存草稿不启用发送；只有确认清单及上传平台副作用后才能启用。授权启用后范围不可变，可暂停、恢复或永久撤销；到期即阻断。
- 所有受控发送共用每日最多 3 个名额；成功和未决占位共同约束额度，跨日期存在未知/在途时暂停后续自动发送。投递日期以占位时的上海自然日为准；跨午夜的最终发送须阻断，不沿用昨日名额。已有成功/未知岗位不能因重启、换授权或换简历再次发送。历史验证批次不改写，新的每日批次独立留证。
- 每日触发使用持久化日期唯一键与运行标识，手动“执行今日批次”和 App 内定时检查共用入口；同一天最多一个实际批次，同批最多尝试每日上限个岗位，明确失败也不无限补投。App 退出/睡眠时不承诺运行，恢复后只处理当天，不补过去日期。中断运行保留占位并要求核验，不自动接着发送。
- 每次上传、开始沟通与最终发送前重新核对持续授权状态、有效期、运行日期及固定文件/岗位身份；暂停/撤销阻止后续动作，已发出的请求不能撤回。实际发送继续使用现有当前 JD/排除名单/附件原字节/确认界面/业务回执检查；没有明确成功回执的动作停止整个批次，不重传、不重发、不降级渠道。
- App 智能运行页显示授权草稿、具体清单、今日成功/占位数、执行状态、短缺原因与最近日期记录。附件位满、候选不足、登录失效、授权无效或未知回执均如实记原因。原有单笔操作与每日批次共享原生会话互斥。跨日测试时钟仅为测试依赖，不开放给生产 RPC；多日真实验收须等待真实日期，不可用模拟时间冒充完成。

P0-017A 首片（2026-09-28）：

- 完整 JD 复用官方 Lead 的公开 HTTPS 详情来源，只读取已保存的官方 URL；不带 Token/Cookie、不跟随重定向、不绕过验证页。只接受与原始岗位 ID 相符的 JobPosting 正文，SEO 摘要不算完整 JD；失败保留原资料。 已核实的“职位描述”标题可作为职责章节，与实质性岗位/任职要求共同判定完整；仍须两类实质正文、原始 ID 和可见/结构化正文一致，不把介绍、摘要或截断文本升级为完整 JD。
- 获取正文后为 `full_unreviewed`；用户经既有草稿审核保存后才为 `complete_reviewed`。完整原文、来源 URL、正文 SHA256、平台原 ID/type 及原 Lead/Profile 关联必须保留，平台身份从后端原 Lead 获取，不能由 LLM 或前端改写。
- 同一 Lead 的转换/补全应复用稳定关联，不另建同义 manual Lead；重复搜索保留正文和审核。正文或画像关键内容改变后须撤销旧审核，未审核资料不能仅通过 status 字段升级为可投递目标。
- 官方来源候选必须有同一 Lead 关联的 active 已审核画像，正文指纹和来源身份一致，并匹配本次运行选中的画像。显式选择无合格候选时必须报错，不能回退其他岗位；CLI 与 App 的 Lead 读取保持同样边界。
- 官方发送版本/回执契约未闭合前，官方来源候选必须明确返回 `official_delivery_contract_unverified`，不得隐式走旧浏览器或邮件；首片不开放审批后的真实执行，不伪造已具备发送能力。

### App 渠道会话的真实浏览器边界（2026-09-06，旧适配路径）

- 复用 Tauri → Python sidecar 与 Playwright 持久化上下文；Chrome DevTools MCP 仅为开发工具，不是 App 运行前提。
- 调试 App 无显式 Python 覆盖时优先使用仓库已有 `.venv`，避免普通启动丢失终端临时环境变量后切回缺少依赖的系统 Python；已设置的覆盖仍优先，打包版继续使用内置运行时并单独验收。
- `submission.channelSession.start` 必须从官网可用入口打开登录界面，确认可见登录表单或正向登录状态后才返回；当前猎聘使用 `https://www.liepin.com/` 的表单/登录入口。HTTP 错误或表单缺失不能返回等待登录；已登录时直接复用检查，失败后前端回读后端状态。
- 登录框瞬间出现不能作为稳定可用的验收依据；加载后主动跳空白须明确失败，检查现有空白页不得静默反复重载。短时稳定检查仅用于发现已知问题，不替代人工登录与长时会话验证。
- `submission.channelSession.check` 只采用后端实际浏览器观察，忽略客户端提供的登录信号和账号身份。登录提示、验证页、非渠道域名优先阻断；普通职位页、申请按钮或登录弹窗消失不足以证明已登录。
- 会话使用现有 `outputs/channel_sessions/<channel>/browser_profile`；重复打开复用所持有会话，清理和 sidecar 关闭释放对应浏览器；不得依赖开发者的日常 Chrome 调试连接。
- 不输入密码、短信或验证码，不上传或发送简历；实际人工登录与真实投递分别验收。

### 投递结果与候选交接（2026-09-05 增量）

- 沿用现有 `LiepinChannel`、`SubmissionRecorder` 与 External L3 投递链路，不新增平行投递实现。
- 浏览器适配的真实投递成功必须来自本次调用的已持久化记录：`mode=submit`、`status=success`、无错误，且 `rate_limit/login_check/target_verify/submit_safety/chat_send_resume/submit` 均成功；仅退出码为 0 不足以判定成功。官方 API 适配须按上节建立等价证据并同步验收器，不能直接复用此浏览器步骤清单或提前放行。
- 检查模式和 dry-run 可以返回流程完成，但必须令 `DeliveryResult.success=false`；真实 Agent 运行只在该字段为 true 时增加成功投递数。缺少浏览器运行依赖返回明确失败，不自动降级为模拟成功。
- Agent 在交给通道前，必须使用共享 HTML/CSS exporter 将本轮生成的 Markdown 导出为 PDF；每次尝试使用独立目录，记录原始简历版本、Markdown/PDF 指纹和文件路径。导出或落盘失败返回明确错误，不进入通道或使用旧附件。
- 猎聘默认“发简历”只说明平台发送流程存在，不能证明发送了本地 `resume_path`。未验证具体附件与本次 PDF 的绑定前，不得执行该默认发送操作或声称附件绑定完成；具体上传入口须有真实页面依据。
- 候选桥接的 shell 模板必须把参数传递给实际子进程，并默认关闭外部授权、最终提交确认和人工会话确认；session 文件存在只证明存储已准备，不能代替人工确认登录有效。
- 候选准备必须核对 lead 中的岗位 URL 与 check-mode 证据中的岗位 ID；不一致时输出明确缺口，不能展示为准备完毕。
- 本增量只收口单次投递前置能力；每日调度、每日成功计数、持续授权及跨运行去重按路线图后续阶段实施。

```bash
# 证据提炼（推荐入口）
python3 tools/run_evidence_extraction.py --input <raw_file>

# 完整 pipeline
python3 tools/run_pipeline.py \
  --raw tools/sample_raw.txt \
  --job-profile job_profiles/jp-2026-001.yaml

# Agent loop（统一核心引擎入口）
python3 tools/run_agent.py --policy profiles/agent_policy.example.yaml --dry-run
```

说明：
- `tools/run_evidence_extraction.py` 是面向工作流和文档约定的推荐入口；`tools/extract_evidence.py` 保留为底层规则实现/兼容脚本。
- `tools/run_pipeline.py` 属于兼容入口，在迁移期内部转调 `tools/config/composer.py` 组装出的新 pipeline / orchestration 层。
- 新增能力优先通过 `tools/run_agent.py` 与 `tools/cli/entrypoints.py` 暴露。

---

## 变更流程

1. 使用 `/opsx:propose` 提交变更提案
2. 通过 brainstorming skill 细化设计
3. 通过 writing-plans skill 生成实现计划
4. TDD 实现（test-driven-development skill）
5. code review（requesting-code-review skill）
6. 使用 `/opsx:archive` 归档已实施变更

---

## 统一核心引擎架构规范

> 本节由架构审核确定（v2，2026-03-06 审核修订），适用于所有新增模块与重构变更。
> v2 修订基于六边形领域核心、策略注册表、管道组合化、配置解聚、Result 类型、事件溯源六项架构改进。

### 核心原则

1. **零 subprocess**：所有阶段通过纯 Python API 调用，禁止 subprocess 串联。
2. **DRY**：LLM 客户端、YAML 解析、配置管理、错误处理各有唯一实现，不得在各阶段重复。
3. **OCP**：规则/LLM 实现通过策略注册表（EngineRegistry）动态注入，新增策略只需注册，不改已有代码。禁止在业务逻辑中出现 `if use_llm` 分支。
4. **可测试**：领域逻辑不依赖 IO 与第三方服务，可独立单元测试。
5. **依赖倒置（DIP）**：所有模块向领域层"内指"，领域层零外部依赖。Protocol 定义在领域层，实现在外层。
6. **组合优于继承**：Pipeline 由 Stage 对象组合而成，agent_loop 复用 pipeline 的 Stage，而非继承。
7. **接口隔离（ISP）**：各组件只接收自己需要的配置切片，禁止传递上帝 Config 对象。

### 架构分层（六边形领域核心）

依赖方向：`cli → orchestration → engines → domain ← infra`

```
┌─────────────────────────────────────────────┐
│  cli/           入口层（唯一读取 env/argv）    │
├─────────────────────────────────────────────┤
│  orchestration/ 编排层（Stage 组合调度）       │
├─────────────────────────────────────────────┤
│  engines/       引擎层（Protocol 实现）        │
│  channels/      投递通道层                    │
├─────────────────────────────────────────────┤
│  domain/        领域核心（零外部依赖）  ← 核心  │
├─────────────────────────────────────────────┤
│  infra/         基础设施层（向内依赖 domain）   │
└─────────────────────────────────────────────┘
```

### 目标目录结构

```
tools/
  domain/                    # 领域核心（零外部依赖，frozen dataclass）
    models.py               # EvidenceCard, JobProfile, MatchingReport, ResumeOutput, Scorecard
    protocols.py            # 所有 Protocol 定义（引擎接口、存储接口）
    value_objects.py        # Score, GapTask, Candidate, ScoreBreakdown 等值对象
    invariants.py           # evidence-first 守卫、事实保真校验
    result.py               # Result[T, E] 类型（Ok/Err，用于可恢复错误）
    events.py               # RunEvent 不可变事件定义
    run_state.py            # RunState 从事件回放重建
  infra/                    # 基础设施层（向内依赖 domain）
    llm/
      client.py             # LLMClient 统一实现（唯一 HTTP 调用点）
      openai_adapter.py     # OpenAI-compatible 适配器
    persistence/
      yaml_io.py            # 统一 YAML 读写（唯一实现）
      file_store.py         # 文件存储（证据/报告/产物）
      file_run_store.py     # RunStore 文件实现（事件追加写入 + 轮次快照）
    logging.py              # 结构化日志
  engines/                  # 引擎层（向内依赖 domain，可依赖 infra）
    registry.py             # EngineRegistry[T] 通用注册表
    evidence/
      rule_extractor.py     # RuleEvidenceExtractor
      llm_extractor.py      # LLMEvidenceExtractor（注入 LLMClient）
      validator.py           # 证据合规校验（强制 results/artifacts）
      store.py               # 证据存储与检索
    matching/
      rule_scorer.py        # RuleMatchingEngine（K/D/S/Q/E/R）
      llm_matcher.py        # LLMMatchingEngine（注入 LLMClient）
      report_builder.py
    generation/
      template_assembler.py # TemplateAssembler（evidence-first，无证据不生成）
      llm_rewriter.py       # LLMRewriter（受控改写，不引入新事实）
      exporter.py           # 格式导出（md/pdf）
    evaluation/
      rule_evaluator.py     # RuleEvaluationEngine（coverage/quant/clarity/length/citation）
      llm_evaluator.py      # LLMEvaluationEngine（先规则后解释，规则分数不可被 LLM 修改）
      scorecard_builder.py
    discovery/
      discovery_engine.py   # 候选发现（三级回退）
  orchestration/            # 编排层（Stage 组合模式）
    stage.py                # Stage Protocol + StageResult + RunContext
    pipeline.py             # LinearPipeline（Stage 序列组合）
    agent_loop.py           # AgentLoop（复用 pipeline 的 Stage，驱动状态机循环）
    review_stage.py        # ReviewStage（auto pass-through / manual 审批）
    gate_engine.py         # GateStage（独立于编排的 N-pass 门禁）
    state_machine.py       # StateMachine 纯函数（10 状态迁移（含 REVIEW））
  config/                   # 配置层
    fragments.py            # LLMConfig, PathConfig, PolicyConfig, EngineSelection（独立切片）
    composer.py             # Composer（唯一了解全部配置的组装点）
    loader.py               # 从 policy YAML + CLI 参数加载配置
    validator.py            # 配置合规校验
  errors/                   # 异常与错误处理
    exceptions.py           # PiProofError 及不可恢复子类
    handler.py              # 错误路由（终止/LEARN/降级）
  channels/                 # 投递通道层
    base.py                 # DeliveryChannel Protocol
    liepin.py               # 猎聘通道（纯 Python）
    email.py                # Email 通道（smtplib）
  cli/                      # 薄 CLI 层，仅解析参数 → 构造 Composer → 调用编排
    commands/
      extract.py / match.py / generate.py / evaluate.py
      pipeline.py / agent.py
    entrypoints.py          # 统一 CLI 注册入口
```

### 核心引擎接口规范（Protocol 定义在 domain/protocols.py）

```python
# domain/protocols.py — 所有接口定义在领域层

class EvidenceExtractor(Protocol):
    def extract(self, raw_material: RawMaterial) -> EvidenceCard: ...

class MatchingEngine(Protocol):
    def score(self, evidence_cards: Sequence[EvidenceCard], profile: JobProfile) -> MatchingReport: ...

class GenerationEngine(Protocol):
    def generate(self, report: MatchingReport, cards: Sequence[EvidenceCard],
                 version: str, config: GenerationConfig) -> ResumeOutput: ...

class EvaluationEngine(Protocol):
    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard: ...

class DiscoveryEngine(Protocol):
    def discover(self, request: DiscoveryRequest) -> list[Candidate]: ...
    # candidate 必须在输出前完成 company/legal_entity 归一、冲突合并与企业例外清单过滤

class GateEngine(Protocol):
    def evaluate(self, request: GateRequest) -> Result[GateDecision, GateFailure]: ...
    # 若 candidate 命中企业例外清单，即使绕过 discovery 过滤，也必须返回 fail 并阻止进入 DELIVER

class DeliveryChannel(Protocol):
    channel_id: str
    def deliver(self, request: DeliveryRequest) -> Result[DeliveryResult, ChannelFailure]: ...

class ReviewStage(Stage):
    """REVIEW 阶段。auto 模式 pass-through；manual 模式暂停等待用户审批。"""
    name: str = "REVIEW"
    def execute(self, context: RunContext) -> StageResult: ...
    # ReviewCandidate: frozen dataclass — job_lead_id, company, position, matching_score, evaluation_score, round_index, resume_version
    # ReviewDecision: frozen dataclass — job_lead_id, action(approve/reject/skip/skip_all), decided_by, decided_at, note

class RunStore(Protocol):
    def append_event(self, event: RunEvent) -> None: ...
    def save_round(self, snapshot: RoundSnapshot) -> None: ...
    def finalize(self, summary: FinalSummary) -> None: ...
    def load_events(self, run_id: str) -> Sequence[RunEvent]: ...
    def get_run_dir(self) -> Path: ...
```

### 策略注册表规范（OCP 实现）

```python
# engines/registry.py — 新增策略只需注册，不改已有代码
T = TypeVar("T")

class EngineRegistry(Generic[T]):
    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., T]] = {}

    def register(self, name: str, factory: Callable[..., T]) -> None:
        self._factories[name] = factory

    def create(self, name: str, **kwargs: Any) -> T:
        if name not in self._factories:
            raise ValueError(f"Unknown engine: {name}. Available: {list(self._factories)}")
        return self._factories[name](**kwargs)

# 各引擎自注册示例
evidence_registry = EngineRegistry[EvidenceExtractor]()
evidence_registry.register("rule", lambda: RuleEvidenceExtractor())
evidence_registry.register("llm", lambda llm_client, prompt_path:
    LLMEvidenceExtractor(llm_client, prompt_path))
# 扩展新策略：只需一行注册
# evidence_registry.register("anthropic", lambda client: AnthropicExtractor(client))
```

### 管道组合规范（Stage 模式）

```python
# orchestration/stage.py
@dataclass(frozen=True)
class StageResult:
    success: bool
    data: Any
    errors: tuple[PiProofError, ...] = ()

class Stage(Protocol):
    name: str
    def execute(self, context: RunContext) -> StageResult: ...

# orchestration/pipeline.py — 线性管道：Stage 的组合
class LinearPipeline:
    def __init__(self, stages: Sequence[Stage]):
        self.stages = stages

    def run(self, context: RunContext) -> PipelineResult:
        for stage in self.stages:
            result = stage.execute(context)
            if not result.success:
                return PipelineResult(failed_at=stage.name, error=result.errors)
            context = context.with_update(stage.name, result.data)
        return PipelineResult(success=True, context=context)

# orchestration/agent_loop.py — 循环编排：复用 Stage，不重写业务逻辑
class AgentLoop:
    def __init__(self, pipeline: LinearPipeline, gate: Stage,
                 discovery: Stage, learn: Stage, review: Stage, policy: PolicyConfig):
        self.pipeline = pipeline  # 组合，不继承
        self.gate = gate
        # ...
```

### 领域模型规范（不可变值对象）

```python
# domain/models.py — frozen=True 保证不可变

@dataclass(frozen=True)
class EvidenceCard:
    id: str
    title: str
    raw_source: str
    results: tuple[str, ...]
    artifacts: tuple[str, ...]
    tags: tuple[str, ...] = ()
    period: str = ""
    context: str = ""

    def is_eligible(self) -> bool:
        """evidence-first 守卫：results/artifacts 缺失不进入候选池"""
        return bool(self.results) and bool(self.artifacts)

@dataclass(frozen=True)
class JobProfile:
    id: str
    title: str
    keywords: tuple[str, ...]
    level: str
    must_have: tuple[str, ...] = ()
    nice_to_have: tuple[str, ...] = ()

@dataclass(frozen=True)
class MatchingReport:
    job_profile_id: str
    evidence_cards: tuple[str, ...]     # card IDs
    score_breakdown: ScoreBreakdown
    gap_tasks: tuple[GapTask, ...]
```

### 错误处理规范（异常 + Result 双轨）

不可恢复错误使用异常，可恢复错误使用 `Result[T, E]` 类型：

```python
# domain/result.py — 可恢复错误的显式表达
@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

@dataclass(frozen=True)
class Err(Generic[E]):
    error: E

Result = Ok[T] | Err[E]

# 异常 vs Result 的边界
# | 场景                   | 处理方式                                |
# |------------------------|----------------------------------------|
# | gate_fail              | Result[GateDecision, GateFailure]      |
# | channel_error          | Result[DeliveryResult, ChannelFailure] |
# | discovery_empty        | Result[list[Candidate], DiscoveryEmpty]|
# | FabricationGuardError  | 异常 — 不可恢复，终止                    |
# | EvidenceValidationError| 异常 — 不可恢复，终止                    |
# | PolicyError            | 异常 — 配置错误，终止                    |

# errors/exceptions.py — 仅保留不可恢复异常
class PiProofError(Exception):
    """所有不可恢复业务异常的基类"""
    category: ErrorCategory
    recoverable: bool = False

class EvidenceValidationError(PiProofError):
    """证据不合规（缺 results/artifacts）"""
    category = ErrorCategory.EVIDENCE

class FabricationGuardError(PiProofError):
    """生成阶段检测到无证据内容"""
    category = ErrorCategory.GENERATION

class PolicyError(PiProofError):
    """配置错误"""
    category = ErrorCategory.POLICY
```

### 配置解聚规范（ISP）

各组件只接收自己需要的配置切片，禁止传递上帝 Config：

```python
# config/fragments.py — 独立配置切片
@dataclass(frozen=True)
class LLMConfig:
    model: str
    base_url: str
    api_key: str
    timeout: int = 120

@dataclass(frozen=True)
class PathConfig:
    evidence_dir: Path
    output_dir: Path
    profile_dir: Path

@dataclass(frozen=True)
class PolicyConfig:
    max_rounds: int
    max_deliveries: int
    gate_mode: str           # strict | simulate
    n_pass_required: int
    delivery_mode: str       # auto | manual
    batch_review: bool = False  # 仅 manual 时生效
    excluded_companies: tuple[CompanyExclusionRule, ...] = ()
    excluded_legal_entities: tuple[str, ...] = ()

@dataclass(frozen=True)
class CompanyExclusionRule:
    match: str               # exact | contains
    value: str

@dataclass(frozen=True)
class EngineSelection:
    evidence_mode: str       # 由 EngineRegistry 校验，不用 Literal
    matching_mode: str
    generation_mode: str
    evaluation_mode: str

# config/composer.py — 唯一了解全部配置的组装点
class Composer:
    """组装所有组件。CLI 层构造 Composer，其他层不直接接触配置。"""
    def __init__(self, llm: LLMConfig, paths: PathConfig,
                 policy: PolicyConfig, engines: EngineSelection): ...

    def build_pipeline(self) -> LinearPipeline: ...
    def build_agent_loop(self) -> AgentLoop: ...

    @staticmethod
    def from_yaml(policy_path: str) -> "Composer": ...
```

企业例外清单规范：

- `excluded_companies` 用于展示名/常用名/别名过滤，支持 `exact` 与 `contains`
- `excluded_legal_entities` 用于主体级排除，优先级高于展示名匹配
- 命中例外清单的 candidate 不得进入 scoring / generation / delivery
- 被过滤 candidate 必须在 `run_log` 或 `rounds/<n>/candidates.json` 中记录 `excluded_by_policy` 原因

### 事件溯源规范（RunStore 增强）

```python
# domain/events.py — 不可变事件
@dataclass(frozen=True)
class RunEvent:
    event_id: str
    run_id: str
    round_index: int
    timestamp: datetime
    event_type: str
    payload: Mapping[str, Any]

# domain/run_state.py — 从事件回放重建状态（支持断点续跑）
@dataclass(frozen=True)
class RunState:
    run_id: str
    current_state: AgentState
    round_index: int
    pass_count: int
    delivered_count: int

    @staticmethod
    def replay(events: Sequence[RunEvent]) -> "RunState":
        state = RunState.initial(events[0].run_id)
        for event in events:
            state = state.apply(event)
        return state

    def apply(self, event: RunEvent) -> "RunState":
        """纯函数：旧状态 + 事件 → 新状态"""
        ...
```

---

## 参考文档

- 业务域：`AIEF/context/business/DOMAIN.md`
- 架构：`AIEF/context/tech/architecture.md`
- Evidence Card Schema：`AIEF/context/tech/SCHEMA_EVIDENCE_CARD.md`
- Job Profile Schema：`AIEF/context/tech/SCHEMA_JOB_PROFILE.md`
- 生成规范：`AIEF/context/tech/GENERATION.md`
- 评估规范：`AIEF/context/tech/EVALUATION.md`
