# PiProofForge Desktop App - Final UX Specification

## 定位

产品级桌面应用（Tauri + Python sidecar），面向求职者自用。

本文件定义 GUI 终版产品规范。凡涉及桌面端的信息架构、交互职责、组件基线、设计 Token、国际化约束与 sidecar 集成要求，均以本文件和 `ui/design/piproofforge.pen` 为准。

## 技术栈

- 框架: Tauri (Rust shell + Web frontend)
- 后端: Python sidecar (复用现有 tools/ 代码)
- 前端: React 18 + TypeScript + Tailwind CSS + Zustand (推荐)

## 设计方案

Dashboard + Chat 混合模式（方案 B+C）：
- 主界面: Dashboard 全景仪表盘，侧边导航切换页面
- AI 助手: 可收起对话面板，新手引导 + 自然语言查询（未来迭代）

## 设计主题

暗色主题：
- 深蓝黑背景 (#071023)
- 青色/天蓝色强调色 (#38BDF8 / #22D3EE)
- 面板使用实色背景 (#1E293B) + 1px 边框
- 设计稿中的文本标签采用 **English / 中文** 仅作为双语对照标注，便于评审；实际产品界面必须通过 i18n 实现单语切换，不得双语同时上屏

## 设计文件

- 主文件: `ui/design/piproofforge.pen`（Pencil MCP 格式）
- 组件放画布上方，9 个页面从上到下纵向排列
- 每页尺寸: 1440 × 900（桌面端标准）
- 导航顺序对应用户旅程: 概览 → 简历 → 证据 → 岗位 → 快速执行 → 自主运行 → 投递 → 策略配置 → 系统设置
- SideNav 底部: 语言切换入口 (EN / 中)

## 设计资产治理机制

### 1. DESIGN.md + piproofforge.pen 双真源联动

- `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen` 共同构成 GUI 设计真源，缺一不可
- 任何页面结构、组件、Design Tokens、导航、状态页、交互约束的变更，必须同时修改这两个文件
- 禁止只改 `ui/design/DESIGN.md` 不改 `ui/design/piproofforge.pen`
- 禁止只改 `ui/design/piproofforge.pen` 不回写 `ui/design/DESIGN.md`
- 若两者冲突，该变更视为未完成，不得进入实现或验收阶段

### 2. 实现以设计资产验收

- 后续前端实现不得只依据文档理解开发，必须逐页对照 `ui/design/piproofforge.pen`
- 实现验收至少覆盖以下项目:
  - 9 页页面结构是否齐全
  - SideNav 导航顺序是否一致
  - 共享组件是否与设计资产一致
  - Design Tokens 是否映射完整
  - Loading / Empty / Error 状态页是否补齐
  - Quick Run / Agent Run 是否在职责、布局、状态表达上明确区分
- 若实现与 `DESIGN.md` 一致但与 `.pen` 不一致，或与 `.pen` 一致但与 `DESIGN.md` 不一致，均不算通过

### 3. 防漂移检查项

- 每次 GUI 变更都必须同步检查:
  - 文档是否已更新
  - `.pen` 是否已同步
  - 前端实现是否与两者一致
- 上述三项任一未满足，该次 GUI 变更不算完成
- 建议在代码评审、设计评审、实现验收三个环节重复执行此检查项，避免文档、设计稿、实现三方漂移

## 桌面窗口与响应式规则

- 设计基线窗口尺寸: `1440 x 900`
- 支持的最小窗口尺寸: `1280 x 800`；低于该尺寸时不再保证完整布局，必须提示用户放大窗口
- 支持的 UI 缩放范围: `80% - 125%`；超过范围交由系统缩放处理，不单独适配
- 主内容区允许纵向滚动；禁止整页横向滚动。表格类组件可在局部容器内横向滚动，但必须固定表头
- 侧边导航在最小尺寸下保持图标 + 文本，不折叠为仅图标模式
- 右侧详情面板在宽度不足时可切换为覆盖式 drawer，但不得直接消失
- 页面响应式只在桌面范围内处理，不为 tablet / mobile 提供单独断点与布局版本
- 当窗口宽度处于 `1280 - 1365` 区间时，统计卡片可从 4 列降为 2 列；双栏布局允许右栏降宽，但页面职责不可折叠丢失
- 窗口尺寸、位置与最大化状态在退出时保存、下次启动时恢复（`tauri-plugin-window-state`，状态文件在应用数据目录 `.window-state.json`）；最小尺寸仍由 `tauri.conf.json` 约束

## 折叠（渐进披露）使用规则

折叠（`<details>`、按钮切换显隐、手风琴）只是信息层级的表达手段，不是新功能的默认落点。任何页面新增折叠前先过下面的标准：

- 允许折叠：次要或低频内容（技术详情、开发期工具、历史记录）；很长的原文或日志；可选的高级项（授权条款、补充依据）；分级呈现中的低优先级部分（低置信候选、已分流项）。
- 禁止折叠：页面主任务的入口（例如证据页的“从材料提炼”）；触发计算或请求的动作（动作必须是显式按钮，不得借“展开”这个无意图手势触发）；用户做决策必需的信息（来源等级、问题原因、状态依据）；仅因为“当前布局放不下”而折叠。
- 折叠不得嵌套超过一层；同一屏并列的常驻折叠区块不超过一个。超出时说明布局本身需要重排，而不是继续加折叠。
- 本应是筛选的事情（“只看有问题的”“显示已分流的”）用筛选器表达，不用折叠/切换按钮。
- 页面若需要一段解释性文字才能让用户理解各区块的关系，视为结构缺陷信号，优先改结构而不是加提示条。

## 页头吸顶与主内容区

- 各页 `.page-header` 为 `position: sticky; top: 0`，并用 `-mx-6 -mt-6` 抵消 `<main>` 的 24px 内边距以撑满宽度。
- 已知缺陷（2026-10-18 用户反馈）：sticky 的 `top: 0` 相对 `<main>` 的内边距盒计算，页头吸顶后停在距 `<main>` 顶边 24px 处，上方 24px 条带没有任何背景，滚动内容从这条缝里透出来。Chromium 最小复现已确认（页头 `getBoundingClientRect().top === 24`，`elementFromPoint(x, 10)` 命中内容元素）。
- 修法：`.page-header` 的 `top` 改为 `-1.5rem`（与 `-mt-6` 等值），使其吸附到 `<main>` 真实顶边；同一复现下页头 `top === 0`、条带命中页头本身。不采用 `box-shadow` 伪延伸（经验证不覆盖该条带）或给 `<main>` 去 padding（会牵动全部 9 页间距）。壳层 sidecar 横幅出现在页头上方时同样适用。

**实施（2026-10-18）**：`ui/src/styles/globals.css` 的 `.page-header` 已移除 `top-0`、改为 `top: -1.5rem`，全部 9 页生效。

---

## 页面清单 (9 页)

### 1. Overview / 概览

**职责**: 资产统计、最近活动、缺口待办、匹配趋势

**布局**:
- 顶部: 页面标题 + "Run Agent / 启动" 主按钮
- 统计卡片行 (4 列): Evidence / 证据卡 (12), Matched Jobs / 匹配岗位 (8), Resumes / 简历版本 (5), Submissions / 投递次数 (23)
- 下方两栏:
  - 左栏 (fill): Recent Activity / 最近活动 — 带图标的活动流列表（简历生成、投递、证据提取、Agent 运行）
  - 右栏 (380px):
    - Match Trend / 匹配趋势 — 折线图 + 渐变面积填充
    - Delivery Funnel / 投递进展（2026-10-11，P0-025 切片 2）— 读取 `overview.get` 的 `metrics.feedback_funnel`：一条按状态分段的部分-整体条（已投递 → 已查看 → 感兴趣 → 面试邀约 → 不合适 → 停止招聘 → 未识别 → 未同步，段间 2px 间隙，零值不画段），下方两列状态行各带图标、文字与计数，零值行弱化；颜色只做辅助，相邻阶段用同色深浅区分；无受控投递时显示空态；入口“查看投递记录”进入 Submissions。Pen 节点 `ovFunnel`（`KJlps`），Overview 画布因此增高到 1200，右栏三卡改为内容高度。
    - Gaps / 缺口待办 — 红色计数徽标 + 警告项列表

### 2. Resumes / 简历中心

2026-10-12 求职方向与边界：在职业档案之后复用现有材料库增加折叠区，显示已保存偏好数量。选材料和文档片段后提炼主投/桥接/探索/回避条目，逐条展示可编辑摘要与只读原文引用；勾选核对确认后保存，提炼本身不修改设置。修改偏好不影响职业事实确认，偏好不进入候选人简历；来源变化或修订冲突明确报错。Quick Run 语义模式先判断方向，结果区显示符合/需核实/明确不符、原因、对应偏好和 JD 原文；明确不符显示 SKIPPED 并停止后续生成。`.pen` 同步既有 Resumes/Quick Run 页内扩展，不新增页面或审批队列。

**职责**: 个人资料维护、用户上传简历管理、系统生成简历管理与导出

完整职业档案增量：在既有三栏前增加可折叠的全宽档案编辑卡（`career01`），仍属于简历中心。原基本信息保持原入口，并将完整度标为“基本信息完整度”。档案包括职业摘要、工作/合作经历、分组能力、教育及可选补充成果；条目可添加/移除，年月与至今明确区分，工作/能力复用证据列表勾选关联。工作记录中的公司是实际任职/合作单位，不预填客户品牌。教育默认展示，用户可明确选择不展示。

保存草稿与确认事实分开，缺项和未确认状态在卡片中展示；未保存修改、外部版本变化或缺项时禁用确认。确认绑定内容和关联证据版本，改变事实会失效。并发旧表单不得覆盖新数据。资料库就绪检查复用原入口，加入职业档案确认；已有上传简历是可选参考，不作为系统生成的必需条件。

生成版预览与 PDF 由 `tools/infra/export/resume_html.py` 和 `resume.css` 共用模板提供。现有白纸预览区域显示 sandbox iframe，并按 A4 宽度等比缩放；`.pen` 保留该区域的容器与内容占位，不再另行维护一套动态简历排版。旧 sidecar 的结构化预览仅保留兼容展示。

2026-10-05 质量优化：单栏 A4 使用清晰的姓名/联系信息、章节/项目/日期层级与舒适正文间距，长项目允许自然续页；标题不孤悬，章节保持源文顺序。生成阶段补入已核实项目场景并按目标选取行动，Quick Run 质量区展示缺少的职责、时间、场景、行动或技能依据，缺项保留 NEEDS_EVIDENCE，PDF 导出成功不升级质量状态。

**布局**:
- 顶部: 页面标题 + "Upload Resume / 上传简历" 次按钮 + "Export PDF / 导出 PDF" 主按钮
- 内容区三栏:
  - 左栏 (320px): Personal Profile / 个人资料
    - Basic Info / 个人基本信息: 姓名、手机号、邮箱、城市、当前职位
    - Profile Status / 资料状态: 完整度、最近更新时间、缺失字段提示
    - 主操作: "Edit Info / 编辑资料"
  - 中栏 (320px): Uploaded Resumes / 已上传简历
    - 每行: 文件名、语言、上传时间、来源渠道（本地上传 / 导入）
    - 支持预览、重命名、删除、设为基准版本
  - 右栏 (fill): Generated Resumes / 系统生成简历
    - 上半区: 已生成简历列表，最大高度 256px，超出时独立滚动；大屏仍保持上下布局，避免进一步压缩纸张预览
      - 每行: 版本名、关联岗位、状态标签 (Latest/Old/Low)、分数、目标公司、更新时间
    - 下半区: Preview / 预览
      - 头部: 当前版本名 + "A/B Compare" 链接 + 编辑图标
      - 内容: 白色纸张预览（模拟真实简历格式）
        - 姓名（按简历语言显示）、联系方式
        - Professional Summary
        - Experience (职位 + 时间 + 成果列表)
        - Skills

### 3. Evidence / 证据卡

**职责**: Evidence Card CRUD、缺口标记、详情查看

> 2026-10-18 起本页以下方「证据页结构重整（2026-10-18）」为准；本节此前的材料区/对账区描述保留为历史实现记录，与新结构冲突处以新结构为准。

材料选择器支持库内 Markdown 与工作目录导入的 TXT。现有材料区增加“选择工作文档”：按文件名称筛选、选择有界片段、展开原文，再启用既有模型提炼；长文完整拆段，每段最多 24000 字符，目录里的 AGENTS/CLAUDE/索引/规则/模板不进入默认候选。“手动整理证据”仍可建立来源草稿，选择文档后也绑定同一片段。审核保存重验文档指纹及结果原文，未审核草稿不进入候选池。新节点 `docPick1`。

可用数量按真实候选资格统计，旧 ready/pass 卡若未经当前来源审核显示待审核。普通编辑保留来源引用与原创建信息；事实改变降为待审核，并可“按原来源重新审核此卡”。重审草稿固定原卡编号与来源，切换卡片立即清空，详情加载时禁止保存；重新审核保存保留创建时间和扩展来源元信息。

2026-10-13 跨文档补证：在同一重审面板中新增默认折叠的“从其他文档补充依据”。复用材料和片段选择器，展示当前字段、连续原文输入及本人/项目/阶段核对；时间、职责、背景采用原文替换，行动和成果逐条追加。采用仅修改草稿，保存沿既有审核按钮。详情可展开字段依据；来源指纹变化显示不可用于生成。年份精度原样保存，不补造月份。`.pen` 的 Evidence 详情同步入口和补证前后状态示意。

**布局**（2026-10-18 起以文末「证据页结构重整」为准，此处为摘要）:
- 顶部: 页面标题 + 刷新 / "从材料提炼"（打开抽屉）/ "New Card / 新增" 主按钮
- 对账汇总条（常驻，计数可点即筛选，右端“重新对账”“运行推断”）
- 内容区两栏:
  - 左栏 (fill): 证据卡列表表格
    - 表头: Title / 标题, Time / 时间（含等级徽标）, Role / 角色（含等级徽标）, Source / 来源数, Status / 状态 + 问题标签
    - 选中行高亮 (accent-bg 背景)
  - 右栏 (420px): 选中卡片详情面板
    - 头部: 状态标签 + 编辑 / 保存 / 取消（文字 + 图标）；删除单独置底
    - 字段: Title / 标题, Time Range / 时间, Role / 角色, Context / 背景, Actions / 行动, Results / 成果（绿色）, Stack & Tags / 技术栈（标签 pills）；字段旁显示等级与来源文档
    - 对账发现（仅问题卡）: 原因、原文候选、分流、待确认推断
    - Artifacts / 附件:
      - 已上传文件列表（文件名、类型、大小、上传时间）
      - 支持预览、删除、重新上传
      - 导入表单折叠在附件区内

**数据字段映射** (对应 `EvidenceCard` 实体):
- title, time_range, context, role_scope, actions, results, artifacts, stack, tags
- `artifacts` 必须在详情面板可见，支持上传后回看与删除，不可只存在于数据模型中

### 4. Jobs / 岗位中心

**职责**: Job Profile + Job Lead 管理

**布局**:
- 顶部: 页面标题 + "New Profile / 新建" 主按钮
- Tab 栏: "Job Profiles / 岗位画像" (激活) | "Job Leads / 岗位线索"
- 卡片网格 (3 列等宽):
  - 卡片内容: 岗位名称 + 状态标签, 描述文本, 技术标签 pills, 分隔线, 统计行 (Match Score / Evidence / Resumes)
  - 激活卡片: cyan 边框; 草稿卡片: 普通边框 + muted 数值
- Job Leads / 岗位线索（次级 Tab）:
  - 猎聘在线搜索独立于本地筛选：输入关键词，主动搜索并导入草稿线索；显示获取/新增数量，区分成功零结果和接口阻断，不自动重试。刷新失败保留已有列表。
  - 官方列表摘要标记“待补完整 JD”，显示来源链接和获取时间；转画像仍为未完整草稿，不凭摘要激活匹配。
  - P0-017A 官方猎聘线索详情提供“获取完整 JD”：成功后将正文/来源填入已有 JD 解析审核区，显式绑定原 lead 与已有 profile，清除旧生成稿；失败保留原稿并显示安全错误。
  - 已绑定正文与来源只读，展示绑定标识及“解除绑定，改为人工导入”。解析/人工审核/保存沿用该身份，保存完整画像更新原岗位；生成稿标题和关键词在审核区独立编辑，不复用另一个已选画像的编辑状态。
  - 切换其他 lead/profile 或清空草稿时清正文、生成稿和绑定；同源解析切换到画像标签保留绑定。显式解除绑定清生成稿但保留正文用于人工导入。获取/解析不自动审批或投递。
  - 主区域: 线索列表表格
    - 表头: Company / 公司, Position / 职位, Source / 来源, Status, Updated At / 更新时间, Action
    - 行数据: 公司名 + 职位名、官方薪资与地区原文, 来源渠道（招聘站/内推/官网）, 当前状态, 最近更新时间, 收藏/转为 Profile；薪资或地区缺失显示“未提供”，不推算金额
  - 右侧详情面板 (420px):
    - 字段: Lead ID, 官方标注薪资、工作地区、来源链接, 职位描述摘要, 关联 Job Profile, 最近跟进记录
    - 操作: 收藏、标记已跟进、转为 "Job Profile / 岗位画像"
  - 支持: 来源/状态筛选、全文搜索、仅看已收藏

2026-10-08 页面接续：Jobs 画像详情增加“使用已保存 JD 生成定制简历”，携带 job_profile_id 到 Quick Run；只对 active 且有 JD 的已保存画像启用。Quick Run 输入区显示职业档案确认状态和所选目标，缺项指回简历中心/证据页；无效链接目标显示错误而非改选首项。结果区增加“查看并准备 PDF”，只使用本次完整、可追溯且有 PDF 的结果，输入变化即清旧结果。Submissions 接收 quick_run_id 仅预填，固定、预览和批准仍沿原按钮；prepared 结果提供前往每日候选清单，空清单回 Jobs。所有导航均不触发生成、平台写入或授权启用。Agent Run 的原生 PDF 候选不展示通用批准/拒绝/跳过按钮，只提供返回该 PDF 审核页的入口；缺失轮次显示未记录，不打印 undefined。

2026-10-11 人工导入来源（P0-022 首片）：画像卡状态标签旁、画像详情副标题与线索行来源列按 `import_mode === "manual"` 显示“人工导入 · 平台名”（`codes.platform.*`），详情附来源记录时间；来源链接按域名识别平台，脉脉 / 拉勾 / BOSS / 智联 / 51job 不做可达性请求。画像详情只读视图末尾新增折叠表单“记录一次手动投递”（投递日期、备注），调用 `submission.recordManual`，成功后通知并可跳转投递记录。

### 5. Quick Run / 快速执行 (原 Pipeline)

2026-10-13 评估与审批质量展示：Quick Run 与固定PDF审批复用同一质量摘要，分别标明本次生成/固定版本；显示岗位适配、正文覆盖、表达规则参考、事实完整性和自动质量状态，并可展开本版缺口。语义结果增加任职/职责/原文子项数量，各要求可逐个查看子项支持与正文呈现状态。Submissions 的历史记录无质量快照时显示未记录，不用旧匹配分推断通过；原批准勾选明确包含已显示质量缺口。`.pen` 保留旧规则图层，新增语义视图说明；较长的Submissions设计画面移至右侧空白区域，保留已有内容。

2026-10-12 P0-026 语义匹配：沿用输入区的模型开关，默认开启“语义匹配全部证据”，关闭为显式规则模式；请求仍绑定所选材料、全部勾选证据和岗位，语义运行总超时 1800 秒。右侧原评分面板在语义结果下显示岗位适配、简历要求覆盖、表达质量及事实完整性，隐藏不适用于该结果的 K/D/S/Q/E/R 条形图；旧规则结果保持原展示。每项要求为默认收起的 details，摘要展示要求和简历状态，展开显示完整要求、证据池判断、理由、原文、证据字段与是否在简历呈现；列表限制高度，可滚动，长原文换行。标明模型判读和引用核验的区别，未知/不足不说成不具备能力；分数不自动改变审批或触发平台动作。`.pen` 的 `Screen/Quick Run` 原输入说明、选卡约束和右侧评分面板同步，示例数值明确为示意数据。

输入区复用已有 evidence_ids 参数增加已审核证据勾选，显示本次选用数量，允许排除旧的重复/单薄卡片；只展示真实可选资格，未审核历史卡不自动混入。模型开关准确标注为“辅助选材”，当前实现不宣称模型自由改写正文。切换岗位时保留已明确选择的有效证据集合，全部取消后不得启动。

**职责**: 4 阶段 pipeline 单次可视化（提炼/匹配/生成/评测）。与 Agent Run 的区别：Quick Run 是一次性执行，不含多轮循环和门禁系统。

运行输入中的材料来源改为明确选择，未选材料时禁用启动；不能自动使用列表首个验收样例。增加“使用模型辅助选材（默认规则选材）”，复用后端参数，默认关闭；已有 LLM 设置保持不变。共享 PDF/HTML 模板优先使用已有 Arial Unicode MS / Noto CJK 等字体，导出验收包含中文可复制文本与视觉检查。

执行结束后，现有 Stage Output 区同步显示 `resume_readiness`：区分“需审核后再投递”与“资料或证据不完整”，展示具体原因。`DONE` 表示 pipeline 执行结束，不表示简历已获投递批准。该说明复用现有日志区域，不新增页面或布局区域。

**布局**:
- 顶部: 页面标题 + "Run / 执行" 主按钮
- 模型配置摘要: 读取 `settings.get.llm_config`，展示 Provider / Model / Base URL / API key configured 状态；不得展示 secret 明文
- 阶段指示条 (4 步, 箭头连接):
  - 已完成: 绿色边框 + circle-check 图标 + 耗时/结果
  - 进行中: cyan 边框 + loader 图标 + elapsed 计时
  - 等待中: 灰色边框 + circle 图标 + "Waiting..."
- 下方两栏:
  - 左栏 (fill): Stage Output / 阶段输出 — 深色终端风格日志面板（JetBrains Mono, 带时间戳）
  - 右栏 (320px): Scores / 评分 — 6 条 ScoreBar (K/D/S/Q/E/R) + 总分

### 6. Agent Run / 自主运行

P0-018 在既有运行区域前增加“每日受控投递”卡片：显示上海自然日确认成功/占位总量、授权状态，提供每日 1–3 上限、上海 HH:mm、到期日期时间及具体岗位/PDF 选择与预览。先保存草稿，再独立勾选平台上传副作用与清单范围，启用或恢复；已启用范围只读，暂停/撤销可在执行中操作。候选不足指回 Jobs → Quick Run → Submissions 的既有准备入口。已上传/已投递候选不重复加入。
2026-10-08 恢复视图沿原每日卡片展开：历史项显示该批成功数/上限、未决数、停止原因和逐项阶段；每个可读快照提供“查看与核验”，带回原 PDF 审核页，不自动检查或发送。上传未确认、中断未决、尚未开始和已确认成功清楚区分；中断结束不改成功/未开始项，原 PDF 页显示仅核验提示并禁用上传、沟通、准备发送和最终发送，保留本地回执核验及已有只读检查。


App 持续运行时每分钟检查到期批次；“执行今日批次”与自动触发共用后端日期锁，不补过去日期。最近日期记录展示成功或短缺原因，当前运行中断后提供“结束中断批次（不重发）”，实际执行期间原生互斥拒绝该动作。关闭/休眠无法保证运行，页面明确说明；按钮防重和原生会话互斥不影响暂停/撤销。设计节点 `daily18` 对应本卡片。

**职责**: 10 状态机、多轮追踪、门禁可视化、事件流

**布局**:
- 顶部: 页面标题（含 Run ID / 开始时间 / 轮次） + Running 状态标签 + "Stop / 停止" 按钮
- 模型配置摘要: 读取 `settings.get.llm_config`，展示 Provider / Model / Base URL / API key configured 状态；不得展示 secret 明文
- 状态机条 (10 节点, 水平排列, space_between):
  - 已完成: 绿色背景 + circle-check 图标 (INIT, DISCOVER, SCORE, GENERATE)
  - 进行中: accent-bg 背景 + cyan 边框 + loader 图标 (EVALUATE)
  - 等待中: bg-inset 背景 + muted 文字 (GATE, REVIEW, DELIVER, LEARN, DONE)
- 下方两栏:
  - 左栏 (fill): N-Pass Gate / 多轮门禁
    - 头部: 标题 + "pass_round: 2 / n_pass_required: 3"
    - 4 行门禁状态 (bg-inset 圆角卡片):
      1. Matching Gate / 匹配门禁 — Score 87 ≥ threshold 70 — PASS (绿色)
      2. Evaluation Gate / 评估门禁 — Eval score 82 ≥ threshold 75 — PASS (绿色)
      3. Channel Ready / 通道就绪 — Checking session... (蓝色, Running)
      4. Company Exclusion / 企业排除 — Not in exclusion list — PASS (绿色)
  - 右栏 (420px): Event Stream / 事件流
    - 带时间戳的事件列表（JetBrains Mono 时间 + 彩色圆点 + 事件描述）
  - 审批面板 (仅 delivery_mode=manual 时在左栏替换 N-Pass Gate 显示):
    - 头部: "Review Candidates / 候选审批" + 当前模式标签 (per-round / batch)
    - 候选卡片列表 (bg-inset 圆角卡片):
      - 每张卡片: 公司名 + 职位 + 匹配分 + 评测分 + 轮次 + 简历版本
      - 2026-09-28：卡片可展开固定版本的简历正文；后台检查 Markdown/PDF 与岗位快照一致后才允许批准，缺失或变化显示阻断，仍可拒绝/跳过。重开页面恢复最近更新的审批运行及其执行结果。
      - 操作: Approve (绿色) / Reject (红色) / Skip (灰色)
    - 底部: "Submit Decisions / 提交决策" 按钮 + 已审批/待审批计数
    - auto 模式下此面板不显示，左栏保持 N-Pass Gate 视图
    - 批准后恢复执行校验并刷新运行状态，单列“审批后的执行结果”；检查通过明确写“未发送”，官方契约阻断、结果未知、真实成功分别显示。已批准未执行项可继续原快照，未知结果暂停全批；不会把批准数当作投递成功数。

**状态机状态**: INIT → DISCOVER → SCORE → GENERATE → EVALUATE → GATE → REVIEW → DELIVER → LEARN → DONE

### 7. Submissions / 投递记录

**职责**: 投递历史、步骤详情、截图、通道降级、重试

“PDF 投递”卡片位于统计行后，复用 Tauri 自有会话、审核快照、既有投递占位和日志，接续 Quick Run 已生成的版本。9 页导航与 Agent Run 的 10 状态机职责保留，最终结果同步到原审批运行。旧 Playwright 通道会话单独保留，不混用认证状态。

完整内容检查复用此卡片的固定版本和批准上传入口（`content01`）：准备时校验职业档案确认、完整正文与关联项目、当前原文及导出 PDF 指纹；未通过时提示回简历中心补齐/重新生成。已有 PDF 字节预览能力在此复用，预览指纹须与快照相符，勾选同时确认内容、岗位适用性和平台副作用。批准仍记入原审核队列，上传及最终发送再次复核；不新增审批页/队列。历史成功可只读查看、核验及按原规则移除附件。

- 登录区：打开 App 内登录、检查 App 内会话、检查附件要求；显示有效/待登录/安全验证/空白/未确认状态。用户手动完成网站认证，App 不接收密码或验证码。
- 反馈同步（2026-10-11）：登录区增加“同步投递反馈（只读）”，仅会话有效时可用。App 在自有猎聘会话内先发现文本含“投递”的站内链接，再只读读取投递记录页，按岗位编号（其次公司+岗位精确匹配）把状态落到各投递记录，列表状态列下方显示平台进展徽标（已投递/已查看/感兴趣/面试邀约/不合适/未识别）与时间，区块内显示最近同步摘要或“未找到投递记录页，已记录候选链接”。同步不发送、不点击业务控件，与原生 PDF 操作互斥；未识别状态保持“未识别”，历史回执与日志不变。反馈卡片的反馈项新增 `platform_delivery_status` 来源，`overview.get` 的 metrics 增加 `feedback_funnel`（总览视觉卡片留到后续切片）。
- 准备区：输入已生成简历的运行编号，固定 PDF 与目标岗位；显示公司/岗位、匹配分、可读 PDF 文件名与完整 SHA256。新 PDF 按“姓名-公司简称-岗位简称-YYYYMMDD.序号.PDF”命名，目录导出与 Quick Run 共用命名记录，同一版本重复导出沿用、同名简称组合当日递增；显式指定文件路径保留。每日候选也显示名称，简称只改文件名，不修改正文/岗位身份；仍超过猎聘限制时在启用/上传前说明原因。历史快照、附件和既有授权不迁移，恢复已有运行不能重建快照或重置额度。
- 批准上传：明确接受“自动补全在线简历及随后续投递附带”的勾选项，已批准的恢复态保留勾选；未批准不能上传。平台文件名限制在上传前校验。上传、未知、附件待核验、附件已绑定分别显示，不能把上传算作投递。
- 投递区：核验目标岗位（只读）→ 开始本次已批准投递 → 检查既有沟通 → 检查发简历确认界面 → 确认投递所选 PDF。开始、简历入口、最终确认均有持久化一次性门禁；确认按钮只在当前会话公司/岗位匹配、确认框唯一选中已绑定 fileId 时启用。2026-10-21：策略配置开启「AI 投递声明」后，发送前先向招聘方发出固定声明，确认送达才继续；卡片显示声明已发送/待发送与实际文案。
- 回执区：`final_send_pending` / `success` 才可“核验本次回执（不重发）”，仅读已保存业务证据。成功后刷新投递表，公司、岗位、版本、父审批运行和回执可追溯；带持久化 attempt 的记录禁用通用重试，后端也拒绝。
- `nativeSessionBusy` 禁用所有并发操作；Error 显示具体错误。`prepared`、`not_submitted` 才可批准上传；未知不能重传；`communication_started` 才可进入简历确认；最终开始后禁止再次确认或现场附件检查，发送时绑定从此冻结。后续平台附件更换不改写历史成功。
- 平台签名附件 URL 仅在内存中用于下载，返回/保存观察（含嵌套 JSON）均去 query/fragment，不进入 UI 或持久化证据。
- 多附件账号按本次上传的 fileId、批准文件名和当前卡片唯一核验，保留其他附件。准备发送确认框时 App 选择唯一匹配的已批准附件，最终发送前再次核对；多项同身份或缺失时禁止发送。附件要求提示包括最多 10 个可见控件标签，总提示最多 20 条，用于说明实际页面状态，读取标签本身不点击网站控件。
- 会话检查识别平台自动跳入的解析同步页：仅在固定 `/resume/parse-result` 且没有登录表单/安全验证时正常返回 `/resume/edit`，重新观察登录状态；不确认解析表单、不补写经历。其他未知状态保持阻断。
- 已成功投递的 PDF 卡片显示平台附件名及“移除此平台附件”入口，独立勾选确认后才启用。App 先重验该已完成运行的回执、本地原件和当前附件字节，再操作唯一对应卡片。原页面已有菜单/对话框、身份重复/变化或缺少明确确认框时不执行最终删除；在途/未知/已移除时禁用重复操作。显示 removed、not_submitted、unknown 三种结果，本地批准快照与投递成功保持不变。 已成功记录的“检查已保存附件（不重传）”保持可用且只读：App 用新鲜的附件页观察与已冻结的发送绑定对账，当前页面没有该 fileId/encryAttachmentId 卡片时显示“平台附件已不在（可能在 App 外移除）”并禁用移除勾选与按钮，本地 PDF、快照、回执不变；缺少卡片计数的观察不做任何平台结论。
- 删除请求在发出前还须由程序核对精确附件 ID 与一次性限制，防止通用弹窗目标变动造成错删；不是收到错误目标回执后才判断失败。
- 对带“经历可同步至在线简历中 / 无需手动填写，可直接添加到在线简历中”的唯一只读解析预览，且无输入字段并有唯一关闭按钮时，App 可先关闭提示；不点击查看或同步。其余既有弹窗仍阻断移除。
- 移除结果 unknown 时提供“核验上次移除（不重删）”。此操作只读取原守卫记录并重新检查当前附件；仅有明确请求前拦截和同一原文件仍在的证据才能恢复 not_submitted。曾放行请求或缺证据时仍禁止重试，不直接再次删除。

2026-10-01 结果与反馈收口：详情页统一显示默认简历/PDF 路线、回执来源、批准版本、简历/回执指纹和“本地投递证据完整/不完整”；不完整保留原业务状态。列表及详情内同通道/邮件重试均按 `retry_allowed` 禁用。

反馈卡片允许选择历史投递（公司、岗位、提交编号）并同步打开详情，选择后加载该记录的历史反馈、批准版本及可用动作。真实投递表单包含来源（默认个人复盘/手动招聘反馈）、下一步动作和必填内容；不预填招聘方评价。空内容、加载或保存中禁止提交，切换目标清空草稿且丢弃过期读回结果。保存后显示时间、来源、内容和动作，重开页面可读回。补证据/调整岗位/重新生成分别提供既有页面入口；重新生成同时显示原岗位画像编号，须在 Quick Run 明确选择和审核。保存只记录计划，不创建伪新版本、不自动投递；旧 Check Mode 反馈入口保留。

通道会话区域沿用“开始配置 / 检查 / 清除会话”三个操作：开始配置通过 Python 后端打开专用 Playwright 登录窗口；用户登录后点击检查，由浏览器正向信号判断登录状态，验证成功保存 profile 并关闭窗口。前端不再提交登录信号或账号身份。窗口关闭、导航失败或缺少运行依赖必须显示真实失败，不能伪造已打开/已登录。此功能不依赖 Chrome DevTools MCP；原生登录成功与实际附件投递分开验收。 开始配置使用官网首页的真实登录表单，确认输入框可见才等待人工登录；失败后刷新后端状态。

**布局**:
- 顶部: 页面标题
- 统计卡片行 (4 列): Total / 总投递 (23), Delivered / 成功 (18), Failed / 失败 (3), Fallback / 降级 (2)
- 投递表格:
  - 表头: Company / 公司, Position / 职位, Channel / 通道, Date / 日期, Status, Action
  - 行数据:
    - 公司名（中英文）+ SUB-ID
    - 通道: Liepin (cyan) / Email ↩ (warning, 降级标识)
    - 状态: Done (绿) / Fallback (黄) / Failed (红)
    - 操作: eye 查看详情 / rotate-ccw 重试
- 详情抽屉/侧板:
  - 基本信息: SUB-ID, Company, Position, Channel, Status, Submitted At
  - Step Timeline / 步骤时间线: 打开职位、填写表单、上传简历、提交结果、降级重试
  - Screenshots / 截图: 缩略图列表 + 放大预览
  - Failure Detail / 失败详情: 错误原因、原始响应、最近一次重试结果
  - Retry Strategy / 重试策略: 原通道重试、降级到 Email、查看失败原因

2026-10-11 手动投递记录：人工导入平台的投递由用户在 App 外完成后回填，记录通道为平台码（列表显示平台中文名）、状态“手动记录”、模式“人工”、步骤“手动记录投递”、回执来源 `manual_tracking`；不可重试，不计自动确认数，可作为反馈迭代的关联投递。

### 8. Policy / 策略配置

**职责**: Policy 编辑器、企业例外清单、投递/门禁策略治理

2026-10-21 AI 投递声明：门禁策略分组底部新增「AI 投递声明」卡，提供默认关闭的开关（改动即时保存，不走页面“保存”按钮）、固定声明文案预览与边界说明。开启后，每次原生 PDF 投递会先在目标猎聘沟通会话向招聘方发送一条固定的 AI 自动化声明（简历与投递操作由 AI 自动化执行），确认送达后才继续发简历；声明未确认时本次投递被阻断。文案固定于 `tools/infra/ai_disclosure.py`，开关保存在本机 `policy.local.yaml` 的 `ai_disclosure_enabled`；Submissions 的 PDF 投递卡片显示声明已发送/待发送状态。`.pen` 本轮未同步（本机无 Pencil 工具），需在 Pencil 中补该卡片与开关。

**布局**:
- 顶部: 页面标题 + "Save / 保存" 主按钮
- 内容区两栏:
  - 左栏 (220px): 策略分组导航
    - Gate Policy / 门禁 (激活)
    - Exclusion List / 排除
  - 右栏 (fill): 策略表单区域
    - Gate Policy / 门禁:
      - 每个字段: 标签(中英文) + 描述 + 输入框
      - n_pass_required / 通过轮数: 3
      - matching_threshold / 匹配阈值: 70
      - evaluation_threshold / 评估阈值: 75
      - max_rounds / 最大轮次: 5
      - gate_mode / 门禁模式: strict
      - delivery_mode / 投递模式: auto（下拉选择: auto | manual）
      - batch_review / 批量审批: false（开关，仅 delivery_mode=manual 时可用）
      - AI 投递声明 / AI disclosure: 开关（即时保存）+ 固定声明文案预览 + 边界说明
    - Exclusion List / 排除:
      - 企业名列表 + 添加/删除 + 导入/导出
      - 命中说明: 为什么被排除、命中时间、备注
      - legal entity / 主体排除与 alias / 别名排除分区展示

### 9. System Settings / 系统设置

**职责**: 通道配置、模型配置、凭证状态、连通性检查

2026-10-20 DeepSeek Provider 接入：模型分组新增 DeepSeek 预设、thinking 开关与 low/high/max 思考强度；API Key 改为按 provider 保存到本机 0600 权限文件，新增按 provider 的已配置状态、环境变量来源提示与清除入口；连接检查使用 provider 名称并在缺密钥时阻断。LLM 配置改为紧凑单卡：provider 分段选择、密钥状态内联、思考开关与强度同排；`.pen` 同步该布局，截图见 `outputs/pen-sync-20261021/system-settings-llm-screen.png`、`outputs/pen-sync-20261021/llm-config-compact.png` 与真实 React 渲染 `outputs/pen-sync-20261021/react-system-settings.png`；`.pen` 主文件已保存。

2026-10-21 Strata Provider 接入：模型分组在 LM Studio 之后新增 Strata 本地 provider 预设（base_url `http://127.0.0.1:8081/v1`、model `qwen3.8-flash-next-q2_0`），provider 卡改为 5 列。Strata 本地回环默认免鉴权：无 Key 时显示「本地服务，无需密钥（可选）」且按可用状态展示，可选 serving API Key 仍按 provider 保存到本机 0600 文件并支持清除；Overview / Quick Run / Agent Run 共用 `ui/src/lib/llmConfig.ts` 的 keyless 判定，不再把无 Key Strata 显示为未配置。思考开关扩展为 DeepSeek / Strata 共用；Strata 通过请求顶层 `reasoning_effort` 控制（关闭/结构化输出为 `none`，开启后 low / high，`max` 归一到 `high`），不发送 DeepSeek 风格 `thinking` 对象。Quick Run 子进程管线使用同一 keyless 判定，无 Key 时不视为凭证缺失、不注入伪造占位 Key，请求头不带 `Authorization`。`.pen` 本轮未同步（本机无 Pencil 工具），需在 Pencil 中补 Strata 选项、5 列 provider 卡与思考开关条件。


**布局**:
- 顶部: 页面标题 + "Save / 保存" 主按钮
- 内容区两栏:
  - 左栏 (220px): 系统分组导航
    - Channels / 通道 (激活)
    - Material sources / 材料来源
    - Evidence inference / 证据推断
    - LLM Config / 模型
  - 右栏 (fill): 系统配置区域
    - Channels / 通道:
      - P0-011 猎聘官方只读卡：系统浏览器打开固定官方 `/mcp/auth` 授权入口（失败显示提示和可复制地址）、password Token 输入、保存到本机、验证、删除已保存凭据、读取平台简历；输入提交后立即清空。
      - 2026-09-28 按用户选择使用本机明文权限文件，不接入钥匙串；凭据目录 `0700`、文件 `0600`，重启自动读取为待验证，正常退出不删除保存项。展示后台返回的 `storage_path` 供管理；回读 `configured/state/code/saved`、检查时间及固定安全错误，不包含 Token 或掩码值，不写入 localStorage 或日志。
      - 状态区分未配置、待验证、有效、失效、限流和凭据/连接异常；保存、读取、删除文件失败显示后台固定安全错误或 `CREDENTIAL_STORAGE_ERROR` 提示，不伪装成保存或删除成功。`configured || saved || code === CREDENTIAL_STORAGE_ERROR` 时允许删除，验证/读取简历仍须 `configured`，处理中禁用重复操作。
      - 读取的简历仅折叠纯文本预览，不持久化、不覆盖资料，删除/替换/失败清除预览。
      - 原有浏览器投递通道另行展示，明确其与官方只读认证独立；只读连接有效不表示投递可用。
      - Liepin / Email 独立通道、优先级与凭证状态；当前按目标平台路由，不自动跨通道降级
      - 支持测试连接与最近一次可用性检查
      - 显示可选通道、最近错误与最近成功时间；历史 fallback 记录保留，不代表当前允许自动降级
    - LLM Config / 模型:
      - provider（LM Studio / Strata / OpenAI / DeepSeek / OpenAI Compatible，5 列卡片）、model、base_url、api_key（掩码）、timeout、temperature
      - DeepSeek 预设：base_url `https://api.deepseek.com`、model `deepseek-flash`；支持 `/models` 发现与连接检查
      - Strata 预设：base_url `http://127.0.0.1:8081/v1`、model `qwen3.8-flash-next-q2_0`；本地回环默认免鉴权，无 Key 显示「本地服务，无需密钥（可选）」并按可用状态展示，可选 serving API Key 仍按 provider 保存与清除
      - 思考模式开关对 DeepSeek / Strata 显示，默认关闭：DeepSeek 按 low / high / max 选择强度（thinking 对象，思考模式下温度不生效）；Strata 按 low / high 选择强度（顶层 `reasoning_effort`，关闭与结构化输出为 `none`，`max` 归一到 `high`）
      - `api_key` 按 provider 分别保存到本机权限文件（目录 `0700`、文件 `0600`），不进入 localStorage、日志或 `policy.local.yaml`；页面只显示已保存 / 来自环境变量 / 本地占位 / 本地可选 / 未配置状态，并支持清除
      - 未提供真实密钥的在线 provider 不得显示为可用；LM Studio 保留本地 `lm-studio` 占位密钥，Strata 无需密钥即可用
      - 支持校验、连通性测试、模型发现；切换 provider 时清空上一 provider 的检测结果
      - 2026-10-21 `.pen` 待补：Strata 选项、5 列 provider 卡与 Strata 思考开关条件；本机无 Pencil 工具，未以源码测试替代画布

---

## 页面层级图 / 信息架构树

整体结构以 `3 级信息架构 + 4 层视觉布局` 为主：

- `第 1 级`: 全局导航层（SideNav + 9 个一级页面）
- `第 2 级`: 页面功能层（Header、主内容区、页面主动作）
- `第 3 级`: 模块交互层（表格、卡片、详情面板、日志区、表单区）
- `第 4 层`: 仅在复杂页面出现的明细层（Artifacts、Screenshots、Step Timeline、子配置字段等）

```text
PiProofForge
├── 1. App Shell
│   ├── SideNav
│   │   ├── Overview
│   │   ├── Resumes
│   │   ├── Evidence
│   │   ├── Jobs
│   │   ├── Quick Run
│   │   ├── Agent Run
│   │   ├── Submissions
│   │   ├── Policy
│   │   └── System Settings
│   └── Main Content
│
├── 2. Overview
│   ├── Header
│   │   ├── Page Title
│   │   └── Run Agent
│   ├── Metrics Row
│   │   ├── Evidence
│   │   ├── Matched Jobs
│   │   ├── Resumes
│   │   └── Submissions
│   └── Two-Column Content
│       ├── Recent Activity
│       └── Right Rail
│           ├── Match Trend
│           └── Gaps
│
├── 3. Resumes
│   ├── Header
│   │   ├── Page Title
│   │   ├── Upload Resume
│   │   └── Export PDF
│   └── Three-Column Content
│       ├── Personal Profile
│       │   ├── Basic Info
│       │   ├── Profile Status
│       │   └── Edit Action
│       ├── Uploaded Resumes
│       │   ├── Resume List
│       │   └── File Actions
│       └── Generated Resumes
│           ├── Generated List
│           └── Preview Panel
│               ├── Preview Header
│               └── Resume Paper
│
├── 4. Evidence
│   ├── Header
│   │   ├── Page Title
│   │   ├── New Card
│   │   └── Import
│   └── Two-Column Content
│       ├── Evidence Table
│       │   ├── Header Row
│       │   └── Data Rows
│       └── Detail Panel
│           ├── Basic Info
│           ├── Context / Actions / Results
│           ├── Stack & Tags
│           └── Artifacts
│               ├── File List
│               ├── Preview
│               ├── Delete
│               └── Re-upload
│
├── 5. Jobs
│   ├── Header
│   │   ├── Page Title
│   │   └── New Profile
│   ├── Tabs
│   │   ├── Job Profiles
│   │   └── Job Leads
│   └── Content
│       ├── Profiles View
│       │   └── Card Grid
│       └── Leads View
│           ├── Filter/Search
│           ├── Leads Table
│           └── Lead Detail Panel
│               ├── Basic Info
│               ├── Summary
│               ├── Related Profile
│               └── Follow-up Actions
│
├── 6. Quick Run
│   ├── Header
│   │   ├── Page Title
│   │   └── Run
│   ├── Stage Bar
│   │   ├── Extract
│   │   ├── Match
│   │   ├── Generate
│   │   └── Evaluate
│   └── Two-Column Content
│       ├── Stage Output / Log Panel
│       └── Scores Panel
│           ├── K
│           ├── D
│           ├── S
│           ├── Q
│           ├── E
│           └── R
│
├── 7. Agent Run
│   ├── Header
│   │   ├── Page Title
│   │   ├── Run Meta
│   │   └── Stop
│   ├── State Machine Row
│   │   ├── INIT
│   │   ├── DISCOVER
│   │   ├── SCORE
│   │   ├── GENERATE
│   │   ├── EVALUATE
│   │   ├── GATE
│   │   ├── REVIEW
│   │   ├── DELIVER
│   │   ├── LEARN
│   │   └── DONE
│   └── Two-Column Content
│       ├── N-Pass Gate
│       │   └── Gate Items
│       │       ├── Matching Gate
│       │       ├── Evaluation Gate
│       │       ├── Channel Ready
│       │       └── Company Exclusion
│       ├── Review Panel (manual mode only)
│       │   └── Candidate Cards
│       │       ├── Candidate Info
│       │       └── Actions (Approve / Reject / Skip)
│       └── Event Stream
│           └── Event Items
│
├── 8. Submissions
│   ├── Header
│   │   └── Page Title
│   ├── Metrics Row
│   │   ├── Total
│   │   ├── Delivered
│   │   ├── Failed
│   │   └── Fallback
│   └── Content
│       ├── Submission Table
│       └── Detail Drawer / Side Panel
│           ├── Basic Info
│           ├── Step Timeline
│           ├── Screenshots
│           ├── Failure Detail
│           └── Retry Strategy
│
├── 9. Policy
│   ├── Header
│   │   ├── Page Title
│   │   └── Save
│   └── Two-Column Content
│       ├── Policy Nav
│       │   ├── Gate Policy
│       │   └── Exclusion List
│       └── Config Form Area
│           ├── Gate Policy Fields
│           └── Exclusion List Management
│
└── 10. System Settings
    ├── Header
    │   ├── Page Title
    │   └── Save
    └── Two-Column Content
        ├── System Nav
        │   ├── Channels
        │   └── LLM Config
        └── Config Form Area
            ├── Channel Settings
            └── LLM Config Fields
```

该层级图用于统一设计评审、组件拆分和前端实现边界：

- Overview、Quick Run：偏 `2.5 级`，以单页摘要和单次操作为主
- Jobs、Resumes、Agent Run：偏 `3 级`，含明显的中层模块切分
- Evidence、Submissions、Policy、System Settings：可达 `4 级`，存在详情、附件、步骤流或子配置层

### 页面层级覆盖对照表

| 页面 | L1 全局导航 | L2 页面功能层 | L3 模块交互层 | L4 明细层 | 当前判定 | 主要缺口 |
|------|-------------|---------------|---------------|-----------|----------|----------|
| Overview | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | 趋势摘要卡与缺口卡片已显式拆分 |
| Resumes | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | 已拆分为个人资料、已上传简历、系统生成简历与预览区 |
| Evidence | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | 详情字段卡与 Artifacts 卡片已显式拆分 |
| Jobs | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | Leads 已拆出筛选、列表，详情区已显式拆成 Summary / Related Profile / Follow-up Actions |
| Quick Run | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | 模型配置摘要、日志条目与总评分块已显式拆分 |
| Agent Run | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | 模型配置摘要、Gate Items 与 Event Items 已显式拆分 |
| Submissions | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | 详情侧板已拆出时间线、截图、Failure Detail、重试策略 |
| Policy | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | Gate Policy、Exclusion List 已显式拆成独立分组与字段卡 |
| System Settings | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | Channels、LLM Config 已显式拆成独立分组与字段卡 |

本轮 Pencil 补齐结果：

- 已完成 `Overview`
- 已完成 `Evidence`
- 已完成 `Quick Run`
- 已完成 `Resumes`

### Pencil 画布落地要求

为避免设计稿只停留在“单块文本占位”，`ui/design/piproofforge.pen` 中的页面结构必须显式表达层级：

- 页面至少拆成 `Header -> Section -> Module`，禁止用一大段文本代替二级分组
- 存在详情流的页面必须显式拆出 `Table/List` 与 `Detail Panel/Drawer`
- 存在流程流的页面必须显式拆出 `Gate Items`、`Event Items`、`Timeline`、`Screenshots` 等三级块
- 配置类页面必须显式拆出 `Module Nav` 与 `Field Cards`，而不是纯文本列表
- Pencil 中的层级表达应能直接支持前端组件拆分，不依赖阅读长段描述自行脑补结构

---

## 已定版设计组件清单

以下组件表示设计规范与 Pen 资产已经定版，不表示代码层已经实现。

| 组件 | Pen ID | 用途 |
|------|--------|------|
| SideNav | `vfxIc` | 侧边导航栏，含 Logo + 9 个导航项 + 底部状态区（sidecar 状态 `k1BGB` + 语言切换），高度按内容自适应 |
| NavItem | `TISge` | 普通导航项（icon + label） |
| NavItemActive | `tUedS` | 激活导航项（accent 高亮） |
| StatusChip/Success | `knPKe` | 成功状态标签 (绿色) |
| StatusChip/Failed | `toEtU` | 失败状态标签 (红色) |
| StatusChip/Running | `pvF9u` | 运行中状态标签 (蓝色) |
| StatusChip/Pending | `RTezv` | 待处理状态标签 (黄色) |
| StatCard | `YERs6` | 统计数字卡片 (icon + 数值 + 标签) |
| ScoreBar | `4deiE` | 评分条 (维度标签 + 进度条 + 分值) |
| Button/Primary | `xWWct` | 主按钮 (cyan 高亮, icon + label) |
| Button/Secondary | `tBGQE` | 次按钮 (panel bg + border, icon + label) |
| Button/Danger | `YBWSR` | 危险按钮 (error 实色)，位于 Feedback/ConfirmDialog 内，用于破坏性操作的确认 |
| Feedback/Toast | `fQ00F` | 右下角通知；成功/信息 5 秒自动消失，错误需手动关闭，最多 4 条，相同内容去重 |
| Feedback/ConfirmDialog | `FQxJ2` | 全局确认框；Esc 取消，默认焦点在“取消”，Tab 在两个按钮间循环 |

补充约束：`SideNav` 在设计稿中允许按内容高度展示，不强制撑满 900px 页面全高；实现阶段应保证其与主内容区在视觉上对齐，不因固定高度导致底部语言切换入口不可见。

### StatusChip 子节点 ID 映射

| 变体 | Dot ID | Label ID |
|------|--------|----------|
| Success | `BApjD` | `0Dbcn` |
| Failed | `Lh2vS` | `QDnff` |
| Running | `0mj1w` | `pxPir` |
| Pending | `jpEkA` | `2mbtN` |

### 未单独建组件但页面内复用的模式

- **表格行**: horizontal frame + cell frames (固定宽度列 + fill 标题列)
- **面板结构**: 圆角 frame + bg-inset header (44px) + content body
- **门禁行**: bg-inset 圆角卡片 + icon + info(name + desc) + status chip
- **事件行**: 时间戳 + 彩色圆点 + 事件描述
- **表单字段**: label + description + input frame
- **标签 pill**: 圆角 frame + accent-bg + accent 文字

---

## Design Tokens (终版基线)

### Colors

| Token | Value | Usage |
|-------|-------|-------|
| bg-primary | #071023 | 主背景 |
| bg-secondary | #101B35 | 辅助背景 |
| bg-panel | #1E293B | 面板/卡片背景 |
| bg-panel-hover | #334155 | 面板悬停 |
| bg-inset | #0F172A | 内嵌区域（表头、日志区） |
| sidebar-bg | #0A0F1C | 侧边栏背景 |
| sidebar-active | #164E63 | 侧边栏激活项 |
| accent | #38BDF8 | 强调色/链接 |
| accent-cyan | #22D3EE | 高亮强调（分数、活跃状态） |
| accent-bg | #0C4A6E | 强调背景（选中行、激活标签） |
| text-primary | #EEF4FF | 主文本 |
| text-secondary | #94A3B8 | 次要文本 |
| text-muted | #64748B | 弱化文本（标签、时间戳） |
| success | #34D399 | 成功（通过、完成） |
| warning | #FBBF24 | 警告（缺口、降级） |
| error | #F87171 | 错误（失败、缺失） |
| border | #1E293B | 边框 |
| border-light | #334155 | 浅边框（输入框） |

### Typography

| 用途 | Font | Weight | Size |
|------|------|--------|------|
| 页面标题 | Inter | 700 | 22px |
| 面板标题 | Inter | 600 | 14px |
| 正文/行文本 | Inter | 500-600 | 13px |
| 描述文本 | Inter | 400 | 13px |
| 小标签 | Inter | 600 | 12px |
| 字段标签 | Inter | 600 | 11px |
| 数值/代码 | JetBrains Mono | 700 | 13-32px |
| 日志/时间戳 | JetBrains Mono | 400-500 | 11px |
| 状态标签 | Inter | 600 | 12px |
| 标签 pill | Inter | 600 | 11px |

### Spacing

| Token | Value |
|-------|-------|
| spacing-xs | 4px |
| spacing-sm | 8px |
| spacing-md | 12px |
| spacing-lg | 16px |
| spacing-xl | 24px |
| spacing-2xl | 32px |

### Radius

| Token | Value | Usage |
|-------|-------|-------|
| radius-sm | 8px | 标签、输入框、小卡片 |
| radius-md | 12px | 面板、大卡片 |
| radius-lg | 16px | 大容器 |
| radius-pill | 999px | 状态标签 |

### Shadows

| Token | Value | Usage |
|-------|-------|-------|
| shadow-sm | 0 1px 2px rgba(0,0,0,0.3) | 输入框、轻量悬浮 |
| shadow-md | 0 4px 6px rgba(0,0,0,0.4) | 下拉、浮层、抽屉 |
| shadow-lg | 0 10px 15px rgba(0,0,0,0.5) | Modal、重点悬浮容器 |

### Layering

| Token | Value | Usage |
|-------|-------|-------|
| `--z-nav` | 100 | 侧边导航 |
| `--z-drawer` | 150 | 覆盖式抽屉（如证据页提炼抽屉），盖过侧栏、低于对话框 |
| `--z-modal` | 200 | 确认对话框、模态遮罩 |
| `--z-toast` | 300 | Toast 全局浮层 |

页内 sticky 元素（页头 `z-20`、表头 `z-10`）不使用上述 token。实际值以 `ui/src/styles/tokens.css` 为准，使用方式为 `z-[var(--z-xxx)]`。

### Motion

| Token | Value | Usage |
|-------|-------|-------|
| duration-fast | 100ms | hover、高频轻交互 |
| duration-normal | 200ms | 面板切换、抽屉展开 |
| duration-slow | 300ms | Modal、页面级过渡 |
| easing-default | cubic-bezier(0.4, 0, 0.2, 1) | 默认缓动 |

### Tailwind / Theme Mapping

- 所有 Token 必须先映射为 CSS variables（建议命名: `--color-bg-primary`, `--spacing-lg`, `--radius-md`），再由 Tailwind theme 引用，禁止在组件中硬编码色值
- Tailwind 侧至少暴露以下语义别名: `bg-primary`, `bg-panel`, `text-primary`, `text-secondary`, `border-default`, `accent`, `success`, `warning`, `error`
- 明暗或主题扩展必须通过变量覆盖实现；组件 class 名保持稳定，不允许通过页面级临时 class 覆盖 Token
- 阴影、圆角、层级、动画时长同样需要进入 Tailwind theme/token 层，不允许只在单个组件内内联定义
- Pen 设计稿、CSS variables、Tailwind config 三者命名需一一对应，允许存在格式差异（如 `bg-primary` → `--color-bg-primary`），但禁止语义漂移

建议映射:

| Token Family | CSS Variable 示例 | Tailwind Theme Key |
|--------------|-------------------|--------------------|
| Colors | `--color-bg-primary` | `theme.colors.bg.primary` |
| Spacing | `--spacing-lg` | `theme.spacing.lg` |
| Radius | `--radius-md` | `theme.borderRadius.md` |
| Shadows | `--shadow-md` | `theme.boxShadow.md` |
| Layering | `--z-modal` | `theme.zIndex.modal` |
| Motion | `--duration-normal`, `--easing-default` | `theme.transitionDuration.normal`, `theme.transitionTimingFunction.default` |

---

## 命名与标签规范

### 命名总规则

- 页面 / 导航 / 按钮 / 面板标题：统一使用 `English / 中文`
- 技术标识、代码值、协议方法名：统一纯英文
- 状态标签：统一纯英文
- 支持性设计板块（状态稿、约束稿、协议稿）：不使用双语对照规则，单独命名
- 同一概念只能有一组中文主译名，不允许在不同位置语义漂移

### 四类标签规范

#### 1. 用户可见主标签

- 适用：页面标题、导航、CTA、表头、面板标题、设置分组
- 格式：`English / 中文`
- 例：`Run Agent / 启动`

#### 2. 状态标签

- 适用：`Done`、`Failed`、`Running`、`Fallback`、`PASS`
- 格式：纯英文
- 禁止写成 `Done / 成功`、`Failed / 失败`

#### 3. 技术标签

- 适用：`JSON-RPC`、`sidecar`、`EC-007`、`SUB-023`、`system.handshake`
- 格式：纯英文

#### 4. 支持性板块标签

- 适用：状态稿、约束稿、协议稿
- 格式：建议纯英文标题；必要时可用英文副标题解释，但不使用 `English / 中文`
- 例：`State Screens`、`Implementation Constraints`

### 统一术语表

| English | 中文主译名 | 备注 |
|---------|------------|------|
| Overview | 概览 | 页面名 |
| Evidence | 证据卡 | 页面名 |
| Jobs | 岗位中心 | 页面名 |
| Quick Run | 快速执行 | 页面名 |
| Agent Run | 自主运行 | 页面名 |
| Resumes | 简历中心 | 页面名 |
| Personal Profile | 个人资料 | Resumes 页面分区 |
| Basic Info | 个人基本信息 | Resumes 页面分区 |
| Uploaded Resumes | 已上传简历 | Resumes 页面分区 |
| Generated Resumes | 系统生成简历 | Resumes 页面分区 |
| Submissions | 投递记录 | 页面名 |
| Policy | 策略配置 | 页面名 |
| System Settings | 系统设置 | 页面名 |
| Matched Jobs | 匹配岗位 | 统计项 |
| Resumes | 简历版本 | 仅统计项 |
| Submissions | 投递次数 | 仅统计项 |
| Gate Policy | 门禁 | 设置分组 |
| Exclusion List | 排除 | 设置分组 |
| Channels | 通道 | 设置分组 |
| LLM Config | 模型 | 设置分组 |
| Stage Output | 阶段输出 | 面板标题 |
| Event Stream | 事件流 | 面板标题 |
| Failure Detail | 失败详情 | 面板标题 |
| Retry Strategy | 重试策略 | 面板标题 |

### 必须收平的现有不一致

- `Resumes / 简历中心` 与 `Resumes / 简历版本`
  - 页面名固定：`Resumes / 简历中心`
  - 统计卡固定：`Resumes / 简历版本`
- `Personal Profile` 相关旧译名
  - 统一改为：`Personal Profile / 个人资料`
- `Basic Info` 相关旧译名
  - 统一改为：`Basic Info / 个人基本信息`
- `Submissions / 投递`、`Submissions / 投递记录`、`Submissions / 投递次数`
  - 导航 / 页面固定：`Submissions / 投递记录`
  - 统计卡固定：`Submissions / 投递次数`
- `Evidence Cards / 证据列表`
  - 统一改为：`Evidence Cards / 证据卡列表`
- `Export PDF`
  - 统一改为：`Export PDF / 导出 PDF`
- `Overview / Loading`、`Submissions / Drawer Overlay`
  - 不继续使用双语 slash 规则
  - 应改为支持性板块命名，例如：`Overview - Loading`、`Submissions - Drawer`

### 支持性板块命名规则

支持性板块顶层名称固定为：

- `State Variants`
- `State Screens`
- `Implementation Constraints`
- `Protocol & Runtime Contracts`

这些板块中的子屏命名统一如下：

- 状态稿：`<Page> - <State>`
  - `Overview - Loading`
  - `Evidence - Empty`
  - `Quick Run - Error`
  - `Agent Run - Offline`
- 约束稿：`<Page> - <Constraint>`
  - `Evidence - Controls`
  - `Submissions - Drawer`
  - `Overview - Min Width 1280`
- 协议稿：纯英文
  - `Protocol Contracts`
  - `Sidecar Lifecycle`
  - `Error Code Baseline`

### 实现例外

- 技术标签 pill（如 `Kubernetes`、`React`）保持英文
- 代码值（如 `EC-007`、`SUB-023`）保持英文
- 状态标签（如 `Pass`、`Done`、`Failed`、`Running`）保持英文

### 命名治理执行顺序

1. 先把 `DESIGN.md` 的规则写死
2. 再按术语表批量收平 `.pen`
3. 最后用这套规则更新 review checklist

---

## 页面 Pen 节点 ID 映射

| 页面 | Frame ID |
|------|----------|
| Screen/Evidence | `JntHF` |
| Screen/Overview | `nXKt2` |
| Screen/Agent Run | `ZSLCx` |
| Screen/Jobs | `FLWrf` |
| Screen/Policy | `OGiSD` |
| Screen/Quick Run | `ihiWw` |
| Screen/Resumes | `nX2o7` |
| Screen/Submissions | `upl7d` |
| Screen/System Settings | `FWOoc` |

---

## 架构审核改进项

基于终版 UI 架构审查（2026-03-07），以下内容已冻结为正式要求：

### 已定版 (设计层)

- [x] Pipeline 重命名为 **Quick Run / 快速执行**，与 Agent Run 明确区分语义
- [x] 导航顺序调整为用户旅程: 概览 → 简历 → 证据 → 岗位 → 快速执行 → 自主运行 → 投递 → 策略配置 → 系统设置
- [x] Quick Run 导航图标从 `play` 改为 `zap`，与 Agent Run 的 `bot` 视觉区分
- [x] SideNav 底部添加语言切换入口 (EN / 中)

### 正式实现要求 (代码层)

#### 1. i18n 国际化策略 (P0 — 最高优先)

**禁止硬编码双语字符串**。设计稿中的 `English / 中文` 格式仅为视觉参考。

实现方案:
```
ui/src/i18n/
  ├── en.json    # { "nav.overview": "Overview", "nav.evidence": "Evidence", ... }
  ├── zh.json    # { "nav.overview": "概览", "nav.evidence": "证据卡", ... }
  └── index.ts   # useI18n() hook, t('key') function
```

规则:
- 所有 UI 文本通过 `t('key')` 引用
- 语言切换存储到 localStorage，随 SideNav 底部按钮切换
- 技术标签 pill、代码值、状态标签保持英文不翻译

#### 2. 缺失通用组件 (P1 — 高优先)

以下模式在多页面出现，应在代码层抽象为通用组件:

| 组件 | 使用页面 | 说明 |
|------|---------|------|
| DataTable | Evidence, Submissions | 表头 + 数据行 + 选中态 + 排序 |
| FormField | Policy, System Settings | 标签 + 描述 + 输入框 + 验证状态 |
| Modal | 全局 | 遮罩 + 内容区 + 确认/取消 (删除确认、导出配置等) |
| LoadingOverlay | 全局 | 页面/面板级加载遮罩 |
| ErrorBoundary | 全局 | 错误捕获 + 降级 UI |
| OfflineIndicator | 全局 | Python sidecar 断连提示 |

StatusChip 4 个变体建议在代码中合并为参数化组件:
```tsx
<StatusChip type="success" label="Pass" />
<StatusChip type="failed" label="Failed" />
```

#### 3. Design Tokens 落地要求 (P2)

本文件中的 Colors / Typography / Spacing / Radius / Shadows / Layering / Motion 已构成终版 Token 基线。代码实现时必须完整映射，不得只实现其中一部分。

#### 4. 页面数据契约与列表规则 (P1)

列表型页面统一规则:
- 默认分页策略: 首屏 `page_size = 20`，支持 cursor-based pagination；仅本地纯静态列表允许一次性加载
- 默认排序字段必须显式声明；未声明时禁止依赖后端自然顺序
- 默认筛选项必须有 UI 占位和空值语义，禁止“接口支持但界面不暴露”
- 列表请求参数统一建议结构:

```json
{
  "cursor": null,
  "page_size": 20,
  "sort": {
    "field": "updated_at",
    "order": "desc"
  },
  "filters": {}
}
```

页面最小数据契约:
- Overview: `{ metrics, recent_activities[], match_trend[], gaps[] }`；无分页；`Error` 触发条件为任一核心聚合请求失败
- Evidence: `list` 返回 `{ items[], next_cursor }`，支持 `query/status/role/tags/date_range` 筛选，支持 `updated_at/score` 排序；`detail` 返回完整 `EvidenceCard + artifacts[]`
- Jobs/Profiles: 返回 `{ items[], next_cursor }`，支持 `status/query/tags` 筛选，支持 `match_score/updated_at` 排序
- Jobs/Leads: 返回 `{ items[], next_cursor }`，支持 `source/status/favorited/query` 筛选，支持 `updated_at/created_at` 排序
- Quick Run: 输入契约至少包含 `evidence_id`, `job_profile_id`, `options`；结果契约至少包含 `stage_results[]`, `scores`, `logs[]`；页面通过 `settings.get.llm_config` 展示 provider summary，不从 run result 读取 secret
- Agent Run: 返回 { run, gate_checks[], events[], next_event_cursor, review_candidates[], review_decisions[] }；事件流分页必须支持 cursor + limit；review_candidates 仅在 delivery_mode=manual 且状态为 REVIEW 时有值；页面通过 `settings.get.llm_config` 展示 provider summary，不从 run result 读取 secret
- Resumes: 页面至少需要 `personal_profile`、`uploaded_resumes[]`、`generated_resumes[]` 与当前选中版本的 `preview` 载荷；首版 bridge 可通过聚合现有 profile 源与 resume list 完成，不强制在本轮冻结为单一 RPC 方法
- Submissions: 返回 `{ items[], next_cursor }`，支持 `company/channel/status/date_range` 筛选，支持 `submitted_at/status` 排序；详情需返回 `steps[]`, `screenshots[]`, `failure_detail`
- Policy: 返回 `{ gate_policy, exclusion_list }`；无分页；两个子模块需支持独立保存结果与错误反馈
- System Settings: 返回 `{ channels, liepin_api, llm_config }`；无分页；LLM 敏感字段默认掩码，猎聘官方凭据仅返回状态、本机保存路径与保存项存在状态；支持独立测试连接与保存/删除错误反馈

#### 5. 三种必备 UI 状态

每个页面必须设计以下状态（当前设计仅展示了数据填充态）:

- **Loading**: 骨架屏或 spinner + 面板保留结构
- **Empty**: 空状态插图 + 引导操作按钮 (如 "No evidence cards yet. Import your first one.")
- **Error**: 错误提示 + 重试按钮 (特别是 Python sidecar 通信失败场景)

各页面最小状态规范:
- Overview: `Loading` 为统计卡片 skeleton + 图表占位；`Empty` 为“暂无活动/暂无匹配数据”；`Error` 为 sidecar 或聚合查询失败，展示全页错误态和 `Retry / 重试`
- Evidence: `Loading` 为表格骨架 + 详情面板骨架；`Empty` 为无证据卡，主 CTA 指向 `Import / 导入`；`Error` 为列表/详情加载失败或导入失败，需保留最近一次错误原因
- Jobs: `Loading` 为卡片骨架或 leads 表格骨架；`Empty` 为无 Job Profile / Lead，CTA 指向 `New Profile / 新建`；`Error` 为查询或转化失败
- Quick Run: `Loading` 为阶段条初始化态；`Empty` 为未执行前的空准备态；`Error` 为单次运行失败，需在日志面板显示错误摘要与重试入口
- Agent Run: `Loading` 为连接/恢复运行态；`Empty` 为当前无活跃 run；`Error` 为状态机拉取失败、事件流中断或 gate 计算失败；REVIEW 状态下 Loading 为候选数据加载中，展示后等待用户操作
- Resumes: `Loading` 为个人资料卡、已上传简历列表、系统生成简历预览三栏骨架；`Empty` 为尚未完善个人资料且无简历资产，CTA 指向 `Edit Info / 编辑资料` 或 `Upload Resume / 上传简历`；`Error` 为资料读取、简历列表读取或 PDF 导出失败
- Submissions: `Loading` 为统计卡片 + 表格骨架；`Empty` 为暂无投递记录；`Error` 为记录拉取失败、截图读取失败或重试失败
- Policy: `Loading` 为策略表单 skeleton；`Empty` 仅用于 exclusion list 为空；`Error` 为保存失败、导入失败或 policy 校验失败
- System Settings: `Loading` 为系统配置 skeleton；`Empty` 仅用于 channels / provider 尚未配置；`Error` 为保存失败、测试连接失败或凭据存储访问失败；猎聘本地读取失败仍保留删除入口

组件形态约束:
- 列表页优先使用 skeleton rows，不直接用全屏 spinner 覆盖整页
- 详情面板优先保留外层容器，只替换内容区域为 skeleton / empty / error
- `Error` 态必须同时给出用户可读摘要、技术错误码（可复制）和单一主恢复动作

#### 6. Python Sidecar 通信协议

需在代码层设计 Tauri ↔ Python sidecar 通信协议:
- 使用 JSON-RPC over stdio
- 包含版本协商、心跳检测、超时重试
- 错误分类: 连接失败 / 执行超时 / 业务异常
- UI 层通过 Zustand store 统一管理 sidecar 连接状态
- 字段级 contract 以 `ui/design/contracts/sidecar-rpc.md` 为准；本节只保留产品级摘要

协议冻结要求:
- JSON-RPC 版本固定为 `2.0`
- 每个 request 必须包含: `jsonrpc`, `id`, `method`, `params`
- 每个 response 必须返回二选一: `result` 或 `error`
- sidecar 主动推送统一使用 notification 形式，不带 `id`
- `id` 仅用于单次 request/response 配对；跨请求、事件、日志的关联必须使用 `meta.correlation_id`
- `meta.correlation_id` 必须由 UI 在发起用户动作时生成，并在后续 request / response / event / log 中透传

核心方法清单:

| Method | 方向 | 用途 |
|--------|------|------|
| `system.handshake` | UI -> sidecar | 版本协商、能力声明 |
| `system.ping` | UI -> sidecar | 心跳检测 |
| `system.shutdown` | UI -> sidecar | 请求优雅停止 |
| `overview.get` | UI -> sidecar | 拉取 Overview 页面聚合数据 |
| `submission.feedback.syncPacket` | UI -> sidecar | 读取受控成功投递清单与投递记录页发现规则（只读） |
| `submission.feedback.recordPlatformStatus` | Tauri -> sidecar | 记录只读观察到的平台投递进展，按岗位身份匹配并追加历史 |
| `evidence.create` | UI -> sidecar | 创建空白证据卡 |
| `evidence.list` | UI -> sidecar | 拉取证据卡列表 |
| `evidence.get` | UI -> sidecar | 拉取单个证据卡详情 |
| `evidence.update` | UI -> sidecar | 更新证据卡字段 |
| `evidence.delete` | UI -> sidecar | 删除证据卡 |
| `evidence.import` | UI -> sidecar | 导入文件并创建/更新证据卡 |
| `profile.get` | UI -> sidecar | 拉取个人资料 |
| `profile.update` | UI -> sidecar | 保存个人资料 |
| `jobs.listProfiles` | UI -> sidecar | 拉取 Job Profiles |
| `jobs.createProfile` | UI -> sidecar | 创建 Job Profile |
| `jobs.updateProfile` | UI -> sidecar | 更新 Job Profile |
| `jobs.deleteProfile` | UI -> sidecar | 删除 Job Profile |
| `jobs.listLeads` | UI -> sidecar | 拉取 Job Leads |
| `jobs.convertLead` | UI -> sidecar | Lead 转 Job Profile |
| `run.quick.start` | UI -> sidecar | 启动 Quick Run |
| `run.quick.cancel` | UI -> sidecar | 取消 Quick Run |
| `run.agent.start` | UI -> sidecar | 启动 Agent Run |
| `run.agent.stop` | UI -> sidecar | 停止 Agent Run |
| `run.agent.get` | UI -> sidecar | 获取 Agent Run 当前状态 |
| `run.agent.getPendingReview` | UI -> sidecar | 获取 REVIEW 状态下待审批的候选列表（仅 delivery_mode=manual） |
| `run.agent.submitReview` | UI -> sidecar | 提交审批决策（approve/reject/skip 列表；批量模式支持 skip_all） |
| `resume.upload` | UI -> sidecar | 上传用户简历 |
| `resume.list` | UI -> sidecar | 拉取已上传/已生成简历列表 |
| `resume.getPreview` | UI -> sidecar | 拉取简历预览结构化数据 |
| `resume.exportPdf` | UI -> sidecar | 导出 PDF |
| `submission.list` | UI -> sidecar | 拉取投递记录 |
| `submission.retry` | UI -> sidecar | 重试投递 |
| `settings.get` | UI -> sidecar | 拉取聚合配置载荷（供 Policy / System Settings 页面分流消费） |
| `settings.update` | UI -> sidecar | 保存聚合配置载荷或局部切片（首版 bridge 可保持聚合接口） |

说明：
- 字段级 contract 现已覆盖 33 个方法；本表只保留产品级职责摘要
- 证据卡、个人资料、岗位画像的写操作 contract 与字段约束以 `ui/design/contracts/sidecar-rpc.md` 为准
- `overview.get` 为 Overview 页面唯一聚合入口；不得由前端通过多次 list 请求自行拼装趋势、缺口与活动流

Request / Response Schema:
```json
// request
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "method": "evidence.list",
  "params": {
    "meta": {
      "correlation_id": "corr_001"
    },
    "cursor": null,
    "page_size": 20
  }
}

// success response
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "result": {
    "meta": {
      "correlation_id": "corr_001"
    },
    "items": [],
    "next_cursor": null
  }
}

// error response
{
  "jsonrpc": "2.0",
  "id": "req_123",
  "error": {
    "code": "TIMEOUT",
    "message": "sidecar request timeout",
    "details": {
      "correlation_id": "corr_001",
      "retryable": true
    }
  }
}
```

事件流格式:
```json
{
  "jsonrpc": "2.0",
  "method": "event.emit",
  "params": {
    "event_type": "agent.run.updated",
    "correlation_id": "corr_001",
    "run_id": "run_001",
    "timestamp": "2026-03-07T10:00:00Z",
    "payload": {
      "status": "EVALUATE"
    }
  }
}
```

错误码基线:
- `UNSUPPORTED_VERSION`: UI 与 sidecar 协议版本不兼容
- `SIDECAR_UNAVAILABLE`: sidecar 未启动或连接断开
- `TIMEOUT`: 请求超时
- `VALIDATION_ERROR`: 参数校验失败
- `NOT_FOUND`: 目标资源不存在
- `CONFLICT`: 状态冲突，例如重复启动 run
- `INTERNAL_ERROR`: sidecar 未分类异常
- `PERMISSION_DENIED`: 权限不足
- `STORAGE_ERROR`: 文件、截图或凭证存储失败

版本协商细则:
- `system.handshake` 请求必须携带 `ui_version`, `protocol_version`, `capabilities`
- sidecar 返回 `accepted_protocol_version`, `sidecar_version`, `capabilities`, `deprecations`
- 若主版本不兼容，UI 必须阻止进入主界面操作区，只展示升级/重试指引
- 若次版本不兼容但可降级，UI 仅启用双方共同支持的 capability，并在 System Settings/Overview 展示降级提示

#### 7. Sidecar 生命周期与 UI 行为

sidecar 连接状态统一为: `starting` / `ready` / `degraded` / `reconnecting` / `disconnected` / `stopped`

行为约束:
- `starting`: 顶部显示全局启动条，所有写操作按钮禁用，读取型页面可显示 skeleton
- `ready`: 所有功能可用，隐藏全局告警
- `degraded`: 保留只读能力，禁用写操作（导入、运行、保存、重试），显示 `OfflineIndicator` 或顶部 warning banner
- `reconnecting`: 保留当前页面内容快照，禁用提交类交互，显示重连进度与最后成功同步时间
- `disconnected`: 页面保留最近一次成功数据快照；所有依赖 sidecar 的 CTA 禁用，并提供 `Reconnect / 重连`
- `stopped`: 由用户主动关闭 sidecar 或应用退出流程触发，不自动重连

页面级规范:
- Quick Run / Agent Run 在 `degraded`、`reconnecting`、`disconnected` 状态下必须禁用 `Run` / `Stop`
- Evidence `Import`、Submissions `Retry`、Policy `Save`、System Settings `Save` 在非 `ready` 状态必须禁用，并给出 hover 或 inline 原因
- 若事件流中断但最近一次 run 状态仍可查询，Agent Run 页面进入 `degraded` 而不是直接 `Error`
- 自动重连应使用指数退避，建议间隔 `1s / 2s / 5s / 10s / 30s`，达到上限后转为 `disconnected`

#### 8. 文件与截图存储策略

存储基线:
- Evidence `artifacts` 与 Submissions `screenshots` 必须采用 sidecar 管理的应用数据目录，禁止由前端直接写入任意工作目录
- 元数据（文件名、大小、mime type、created_at、source_id、checksum）进入结构化存储；二进制文件单独落盘
- UI 只持有资源 ID 或受控路径，不持有用户原始绝对路径作为长期展示字段
- 删除 Evidence / Submission 相关资源时，必须定义软删除或引用计数策略，避免误删仍被其他记录引用的文件

建议目录:
```text
app-data/
  evidence/
    <evidence_id>/
      artifacts/
  submissions/
    <submission_id>/
      screenshots/
```

读取与预览:
- 预览必须通过 sidecar 提供的受控读取接口，不允许前端自行拼接文件路径读取
- 超大文件或截图列表应支持分页/懒加载，避免一次性载入全部二进制内容
- `STORAGE_ERROR` 或缺失文件必须在详情面板内显式标记，不得静默吞掉

#### 9. 补充交互要求

以下交互要求必须纳入正式实现:
- [x] 语言切换入口 → 已添加到 SideNav 底部
- [ ] 文件上传交互 → 整合到 Evidence 页面 "Import / 导入" 按钮，支持拖拽上传
- [x] 配置编辑承载页面 → 已确定由 Policy / System Settings 两个正式页面覆盖

---

## 设计完成状态

全部 9 页的主态信息架构与 11 个可复用组件已完成终版设计；Loading / Empty / Error 三态以及代码实现映射仍需在落地阶段补齐。以下次级视图或细节交互已补充到本文档，并需在实现阶段重点验收：Resumes 个人资料/上传简历/系统生成简历三分区、Evidence 附件交互、Jobs/Job Leads、Submissions 详情侧板、Policy 策略字段页、System Settings 系统配置页。

### MVP 核心页面 (优先打磨)
1. **Evidence** — 产品核心，证据质量决定后续所有输出
2. **Quick Run** — 最高频使用场景
3. **Overview** — 价值感知仪表盘

### 实施收口任务
1. 依据 `ui/design/contracts/sidecar-rpc.md` 固化 JSON-RPC schema、错误码枚举与 typed bridge
2. 落地 DataTable / FormField / Modal / OfflineIndicator 的代码抽象
3. 将 Design Tokens 导出为 CSS variables 与 Tailwind theme 配置
4. 在 `.pen` 设计稿中补齐 Loading / Empty / Error 三态与断连态
5. 依据 `AIEF/docs/plans/gui-first-batch-kickoff.md` 建立 GUI 首批脚手架与实现边界
6. 将窗口尺寸、分页/排序/筛选和 sidecar 生命周期约束写入实现验收清单

### 文档口径

- `已定版` 表示设计规范已冻结，可作为实现与验收基线
- `正式实现要求` 表示代码层必须满足的约束，不表示当前仓库已完成实现
- 若其他文档与本文件冲突，以本文件为准


### 2026-09-29 App 内默认简历审批入口

复用 Jobs 线索详情和 Agent Run 审批区。官方岗位详情增加“准备平台默认简历审批”；完整 JD 未审核/没有画像时禁用并说明前置步骤。准备时显示忙碌状态，失败保留岗位并展示固定原因；成功打开明确 run_id 的审批页，不跳外部网站。准备只读，批准后才会尝试发送，未知匹配/评测显示未评估。

Agent Run 结果区并列展示“App 自行确认”和“外部观察确认”数量。历史网站观察的实际成功保留防重，标明 App 未自行确认回执；不得显示为 App 闭环已完成。快照仍展示默认平台简历/生成 PDF 类型及正文。设计稿沿原 Jobs/Review 节点增量注明，不新增页面。


2026-09-29 回执增量：Agent Run 未知结果带已保存提交编号时，在结果行增加“核验已有回执”，旁注明“只读取本机保存的响应，不会重新投递”。核验期间禁用按钮；失败给固定证据不可用提示，明确维持原结果；成功刷新当前运行的来源计数与追踪事件。原始 API 响应不进入 UI。

模型长 JD 解析超时的恢复：Jobs 增加显式“手动整理画像”，预填已绑定来源职位名称，复用原审核区，摘要与逐行必备要求可编辑；关键词、来源和完整性校验沿原实现。手工稿不调用模型、不自动审核。

投递记录详情展示 API 对应的简历版本，并可返回本次审批与回执；API 行的重试禁用，保留原结果。


2026-09-29 十岗批次验收：Agent Run 状态区展示授权上限、已占用（含历史实际尝试）、已确认成功和剩余名额。默认简历/PDF 同享额度，外部观察确认也占用原授权，不能用 App 验证计数重置名额。额满时 Jobs 准备入口返回固定原因，真实发送仍由 SQLite 原子占位兜底。历史 API 尝试可在 App 本地按完整响应 SHA256 引用相同已保存内容核验，保留原观察事件，不复制假造旧接收文件。

### 2026-10-11 交互与布局优化（UX 第一批）

依据同日 UX/UI 分析落地，均为非结构性改动，9 页信息架构与导航顺序不变。`.pen` 已同步：Design System 新增 `Feedback Components` 行（`zkCKn`），SideNav 底部新增 sidecar 状态区（`k1BGB`）并改为内容高度，Agent Run 的 `daily18` 移到 `agHeader` 之后，Implementation Constraints 新增约束卡 `Feedback & Layout - UX Batch 1`（`kFfw8`）。

**新增共享组件（代码层：`ui/src/lib/ui.ts`、`ui/src/components/feedback/`）**

| 组件 | Pen ID | 用途 |
|------|--------|------|
| ToastViewport | `fQ00F`（Feedback/Toast） | 右下角通知栈；成功/信息 5 秒自动消失，错误需手动关闭，最多 4 条，相同内容去重 |
| ConfirmDialog | `FQxJ2`（Feedback/ConfirmDialog，含 Button/Danger `YBWSR`） | 全局确认框；Esc 取消，默认焦点在“取消”，Tab 在两个按钮间循环；danger 变体用于破坏性操作 |

**交互规则**

- 列表型页面（Overview、Resumes、Evidence、Jobs、Submissions）首次加载显示占位；之后由保存/刷新触发的重载保留已有内容与编辑状态，只在页头按钮显示“刷新中”，失败时用错误通知并保留上次数据。职业档案编辑器因此不再因基本资料保存或上传而卸载。
- 破坏性或不可逆操作必须经 ConfirmDialog：删除证据卡/附件、清除通道会话、重试投递、删除猎聘凭据、停止运行、批准/拒绝候选、撤销每日授权、立即执行今日批次、结束中断批次、归档岗位画像、用抓取的完整 JD 覆盖已有文本、清空非空草稿、移除职业档案条目、有未保存修改时重新加载（策略配置、系统设置、职业档案）。
- 成功反馈统一走通知（`toasts.*` 文案），不再只靠状态 chip 或常驻内联文字。
- 按钮层级固定为 primary / secondary / ghost / danger 四级（`buttonClass`），同一行只保留一个可用的 primary；每日受控投递的按钮按“草稿操作 | 授权控制”分组。
- 禁用的主按钮必须以 title 或内联文字说明原因：快速运行启动（列出全部阻塞原因）、岗位画像新建、系统设置保存、每日投递各按钮、职业档案确认复选框。
- 页头原“重试”统一改为“刷新”；筛选栏支持回车提交；证据表格行可键盘聚焦并用 Enter/空格选中。
- Quick Run：后端同步执行、没有逐阶段进度，执行期间四个阶段统一显示进行中并说明不可中途取消；原取消按钮移除。评分条显示维度全称并带 progressbar 语义。
- Overview：统计卡可点击进入对应页面；“查看证据缺口”带 `status=gap` 进入证据页；缺口为 0 时徽标为成功色。

**布局规则**

- sidecar 处于 `ready` 时不再在主内容区顶部显示状态面板；常驻状态移到 SideNav 底部（状态点 + 状态名 + 版本，悬停显示最近心跳），非 `ready` 状态才在主内容区顶部显示横幅。SideNav 语言切换按钮显示目标语言名称。
- 新增 Tailwind 断点 `wide: 1366px`：1280–1365 区间右侧详情栏降为 360px，1366 起恢复 420px；Evidence、Jobs、Agent Run 的右栏自 `xl` 起 sticky 并限高内部滚动。
- Evidence 表格列宽调整为 40/16/20/8/16，时间列不换行，角色列截断并以 title 显示全文，表头 sticky，最小宽度 640px 时在容器内横向滚动。
- Agent Run：页头在前，“每日受控投递”卡片位于页头之后、运行区域之前（仍满足“在既有运行区域前”的约定）。
- Quick Run 终端区背景改用 `--bg-primary` token，不再硬编码色值。

### 2026-10-11 投递记录页交互与布局优化（UX 第二批）

- 区块顺序改为“主任务优先”：统计行 → PDF 投递 → 尝试记录 + 运行详情 → 反馈迭代 → 通道会话（旧 Playwright 通道）→ Check Mode 演练（默认收起的 `details`）。PDF 投递仍位于统计行后，满足原约定。
- PDF 投递卡顶部新增 8 步步骤条（固定 PDF → 预览并批准 → 上传附件 → 核验附件 → 核验岗位并沟通 → 检查沟通并准备简历 → 确认发送 → 核验回执），按 `phase` 推导当前步骤；各按钮的启用条件不变，只有当前步骤的按钮显示为 primary，其余为 secondary，移除附件为 danger。
- 清除通道会话、原通道重试、邮件降级重试接入 ConfirmDialog；会话清除、重试排队、反馈记录成功走通知；刷新沿用“首次加载占位、之后保留内容”的规则。
- 会话路径、反馈记录路径、详情中的简历/资料/日志路径折叠进“技术详情（路径与指纹）”；运行详情面板自 `xl` 起 sticky，右栏 360px，1366 起 440px。
- 原生核对补充规则：主内容区是唯一滚动容器，切换路由时复位到顶部；表单 `select` 背景必须用实色 token，半透明背景在 Tauri WebKit 下会退回原生白色外观。
- `.pen`：Screen/Submissions 的 PDF 投递卡（`nLpn01`）新增步骤条行 `pdfSteps`（`BRizs`，8 个芯片，首个为当前态），`subColumns`（`NzPYZ`）移到反馈卡之前以对应新的区块顺序。

### 2026-10-11 一级页面布局与引导优化（UX 第三批）

起因：用户从 App 定位（求职者自用、运行在个人电脑上的桌面工具）出发，要求分析一屏显示中固定与滚动的划分、操作引导与首次使用友好度，并先处理一级页面的问题；约束是做减法，不堆元素、不造成信息冲击。分析结论见同日对话：页面按系统模块切分而非按任务，一屏看不到主对象，页头随页滚走，滚动里套滚动，常驻表单挤走浏览态，术语与命名不一致，没有首次使用引导。

**三层规则（所有页面）**

- 固定层：SideNav + 吸顶页头 `.page-header`（标题、一行副标题、最多两个操作按钮，外加一个图标刷新按钮，刷新文字只给读屏器）；实色背景、底部 1px 边框、高度约 89px；负外边距抵消主内容区 `p-6`。
- 工作层：主列表/网格 + 详情右栏，右栏 `sticky top-[6.5rem]`、最大高度 `100vh-8rem`；证据表格限高 `100vh-20rem` 并固定表头。
- 工具层：导入、解析、编辑器、演练等默认收起（`.fold-section`，`<details>` 保持挂载），展开与否由数据状态决定。

**各页改动**

- 总览：前置条件缺失时在统计卡前显示“开始前的几件事”（模型 → 职业档案与材料 → 证据 → 目标岗位），每个未完成步骤一个按钮；页头主按钮指向第一个未完成步骤，全部就绪才回到“启动智能运行”。就绪读取 `settings.get`、`material.readiness`、`jobs.listProfiles`，任一失败则隐藏清单，不阻塞主数据。统计卡提示改为用户语言。
- 证据卡：统计卡改为一行统计条 `.stat-strip`；筛选表单并入列表卡头部；材料来源折叠为一行摘要，仅当没有证据卡时默认展开。
- 岗位中心：统计卡改统计条；新建画像输入行与 JD 解析区合并为一个折叠区块 `#jobs-create`，页头“新建画像”只负责展开并聚焦标题输入，区块内新增“创建画像”主按钮；没有画像、或存在解析草稿/绑定线索时自动展开。
- 简历中心：职业档案编辑器包在折叠区块里，摘要行显示确认状态与工作/教育/能力条数，未确认时默认展开；编辑器去掉外层卡片边框；工作材料列表限高 420px 内滚。
- 快速运行：岗位与定位两个下拉从页头移入“运行输入”，岗位选项显示“公司 · 岗位”，去掉重复的“所选岗位画像”卡；模型配置摘要压成一行；页头只剩刷新图标与“启动运行”。
- 智能运行：页头分段标签 `.seg-tabs`“每日受控投递 | 自主运行（本地演练）”，默认每日投递，带 `run_id` 深链进入自主运行；画像下拉、本地演练、停止移入自主运行标签的工具条；模型摘要一行化；非活动标签保持挂载（`hidden`）。
- 投递记录：页头分段标签“投递一份 PDF | 记录与反馈”，默认记录，带 `quick_run_id` 深链进入投递；统计卡改统计条放在记录标签顶部；表格去掉“最后步骤 / 限流”原始副行（详情面板已有失败原因与限流）；PDF 指纹只显示前 12 位，完整值在 `title`。
- 策略配置 / 系统设置：页头吸顶，刷新改图标，保存按钮提示 ⌘S。

**壳层与术语**

- 快捷键（AppShell）：⌘/Ctrl+1…9 切页（输入框内不触发），⌘R 派发 `pipf:refresh`，⌘S 派发 `pipf:save`；页面用 window 事件接入，不注册回调；导航项 tooltip 带 ⌘N。
- `html lang` 跟随当前语言（默认 zh）；侧栏底部显示“本地服务 · 状态”，版本号进 tooltip。
- 术语收平：导航 = 页面标题（证据卡、岗位中心、投递记录，按本文件术语表）；九页副标题改写为“你可以在这里做什么”；每日投递候选的 SHA256 改为 12 位指纹加 tooltip。

**Pen 节点**：Design System 新增 `Layout Components`（`urdhh`：Layout/PageHeader `pMNx0`、Layout/StatStrip `I8lodt`、Layout/SegTabs `XOcaK`）与 `Guidance Components`（`a38v5l`：Layout/FoldSection `ljZwE`、Overview/SetupChecklist `WS4VQ`），Design System 顶边上移到 y=-1060；Implementation Constraints 新增约束卡 `Layout & Guidance - UX Batch 3`（`qxXC8`）；Screen/Submissions 页头改为标题 + 操作区并加 SegTabs 实例，`subStats` 改为 StatStrip 实例；Screen/Agent Run 页头加 SegTabs 实例并把停止按钮归入操作区。

**验证**：tsc、vite build 通过；tests/unit/gui 72 项通过（新增 `tests/unit/gui/test_overview_setup_checklist_ui.py` 3 项，先红后绿）；内置浏览器 1440×900 读回九页首屏与滚动后页头吸顶、折叠默认态、深链进入对应标签、⌘R 事件与 ⌘3 切页、1280×800 无横向滚动。未做：Tauri 原生窗口读回；窗口尺寸记忆、跟随系统外观、全局长任务指示留待后续批次；二级及更深层页面的分析与优化未开始。

### 2026-10-11 二级及更深层页面优化（UX 第四批）

起因：一级页面收口后，用户要求分析二级、三级及更深层页面并直接处理。分析结论见同日对话：详情右栏与编辑器把对象的全部字段永远展开（证据详情 1714px、画像详情 1134px、职业档案编辑器 2991px，右栏可视高度 770px）；标识符、哈希、英文步骤名、JSON 回执直接当正文；每个可写区块前都放一段四五十字的边界说明；开发期工具与用户功能混放；Tailwind 透明度修饰符对 `var()` 颜色静默失效导致强调描边、淡色底与分组导航高亮全站缺失。

**规则**

- 详情栏默认只读：标题用人类可读名称，状态用标签，正文分组显示，技术栈与标签用 chips；页头“编辑”进入表单（保存 / 取消编辑）。新建草稿、模型草稿、按原来源重审自动进入编辑态；切换卡片或保存成功后退出。ID、来源材料、路径、哈希只出现在栏底的“技术详情”折叠里。
- 代码词不直达用户：投递步骤名、浏览器通道、来源、模式、平台码经 `codes.*` 字典映射为中文，原始码作为 tooltip 或回退值。JSON 回执折叠为“已收到平台回执，原文见技术详情”；成功记录的失败区不再显示 JSON。
- 边界说明只保留一句，其余进“了解这一步”折叠；授权勾选保留短句，完整条款放“查看完整授权条款”折叠，复选框的 `aria-label` 仍是完整条款（每日投递、PDF 投递）。
- 每日受控投递卡顺序：今日状态 → 一句说明 → 授权设置（启用后折叠，摘要显示上限与时间）→ 候选清单 → 授权勾选 → 按状态只突出一个主按钮（已启用执行今日批次、有改动保存草稿、否则确认并启用）；暂停 / 撤销 / 结束中断收进“更多操作”；历史批次折叠并显示数量。
- 职业档案编辑器：每条经历是一行摘要（公司 · 职务 · 时间 / 学校 · 专业 · 学历 / 能力分类 / 成果名称）的折叠条目，只有空条目默认展开；缺项提示、确认勾选与保存 / 确认按钮吸底，编辑长表单时始终可见。
- 证据材料来源只保留一条路径（选材料 → 选片段 → 提炼），按钮不可用时给一行步骤提示；去掉重复的三张材料卡；文档预览去掉 YAML 文件头。岗位“新建岗位画像”以 JD 解析为主路径，仅标题创建降为子折叠；线索标签的猎聘搜索折叠；线索详情按状态只亮一个主按钮（未取完整 JD 时是“获取完整 JD”，否则“转为岗位画像”），来源码显示中文，不再显示线索 ID。
- 开发期工具（旧通道会话、Check Mode 演练）合并为投递记录末尾一个折叠的“高级与演练工具”。自主运行没有运行记录时只显示一块空态面板；快速运行未运行时不显示评分条。颜色 token 改为 `rgb(var(--x-rgb) / <alpha-value>)`，透明度修饰符全站生效，策略 / 系统设置的分组导航高亮恢复正常。

**各页改动**：证据卡 `index.tsx`（只读视图、编辑切换、材料来源单路径、导入附件与技术详情折叠）、`material-document-picker.tsx`（预览去文件头）；岗位中心（JD 解析优先、画像详情只读 / 编辑、猎聘搜索折叠、线索主按钮与来源标签）；投递记录（步骤字典、回执折叠、ID 下沉、反馈下拉不带 ID、说明压短、高级工具折叠）；智能运行 `daily-delivery.tsx`（重排、折叠、单一主按钮、更多操作）与 `index.tsx`（空态）；简历中心 `career-profile.tsx`（条目折叠、吸底操作栏）；快速运行（评分条按结果显示）；`tokens.css` + `tailwind.config.ts`（透明度）。

**Pen 节点**：Implementation Constraints 新增约束卡 `Depth & Vocabulary - UX Batch 4`（`wzkfN`）。本批不改画面结构，不新增组件。

**验证**：tsc、vite build 通过；tests/unit/gui 73 项通过（新增 `tests/unit/gui/test_evidence_detail_view_mode_ui.py`，先红后绿；`test_evidence_rereview_ui.py` 的断言改为“切换卡片后保存按钮可以不存在，存在时必须禁用”）；内置浏览器 1440×900 读回：证据详情只读 / 编辑 / 取消切换与栏高 1714→1261px、画像详情 1134→655px、职业档案编辑器 2991→848px 且吸底栏可见、投递详情步骤名中文与回执折叠、高级工具折叠、每日投递卡新顺序与“更多操作”、快速运行无评分条、策略页分组导航按钮的 class 随切换变化。未做：Tauri 原生窗口读回；PDF 投递卡固定后的流程区与审批面板在只读模式下不可触发，按源码检查。

### 2026-10-11 全局长任务指示（UX 第五批）

起因：快速运行在后端同步执行，执行期间切到别的页面会让页面卸载、结果被丢弃，用户也看不到任何进度。本批不加依赖，只用现有 zustand。

- 新增 `ui/src/state/task-store.ts`：按任务类型记录 `running / done / error`、开始与结束时间、所属岗位画像与结果；目前只有 `quickRun`。
- 快速运行页：启动时登记任务；结束时无论页面是否已切走、目标是否已改变，都把结果写入 store 并弹出成功 / 失败通知，只有本页状态仍按版本守卫更新。回到页面时：任务仍在进行则恢复“运行中”与计时并禁止重复启动；任务已结束且属于当前岗位画像则读回结果；失败则显示失败原因。
- SideNav 底部：有任务进行中时显示一行“快速运行 · 目标 进行中”带旋转图标，点击回到快速运行页；任务结束后该行消失，完成情况由全局通知承担。
- 词条：`shell.taskRunning`、`shell.taskOpen`。
- 测试：新增 `tests/unit/gui/test_task_store.py`；`test_quick_run_inputs_ui.py` 补 `@/state/task-store` mock；tests/unit/gui 74 项通过，tsc、vite build 通过。
- 读回：内置浏览器以只读桥接（对 `run.quick.start` 延迟 8 秒后拒绝）走通“启动 → 切到总览看到指示 → 点指示回到页面为运行中 → 任务结束后指示消失并弹出失败通知 → 页面回到可运行态”。
- Pen 节点：Implementation Constraints 新增约束卡 `Background Tasks - UX Batch 5`（`YTTf3`）。

### 2026-10-11 窗口尺寸与位置记忆（UX 第六批）

- 桌面端常规体验补齐：`ui/src-tauri/Cargo.toml` 加入 `tauri-plugin-window-state = "=2.4.1"`（固定版本：2.5.0 要求 tauri ≥2.12，会连带升级锁文件里几十个 crate；2.4.1 要求 ≥2.8.2，与锁定的 tauri 2.10.3 兼容），`main.rs` 在构建器链最前注册插件。无前端改动。
- 行为：启动时按应用数据目录的 `.window-state.json` 恢复主窗口尺寸、位置与最大化状态；退出时保存。最小尺寸 1280×800 仍由 `tauri.conf.json` 约束。
- 验证：`tauri build --bundles app` 通过（tauri 仍为 2.10.3，锁文件新增 32 个插件依赖包、6 个移除、12 个过渡升级）；启动打包版 14 秒后经 AppleScript 请求退出，状态文件写出主窗口 2880×1800 物理像素（即 1440×900 逻辑）、坐标 288/112。恢复路径是插件标准行为，未在本会话做可视化核对（无桌面控制权限）。

### 2026-10-11 原生窗口读回与 WebKit 修复（第三至六批收口）

- 用户授予桌面控制后，启动打包版（含第三至六批与窗口状态插件）用后台窗口控制逐页截图：总览（开始前清单与动态主按钮）、简历中心（职业档案折叠、条目摘要、吸底操作栏）、证据卡（统计条、材料来源折叠、只读详情与编辑态切换）、岗位中心（新建画像折叠与 JD 解析优先、只读画像详情、线索标签与猎聘搜索折叠）、快速运行（选择器下沉、模型一行、无评分条）、智能运行（标签切换、每日卡新顺序、自主运行空态）、投递记录（两个标签、统计条、高级工具折叠）、策略配置（分组高亮）、系统设置，全部与设计一致。打包版用内置示例数据。
- 发现并修复两处 WebKit 差异：每日投递卡“更多操作”弹层为绝对定位的无宽度容器，WebKit 把按钮压成逐字换行，改为 `w-max whitespace-nowrap`；职业档案吸底栏里的待补内容清单占去过多视口，改为一行计数的折叠。重新打包后原生复核通过。
- 读回方式：`open -n` 启动打包版，桌面控制在后台窗口内点击与截图，结束后用 AppleScript 请求退出。打包版退出时也写出了窗口状态文件。

### 2026-10-11 空工作区首次启动走查（UX 第七批）

方法：把打包版复制到隔离目录，清空其资源目录下的 `evidence_cards`、`job_profiles`、`matching_reports`、`outputs`、`materials`、`uploaded_resumes` 与 `personal_profile.yaml`，直接运行副本的可执行文件，用桌面控制逐页截图，模拟一个全新用户第一次打开。

发现与处理：

- 总览“选择一个模型”在未配置时显示已完成：后端 `settings.get` 在没有配置时也返回默认 `provider=openai`、`model=gpt-4`，前端按“有 provider 和 model”判定。改为按 `llm_config.api_key.configured`（密钥或本地占位保存过）判定；该步直达 `/system-settings?section=llm`，设置页按 `section` 参数打开分组，不再落在“通道”。
- 证据卡“材料来源”在没有任何材料时仍显示材料下拉、提炼按钮和文档拾取器：改为只显示一句提示加“去简历中心上传材料”按钮，经壳层 `pipf:navigate` 事件跳转（页面不新增 import，兼容 vm 测试）。
- 旧导航名残留：岗位页空态“在工作区中添加新的岗位画像文件”改为“在上方粘贴岗位描述并解析，或展开‘仅用标题创建’”；每日投递空态里的“职位管理”改为“岗位中心”；职业档案关联说明里的“证据管理”改为“证据卡页”。
- 其余页面空态可接受：简历中心编辑器默认展开且吸底栏提示 8 项待补；快速运行一行列出四条阻塞原因；投递记录、智能运行空态简洁；系统设置默认停在“通道”已由上面的参数修复。

验证：tests/unit/gui 74 项、tsc 通过；重新打包后用空副本原生复核：总览四步待完成、主按钮直达模型分组，证据卡空材料态只剩提示与去上传按钮并可跳转。

### 2026-10-12 岗位线索公司规模（投递实验前置）

背景：用户把投递实验改为“JD 高匹配 + 微小公司”，需要在 Jobs 的线索列表里直接看到并筛出小公司。官方搜索已返回公司规模、融资阶段等事实，之前被丢弃。

改动（只在既有结构里加一行一控件，不新增卡片）：

- 线索行：公司名下方加一行 `text-xs text-text-muted`，内容为“规模 · 融资阶段”（如 `1-49人 · 天使轮融资`），任一缺失则只显示另一项，两者都缺则不占高度。
- 筛选区：状态下拉后新增“公司规模”下拉（`data-testid="lead-size-filter"`），档位“全部规模 / 100 人以下 / 500 人以下”，对应后端 `company_size_max` 99 / 499；“全部”保持 null。关键词输入同时匹配工作地区，不另加地区输入框。
- 线索详情：薪资 · 地区行末尾追加“公司规模: 规模 / 融资阶段 / 行业”；画像侧栏公司行追加规模。
- 文案键：`pages.jobs.leads.companySize / allSizes / sizeUnder100 / sizeUnder500`。

验证：tests/unit/gui/test_jobs_liepin_detail_ui.py 新增行文案与下拉档位断言。`.pen` 已同步：Screen/Jobs 的 `leadFilters` 新增 `leadSizeFilter` 公司规模下拉，`leadRow1`/`leadRow2` 各加 `leadRow1Size`/`leadRow2Size` 规模·融资阶段行。

### 2026-10-12 证据页“材料对账”折叠区

背景：用户要求 App 能对本机材料做核对、分析、整合。第一片做成只读对账：哪些卡的结果在材料里找不到原文、缺什么字段、疑似重复、材料里有哪些年月线索。

结构（放在“材料来源”折叠区之后、证据列表之前，默认收起）：

- 摘要行：未对账时一句提示；对账后换成六个计数“可用 · 待补 · 未入池 · 结果不可追溯 · 缺时间 · 疑似重复”。
- 内容区：一行说明“只读检查，不改动任何卡”+ 右侧 `page-icon-button` 重新对账；下面是问题清单（`ul.divide-y`），每行左侧标题 + 池状态小字，第二行原因串（如“2 条结果在材料里找不到原文 · 缺时间（材料中出现：2024-06、2024-09） · 疑似与 ec_x 重复”），右侧“查看”进入该卡详情。最多显示 30 行，超出给一句提示。
- 不新增页面、不新增统计条项；展开时才请求，避免首屏多一次扫描。

验证：tests/unit/gui/test_evidence_reconcile_ui.py。`.pen` 已同步：Screen/Evidence 新增 `materialReconcileFold` 折叠区实例（摘要行、六项计数、问题行占位与展开箭头）。

2026-10-17 补全分流：对账列表每行右侧增加小号下拉“未分流 / 值得补 / 不参与展示 /（有疑似重复时）与 ec_x 重复”，位于“查看”按钮左侧；摘要行追加“值得补 · 已分流 · 未分流”计数。已分流卡默认收起，清单下方文字按钮“显示已分流的 N 张 / 收起”。卡变化后行内以警示色提示“之前的分流判断失效”。不新增页面或统计条。验证：tests/unit/gui/test_evidence_triage_ui.py。`.pen` 已同步：对账行 `triageSelect1`/`triageSelect2` 分流下拉、`reconcileCounts` 值得补/已分流/未分流计数、`reconcileRow2Warning` 卡变化警示与 `reconcileShowHidden` 文字按钮。

### 2026-10-12 职业档案“自动关联证据”按钮

背景：证据池从 8 张扩到 51 张后，逐段工作手动勾选不现实；用户批准按材料来源自动关联。

- 位置：职业档案编辑器吸底操作行最左侧，与“保存”“确认”同一排，`buttonClass.secondary`，`data-testid="career-autolink"`；有未保存修改、档案已过期或无修订号时禁用，title 说明原因或规则。
- 行为：一次调用完成建议与写入，成功后刷新档案并弹出“已自动关联 N 张，M 张无法判定”；无法判定的卡仍通过各段工作下的“关联证据”多选处理。写入后确认复选框自然失效，用户需重新确认。
- 不新增面板、不新增列表；规则说明放在按钮 title。

验证：tests/unit/gui/test_career_autolink_ui.py。`.pen` 已同步：Screen/Resumes 新增 `careerEditorOps` 吸底操作行（`careerAutolink` 自动关联证据、保存草稿、确认档案与禁用提示）。


2026-10-12 Quick Run 停止状态校正：方向不符的 SKIPPED 结果显示后续阶段“已跳过”和“本次未生成简历”，操作入口返回岗位中心，不显示 PDF 准备入口。

2026-10-12 职业档案连续录入修正：新增条目填写名称后保持展开，直至保存或放弃；沿用既有条目折叠布局和字段，不增加新入口。已确认补充成果纳入语义评估，个人项目归属独立。

2026-10-12 简历导出显示修正：原材料片段带未成对的 Markdown 加粗符号时按普通文本显示，代码片段中的运算符保留；不修改事实、来源字段或已固定 PDF 快照。

2026-10-12 附件核验结果：沿既有PDF阶段状态区显示未核验提示，上传记录保留、重新检查不重传；没有新增页面或变更审批顺序。

2026-10-12 单次投递：附件已核验时在既有PDF状态区显示“登记本岗位一次投递授权（限此PDF）”；登记后显示最多一次的范围说明，后续沿原岗位核验、沟通、发送和回执步骤。旧批次不重置，每日上限不变。

### 引用式材料（2026-10-17）

- 证据页材料库折叠区新增「引用外部目录」：选来源根 → 相对路径 → 扫描预览（文件数/跳过项）→ 命名创建；材料下拉与已引用列表对引用材料标注「引用 N 档」，并提供状态检查 / 刷新 / 解除（刷新与解除需确认）。
- 系统设置新增「材料来源」分类：管理允许被引用的外部来源根（路径必须为已存在目录）；移除来源后，依赖该根的引用材料校验失败并阻断。
- 语义：不复制原件；内容变更可检出并阻断（「来源已变更，需重审」），刷新后以最新内容为新基线；快照材料行为不变。
- `.pen` 已同步（2026-10-17 补记）：Screen/Evidence 材料来源区（`docPick1`）新增 `refMaterialEntry`（引用外部目录入口与不复制原件提示）与 `refMaterialItem`（引用材料条目、检查/刷新/解除）；Screen/System Settings 新增 `setNav3`「材料来源」导航与 `setMaterialSourcesCard` 引用根字段卡。左列屏幕增高后按 40 间距重排，无重叠。

### 四层质量报告（2026-10-18，Phase A）

- Quick Run 结果区与投递记录固定 PDF 审批区新增「四层质量报告」折叠组件：合格 / 对位 / 优质 / 突出四层，显示通过状态、规则缺口（`rule · target · reason`）与 LLM 待判项；failure 指向证据卡 id 时提供「在证据页查看」跳转。
- 旧版规则总分与表达参考分移入「对比旧版分数（不参与通过判定）」折叠区；78 参考线不再展示或决定通过，`evaluation_reference_score` 字段废弃。
- 简历 Markdown 模板在首屏末尾写入 `<!-- first-screen-end -->`，渲染层忽略该注释行；评估器以该标记切分首屏，旧正文缺少标记时按前 30% 行回退并记录 `first_screen.mode=fallback`。
- Phase A 只实现规则判项，未接入的 LLM 判项在报告中列为「LLM 判项待接入（Phase B）」，不显示为已通过。
- `.pen` 待补（Quick Run 结果区与审批区的四层折叠实例）。

### 突出点与质量判项（2026-10-18，Phase B）

- 四层报告突出层展示 LLM 提名的突出点与候选：bullet ↔ JD 条目、超出维度（规模 / 难度 / 范围 / 稀缺组合）、证据等级、理由与引用；用户可「否决」或「设为突出点」，决策写入 `app-data/quality_decisions.json`，重新评测后生效，不写卡、不改生成事实。
- Quick Run 结果区与固定 PDF 审批区在四层报告内展示决策入口与状态提示；LLM 判项未覆盖或无效时保留 pending / 待接入提示，不显示为已通过。
- `.pen` 待补（突出点/候选与决策按钮实例）。

### 投递建议与对位缺口类型（2026-10-21，用户方向）

- 产品目标是帮助候选人拿到面试/录用，不以 `auto_pass` 全绿为目标。四层报告顶部新增「投递建议」区：建议结论（建议投递 / 建议补强后投递 / 建议先补证据或更换更匹配目标 / 先核对事实与硬性条件）、「仅供参考，不拦截投递」说明、依据列表、下一步动作，以及前三条职责口径的证据缺口/未表达计数（计数胶囊注明「前三条职责」，与 R2.3 聚合计数区分）。
- 对位层每条 R2.2/R2.3 缺口显示类型徽标：`证据缺口`（证据池非 supported，含 partial/insufficient/conflict/未知，需补证据或换目标）与 `未表达`（证据池已支撑，但正文未呈现或未进首屏）。R2.3 同时存在两类缺口时展示两条聚合 failure；R2.4 内容取舍缺口不显示该徽标。旧报告无 `delivery_advice` 时不渲染建议区。
- 建议不改变 `auto_pass`、不改变审批门禁、不替代用户最终发送决定；PDF 页数/裁切未回填时提示「投递前会再次校验」，不按简历缺口处理，但首屏摘要/核心经历等已可判缺口仍保留在合格层与建议依据中。
- `.pen` 待补（Quick Run 结果区与审批区四层报告顶部建议区、缺口类型徽标实例）。

### 证据可信等级与待确认推断（2026-10-18，Phase C）

- 证据卡字段可携带字段级可信等级 L1–L5：合格/来源检查之外，卡片详情与列表显示时间、角色的等级徽标；缺省旧卡视为 L1（有值）或 L5（空值），不改动既有审核与生成门禁。
- 对账面板新增「待确认推断」行：显示推断字段、值、等级与置信度、原文/元数据依据，提供「接受」「修改后接受」（转 L4）「否决」；高置信候选默认展示，低置信折叠；支持批量接受高置信候选。接受/否决不写卡的时机由用户确认，接受后卡片进入待审核。
- 2026-10-20 行为修复：逐条/批量接受同一卡的多个字段时接续新指纹，保留各字段等级；每次成功即更新剩余候选和计数，失败后只重试未完成项，完成时不触发模型重跑、不抢回用户已切换的卡。页面结构与现有画布保持一致。
- 系统设置新增「证据推断」分类：LLM 跨文档推断开关；关闭时只显示规则 L2 时间线索，不调用模型。
- 单文档提炼提示词注入文档元数据（路径日期/标题日期/修改时间/任职区间），时间候选限 L1/L2 并带依据；角色仅接受原文明示 L1。
- `.pen` 已同步：Screen/Evidence 材料对账折叠区新增 `reconcileInferenceRow`（待确认推断行，含接受/修改后接受/否决），证据页高度 1310 并重排左列。系统设置「证据推断」分类 `.pen` 待补。

### 生成按等级降级与首屏组织（2026-10-18，Phase D1–D4）

- A/B 简历模板保留字段来源等级。2026-10-20 用户修订后，L3 的已采纳职责、动作与责任限定保持原义，不再机械替换主导/负责人或添加「参与 / 推动」前缀；来源等级与责任强度分别判断。L5 时间卡不进入正文，推断精度为年时只显示起始年。
- LLM 受控改写不得提高角色强度或时间精度；违规时回退模板原文（规则复核而非仅提示词约束）。
- 首屏标记 `<!-- first-screen-end -->` 移到第一条经历之后；证据卡按 JD 语义引用排序（引用优先，未引用压缩为最多 4 / 最少 2 条），使 JD 前三条职责对应 bullet 进入首屏。
- `resume_trace` 的时间/角色 claims 携带等级与依据，trace 顶层记录 `field_provenance`；候选人正文与 PDF 仍不含内部追溯信息。
- 边界：B4 突出点由评估阶段提名（生成先于评估），正文回填突出点需评估后二次生成，留作后续切片；`.pen` 无结构性页面变更。

### 证据页三层关系与材料对账就地查看（2026-10-18，UX 修复）

- 页面信息架构：材料来源（登记可引用的材料目录/文档，是卡片结果的溯源对象）→ 材料对账（对全部卡做只读体检：逐字追溯、缺失字段、疑似重复、池状态、分流与推断候选，不改卡）→ 证据卡列表 + 详情（编辑字段、来源、审核与附件；对账问题的修正落在这里）。
- 证据页标题下常驻三层关系提示条，说明每层的职责与数据流向，避免把“对账/来源/卡片列表”混为一谈。
- 材料对账行「查看」不再把数据加载到远处的详情面板，而是**在点击行下方就地展开只读摘要**：池/审核/入池状态、时间与角色（带 L1–L5 等级）、场景、技术栈、标签、来源文档数、附件数、行动/成果、缺失项，以及“对账发现”（不可追溯结果、原文候选及相似度、材料时间线索、建议来源、疑似重复）。数据出现在用户点击的位置，按钮同时变为“收起”。
- 摘要底部「打开完整详情（编辑/来源校验）」才把右侧证据详情面板加载并滚动到视口；详情面板保持原职责，不复制编辑/重审流程。
- ~~`.pen` 待补：关系提示条与对账摘要行尚未同步~~（该两处结构已被下方「证据页结构重整」取代，不再补充画布）。
- 2026-10-18 复盘：本轮“提示条 + 就地摘要”属于补丁——需要两段说明文字才能解释区块关系，且“查看”失效的根因是材料区与对账区把列表/详情双栏推出首屏。两项均由下一节结构重整取代，不再补 `.pen`。

### 证据页结构重整（2026-10-18，设计基线）

**背景**：10-17 至 10-18 两天内引用式材料、补全分流、待确认推断、就地摘要四片功能依次叠加，每片都选择“在既有区域内加一个折叠”落地。结果证据页有 12 处点击才可见的内容、两处两级嵌套（材料来源 → 引用外部目录；材料对账 → 行摘要 → 低置信候选），三个并列折叠块没有主次，对账列表与证据列表是两份互不联动的卡清单，同一张卡出现两次、两种展示、两个“查看”。本次按上文「折叠使用规则」重整，不新增能力，只重排已有能力。

**页面结构（自上而下，一屏）**：

1. 页头：标题 + 副标题；动作区从左到右：刷新（图标）、「从材料提炼」（次要按钮，打开提炼抽屉）、「新增」（主按钮）。去掉页头“导入附件”（与详情面板内的导入表单重复，保留后者）。
2. 对账汇总条（常驻，替代原“材料对账”折叠块与原统计条）：一行计数“全部 N · 可用 · 待补 · 未入池 · 结果不可追溯 · 缺时间 · 疑似重复 · 待确认推断 · 值得补 · 已分流”，每个计数是按钮，点击即把下方列表切到对应筛选并高亮当前项；右端「重新对账」显式按钮（带运行中态）与「运行推断」按钮、批量接受高置信入口、推断开关关闭时的一句提示。页面进入时自动跑一次对账（原逻辑是展开时才跑，改为进入页面即跑，结果缓存到刷新），不再依赖“展开”手势。
3. 列表 + 详情双栏（紧接汇总条，保证在 1440×900 下首屏可见）：
   - 左栏证据列表：筛选行保留搜索 / 角色 / 标签输入，状态下拉扩成“问题筛选”单一下拉（全部 / 可用 / 草稿 / 缺口 / 结果不可追溯 / 缺时间 / 疑似重复 / 待确认推断 / 值得补 / 已分流 / 未分流），与汇总条计数同源。表格列：标题（第二行不再显示 `evidence_id`）/ 时间（值 + L1–L5 等级徽标）/ 角色（值 + 等级徽标）/ 来源（来源文档数，无来源显示“—”）/ 状态与问题标签（状态 chip 之后跟最多 3 个小标签：不可追溯、缺时间、重复、待确认、值得补、不展示；多出的以 “+n” 表示）。去掉“分数”列（口径无处解释，对用户决策无帮助；数值仍保留在详情技术信息）。
   - 右栏详情面板职责不变，调整：
     - 顶部操作统一为文字 + 图标按钮：编辑 / 保存 / 取消；删除移到面板底部，单独一行、危险色描边，不与保存并排。
     - 只读视图每个字段旁直接显示等级徽标与来源文档名（时间、角色必显；其他字段有 `field_sources` 时显示），长原文才用折叠；原“已绑定字段依据”折叠取消。
     - 新增「对账发现」区（只对有问题的卡出现，位于字段之后、附件之前）：问题原因、不可追溯结果与原文候选及相似度、材料时间线索、疑似重复链接、分流下拉、待确认推断候选（接受 / 修改后接受 / 否决 三个按钮组，低置信默认折叠——这是允许的分级折叠）。原对账行里的分流下拉、推断候选与就地摘要全部迁到这里，列表行不再承载操作。
     - 保留折叠：从其他文档补充依据、导入附件、技术详情（含 `evidence_id`、来源材料 id、分数）。
4. 提炼抽屉（右侧覆盖式 drawer，宽 560px，Esc / 遮罩关闭）：原“材料来源”区的单路径流程原样迁入：选材料 → 选片段（文档拾取器与原文预览折叠）→ 「提炼」/「手动整理证据」。提炼成功后关闭抽屉，详情面板进入草稿审核态（既有行为）。没有材料时抽屉内显示提示与「去简历中心上传材料」。「引用外部目录」从证据页移除，由系统设置「材料来源」分类承载（设计已存在），抽屉底部给一个跳转链接。

**删除项**：三层关系提示条 `evidence-relation-hint`、对账区说明文字 `reconcile.scope`、对账行就地摘要 `evidence-reconcile-preview` 与 `focusDetailPanel` 滚动补丁、`evidence-reconcile-list` 独立列表、“显示已分流的 N 张”切换、页头导入附件按钮、列表“分数”列。文案 `relationHint` / `reconcile.hint` / `reconcile.scope` / `reconcile.view` / `reconcile.hidePreview` / `triage.showOut` / `triage.hideOut` 随之删除。

**折叠计数**：重整前 12 处（含 2 处两级嵌套），重整后 5 处（文档原文预览、低置信推断候选、从其他文档补充依据、导入附件、技术详情），无嵌套、无并列常驻折叠块。

**空状态**：0 张卡时不显示汇总条与表格，只显示一块空态面板：一句说明 + 「从材料提炼」主按钮 + 「新增」次按钮；没有材料时主按钮改为「去简历中心上传材料」。

**兼容与数据**：不新增 RPC；对账、推断、分流、确认推断沿用 `evidence.reconcile` / `evidence.inferFields` / `evidence.confirmInference` / `evidence.triage.set`。列表问题标签与筛选在前端由对账结果按 `evidence_id` 合并，对账未完成前列表照常显示、标签为空。自动对账每次进入页面只发起一次，失败不自动重试，错误显示在汇总条提示行，由“重新对账”手动触发。列表单次最多加载 100 张（后端上限）；响应带 `next_cursor` 时在列表标题旁显示“仅加载前 N 张，汇总条计数为全量”的警示（`evidence-list-truncated`），超过 100 张后的按问题服务端筛选留作后续切片。

**层级与控件（2026-10-18 实现复核后收口）**：提炼抽屉遮罩使用新增 token `--z-drawer: 150`（高于侧栏 `--z-nav: 100`、低于确认对话框 `--z-modal: 200`），打开时侧栏被遮罩覆盖；详情面板保存按钮为主色“图标 + 文字”，与编辑/取消文字按钮同形态；推断候选的接受（主色）/ 修改后接受（描边）/ 否决（警示描边）为按钮组，不再使用下划线文字链。

**验证口径**：`tests/unit/gui` 中 `test_evidence_reconcile_ui.py` / `test_evidence_triage_ui.py` / `test_evidence_inference_ui.py`（如存在）按新位置改写断言，对账行相关 `data-testid` 迁到详情面板「对账发现」区；新增一条断言“页面进入后自动发起一次对账且列表与汇总条计数一致”。1440×900 下双栏顶部必须在首屏内（页头 + 汇总条合计高度 ≤ 160px）。

**`.pen`**：Screen/Evidence 需按本节重画（页头动作区、汇总条、带等级徽标与问题标签的表格、详情面板「对账发现」区、提炼抽屉），并删除 `materialReconcileFold`、`reconcileInferenceRow`、`refMaterialEntry`、`refMaterialItem`、`docPick1`（迁入抽屉实例）。实施前先完成画布，实施不得在画布未同步时标为完成。

**实施记录（2026-10-18）**：
- 代码：证据页按本节重排——页头动作改为刷新 /「从材料提炼」抽屉入口 /「新增」；进入页面自动跑一次对账（结果缓存至手动刷新）；常驻对账汇总条（计数按钮切换下方列表问题筛选，右端重新对账 / 运行推断 / 批量接受高置信）；列表列改为 标题 / 时间+等级 / 角色+等级 / 来源文档数 / 状态+问题标签，删除分数列与行内操作；详情面板新增「对账发现」（原因、不可追溯结果与原文候选、时间线索、疑似重复、分流、待确认推断接受/修改后接受/否决，低置信折叠）；「从材料提炼」改为右侧 560px 覆盖抽屉，引用外部目录管理迁到系统设置「材料来源」；删除关系提示条、对账折叠区/独立列表/就地摘要、显示已分流切换、页头导入按钮。
- 空态：0 张卡且无草稿/详情时只显示空态面板（提炼/新增，或去简历上传材料）；从空态新建或手动整理时仍渲染详情编辑区。
- 画布：Screen/Evidence 重画为 1440×980（页头、汇总条、双栏列表+详情、对账发现、底部删除），新增 `State/Evidence 提炼抽屉`（1440×980，遮罩 + 560px 抽屉，含材料/片段/原文预览与引用迁移说明）；删除 `materialReconcileFold`、`reconcileInferenceRow`、`refMaterialEntry`、`refMaterialItem`、`docPick1` 等旧节点；左侧屏幕按 40 间距重排。
- 测试：`test_evidence_reconcile_ui.py` / `test_evidence_triage_ui.py` 按新位置重写（自动对账、汇总计数筛选、详情对账发现与分流）；`test_evidence_page_contract.py`、`test_evidence_inference_ui.py`、`test_text_evidence_review_ui.py`、`test_material_reference_ui.py` 同步更新；新增列表 payload 等级/来源文档数字段测试。
