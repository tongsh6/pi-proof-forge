# UI 终版设计审查报告

审查日期：2026-03-07（终版）

审查范围：`ui/design/piproofforge.pen`、`ui/design/DESIGN.md`、`README.md`、`AIEF/context/tech/GUI_ARCHITECTURE.md`

审查结论：GUI 终版文档基线已统一。`ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen` 共同定义产品规范，`README.md` 与 `AIEF/context/tech/GUI_ARCHITECTURE.md` 已对齐到同一条桌面端路线：Tauri + React/TypeScript + Python sidecar。

---

## 一、审查基线

### 权威来源

- `ui/design/DESIGN.md`
- `ui/design/piproofforge.pen`

`ui/design/DESIGN.md` 已明确声明主设计文件为 `ui/design/piproofforge.pen`，并定义了桌面端 9 页信息架构、导航顺序、可复用组件、Design Tokens 与双语策略。

### 对齐文档

- `README.md`
- `AIEF/context/tech/GUI_ARCHITECTURE.md`

上述文档现在与终版设计口径一致：GUI 以桌面端产品为目标，设计真源为 `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen`。

---

## 二、核心判断

### 1. Pencil 应为唯一设计真源

Pencil 设计已经定义完整的产品级桌面应用结构：

- 9 个页面，从 Overview 到 Policy / System Settings
- SideNav 作为全局导航容器
- Quick Run 与 Agent Run 分离
- 组件与 Token 已形成统一设计语言

因此，后续 UI 审查、实现拆解、前端验收都应围绕 `ui/design/DESIGN.md` 的页面职责和 `ui/design/piproofforge.pen` 的画布内容进行。

### 2. 文档口径已压平为唯一终版

当前文档体系不再保留并列 GUI 路线。以下内容已经统一：

- 产品形态：桌面应用
- 技术栈：Tauri + React/TypeScript + Python sidecar
- 通信模型：JSON-RPC over stdio
- 设计真源：`ui/design/DESIGN.md` + `ui/design/piproofforge.pen`

---

## 三、发现的问题

### ~~P0：权威设计源声明与实际资产不一致~~ ✅ 已解决

> **解决时间**：2026-03-07
>
> `ui/design/piproofforge.pen` 已补齐完整设计内容，包括 11 个可复用组件和 9 个页面（Overview、Evidence、Jobs、Quick Run、Agent Run、Resumes、Submissions、Policy、System Settings），与 `DESIGN.md` 描述一致。Design Tokens 中的 Colors、Spacing、Radius 已通过 Pencil variables 定义；Typography、Shadows、Layering、Motion 仍需在实现阶段补齐。
>
> 原发现的空白 800x600 frame 问题不再存在。

### ~~P0：GUI 技术路线存在冲突~~ ✅ 已解决

> **解决时间**：2026-03-07
>
> `AIEF/context/tech/GUI_ARCHITECTURE.md` 已重写为终版 GUI 架构文档，技术路线统一为 `Tauri + React/TypeScript + Python sidecar`，通信模型统一为 `JSON-RPC over stdio`。

### P1：双语策略需要从“视觉表达”切换为“实现约束”

Pencil 设计中使用 `English / 中文` 双语标签表达信息层级，但 `ui/design/DESIGN.md` 已明确指出实现层禁止硬编码双语，必须通过 i18n 切换输出单语界面。

结论：后续 UI 审查不应再检查“是否双语同时上屏”，而应检查：

- 是否存在 `t('key')` 式文本抽取
- 语言切换入口是否在 SideNav 底部
- 是否避免硬编码中英混排

### P1：主导航和页面职责是终版实现边界

当前 Pencil 设计的主导航顺序为：

Overview -> Resumes -> Evidence -> Jobs -> Quick Run -> Agent Run -> Submissions -> Policy -> System Settings

这意味着后续实现不得回退为单页工作台，也不得把 Quick Run 与 Agent Run 合并处理。

同时，`Resumes / 简历中心` 不再只承载“生成结果预览”，而是个人使用场景下的资料主入口，必须覆盖：

- `Personal Profile / 个人资料`
- `Uploaded Resumes / 已上传简历`
- `Generated Resumes / 系统生成简历`

---

## 四、终版审查重点

后续设计审查与实现验收应重点检查：

- 是否完整覆盖 9 页信息架构
- 是否坚持单语 i18n 运行态
- 是否按终版要求实现 Resumes 资料主入口、Evidence 附件交互、Job Leads、Submissions 详情、Policy/System Settings 配置页
- 是否补齐 Loading / Empty / Error 三类关键状态
- 是否围绕 sidecar 连接状态建立统一状态管理与错误反馈

### 设计审查执行要求

凡是涉及 GUI 页面结构、共享组件、Design Tokens、状态页、导航或交互规则的变更，设计审查必须显式执行 `docs/plans/gui-review-checklist.md` 的 Design Review Checklist。

若 `ui/design/DESIGN.md`、`ui/design/piproofforge.pen`、实现验收标准三者存在任一不同步，该次设计审查不得通过。

---

## 五、终版文档对齐完成标准

以下条件同时满足，视为 GUI 文档基线完成冻结：

1. `README.md`、`ui/design/DESIGN.md`、`ui/design/REVIEW.md`、`AIEF/context/tech/GUI_ARCHITECTURE.md` 对 GUI 技术路线只有一种说法。
2. `已定版`、`正式实现要求`、`设计真源` 这几个术语语义一致。
3. 通信模型只保留 `JSON-RPC over stdio` 一种终版方案。
4. 设计真源固定为 `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen`。

---

## 六、优先级建议

### P0

- ~~补齐 `ui/design/piproofforge.pen`，使其真正反映 `ui/design/DESIGN.md` 描述的 9 页设计~~ ✅ 已完成
- ~~统一 GUI 技术路线与通信模型文档口径~~ ✅ 已完成

### P1

- 明确页面职责、共享组件、i18n、sidecar 状态等正式实现要求
- 基于终版设计编写实现验收清单

### P2

- 在实现阶段补齐通用组件、Design Tokens、三种页面状态与 sidecar 通信状态表达

---

## 七、正式结论

本项目当前 GUI 规范已冻结为唯一终版，不再保留并列的替代路线。

`ui/design/piproofforge.pen` 已补齐完整的 9 页设计和 11 个可复用组件，与 `ui/design/DESIGN.md` 描述一致。`README.md` 与 `AIEF/context/tech/GUI_ARCHITECTURE.md` 已同步到同一终版口径。

后续工作的正确顺序：

1. ~~冻结 GUI 终版文档基线~~ ✅ 已完成
2. 以终版设计和架构文档为准进行桌面端实现
3. 基于终版规范编写实现验收清单并推进落地
