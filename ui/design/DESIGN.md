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
    - Gaps / 缺口待办 — 红色计数徽标 + 警告项列表

### 2. Resumes / 简历中心

**职责**: 个人资料维护、用户上传简历管理、系统生成简历管理与导出

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
    - 上半区: 已生成简历列表
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

**布局**:
- 顶部: 页面标题 + "New Card / 新增" 和 "Import / 导入" 按钮
- 内容区两栏:
  - 左栏 (fill): 证据卡列表表格
    - 表头: Title / 标题, Time / 时间, Role / 角色, Score, Status
    - 行数据: 卡片标题 + ID, 时间范围, 角色, 分数（彩色）, 状态标签
    - 选中行高亮 (accent-bg 背景)
  - 右栏 (420px): 选中卡片详情面板
    - 头部: EC-ID + 状态标签 + 编辑/删除图标
    - 字段: Title / 标题, Time Range / 时间, Role / 角色, Context / 背景, Actions / 行动, Results / 成果（绿色）, Stack & Tags / 技术栈（标签 pills）
    - Artifacts / 附件:
      - 已上传文件列表（文件名、类型、大小、上传时间）
      - 支持预览、删除、重新上传
      - 与 "Import / 导入" 按钮联动，支持拖拽上传

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
  - 主区域: 线索列表表格
    - 表头: Company / 公司, Position / 职位, Source / 来源, Status, Updated At / 更新时间, Action
    - 行数据: 公司名 + 职位名, 来源渠道（招聘站/内推/官网）, 当前状态, 最近更新时间, 收藏/转为 Profile
  - 右侧详情面板 (420px):
    - 字段: Lead ID, 来源链接, 职位描述摘要, 关联 Job Profile, 最近跟进记录
    - 操作: 收藏、标记已跟进、转为 "Job Profile / 岗位画像"
  - 支持: 来源/状态筛选、全文搜索、仅看已收藏

### 5. Quick Run / 快速执行 (原 Pipeline)

**职责**: 4 阶段 pipeline 单次可视化（提炼/匹配/生成/评测）。与 Agent Run 的区别：Quick Run 是一次性执行，不含多轮循环和门禁系统。

**布局**:
- 顶部: 页面标题 + "Run / 执行" 主按钮
- 阶段指示条 (4 步, 箭头连接):
  - 已完成: 绿色边框 + circle-check 图标 + 耗时/结果
  - 进行中: cyan 边框 + loader 图标 + elapsed 计时
  - 等待中: 灰色边框 + circle 图标 + "Waiting..."
- 下方两栏:
  - 左栏 (fill): Stage Output / 阶段输出 — 深色终端风格日志面板（JetBrains Mono, 带时间戳）
  - 右栏 (320px): Scores / 评分 — 6 条 ScoreBar (K/D/S/Q/E/R) + 总分

### 6. Agent Run / 自主运行

**职责**: 10 状态机、多轮追踪、门禁可视化、事件流

**布局**:
- 顶部: 页面标题（含 Run ID / 开始时间 / 轮次） + Running 状态标签 + "Stop / 停止" 按钮
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
      - 操作: Approve (绿色) / Reject (红色) / Skip (灰色)
    - 底部: "Submit Decisions / 提交决策" 按钮 + 已审批/待审批计数
    - auto 模式下此面板不显示，左栏保持 N-Pass Gate 视图

**状态机状态**: INIT → DISCOVER → SCORE → GENERATE → EVALUATE → GATE → REVIEW → DELIVER → LEARN → DONE

### 7. Submissions / 投递记录

**职责**: 投递历史、步骤详情、截图、通道降级、重试

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

### 8. Policy / 策略配置

**职责**: Policy 编辑器、企业例外清单、投递/门禁策略治理

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
    - Exclusion List / 排除:
      - 企业名列表 + 添加/删除 + 导入/导出
      - 命中说明: 为什么被排除、命中时间、备注
      - legal entity / 主体排除与 alias / 别名排除分区展示

### 9. System Settings / 系统设置

**职责**: 通道配置、模型配置、凭证状态、连通性检查

**布局**:
- 顶部: 页面标题 + "Save / 保存" 主按钮
- 内容区两栏:
  - 左栏 (220px): 系统分组导航
    - Channels / 通道 (激活)
    - LLM Config / 模型
  - 右栏 (fill): 系统配置区域
    - Channels / 通道:
      - Liepin / Email 通道开关、优先级、失败降级策略、凭证状态
      - 支持测试连接与最近一次可用性检查
      - 显示 fallback 顺序、最近错误与最近成功时间
    - LLM Config / 模型:
      - provider, model, base_url, api_key（掩码）, timeout, temperature
      - 支持校验、连通性测试、默认模型标记
      - `api_key` 默认不回显明文；仅支持“已配置 / 未配置”状态、更新、清除
      - 敏感信息必须存储在 OS credential store（macOS Keychain / Windows Credential Manager / Secret Service），禁止落盘到明文 JSON、localStorage 或日志

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
| Quick Run | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | 日志条目与总评分块已显式拆分 |
| Agent Run | 已覆盖 | 已覆盖 | 已覆盖 | 已覆盖 | 已达标 | Gate Items 与 Event Items 已显式拆分 |
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
| SideNav | `vfxIc` | 侧边导航栏，含 Logo + 9 个导航项 + 语言切换 |
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
| z-dropdown | 10 | 下拉菜单 |
| z-modal | 50 | 模态框、遮罩层内容 |
| z-tooltip | 100 | Tooltip、全局浮层 |

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
- Quick Run: 输入契约至少包含 `evidence_id`, `job_profile_id`, `options`；结果契约至少包含 `stage_results[]`, `scores`, `logs[]`
- Agent Run: 返回 { run, gate_checks[], events[], next_event_cursor, review_candidates[], review_decisions[] }；事件流分页必须支持 cursor + limit；review_candidates 仅在 delivery_mode=manual 且状态为 REVIEW 时有值
- Resumes: 页面至少需要 `personal_profile`、`uploaded_resumes[]`、`generated_resumes[]` 与当前选中版本的 `preview` 载荷；首版 bridge 可通过聚合现有 profile 源与 resume list 完成，不强制在本轮冻结为单一 RPC 方法
- Submissions: 返回 `{ items[], next_cursor }`，支持 `company/channel/status/date_range` 筛选，支持 `submitted_at/status` 排序；详情需返回 `steps[]`, `screenshots[]`, `failure_detail`
- Policy: 返回 `{ gate_policy, exclusion_list }`；无分页；两个子模块需支持独立保存结果与错误反馈
- System Settings: 返回 `{ channels, llm_config }`；无分页；敏感字段默认掩码，支持独立测试连接与保存结果反馈

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
- System Settings: `Loading` 为系统配置 skeleton；`Empty` 仅用于 channels / provider 尚未配置；`Error` 为保存失败、测试连接失败或 credential store 访问失败

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
