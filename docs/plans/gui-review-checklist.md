# GUI 评审与验收清单

> 状态：active
> 用途：把 GUI 终版治理规则接入 design review、code review、实现验收，避免 `DESIGN.md`、`.pen` 与实现三方漂移。
> 适用范围：任何修改 `ui/design/DESIGN.md`、`ui/design/piproofforge.pen`、GUI 实现代码、GUI token / schema / 状态约束、sidecar integration 的变更。

## 1. 先决条件

开始 GUI 设计审查、代码审查或实现验收前，先确认：

- [ ] 当前 GUI 真源仍为 `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen`
- [ ] 当前 GUI 架构真源仍为 `AIEF/context/tech/GUI_ARCHITECTURE.md`
- [ ] 当前 GUI bridge contract 真源仍为 `ui/design/contracts/sidecar-rpc.md`
- [ ] 当前变更范围已经明确：是改设计规范、改设计资产、改实现代码、改 sidecar integration，还是多者联动

## 2. Design Review Checklist

当变更涉及页面结构、导航、共享组件、Design Tokens、状态页或交互规则时，设计评审必须检查：

- [ ] `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen` 是否同步修改
- [ ] 是否存在只改文档、不改 `.pen` 的情况
- [ ] 是否存在只改 `.pen`、不回写文档的情况
- [ ] 9 页信息架构是否仍完整，且未回退为单页工作台
- [ ] SideNav 导航顺序是否仍为 `Overview -> Resumes -> Evidence -> Jobs -> Quick Run -> Agent Run -> Submissions -> Policy -> System Settings`
- [ ] 是否保持 `Policy / 策略配置` 与 `System Settings / 系统设置` 两个正式页面边界，未回退为单个 `Settings`
- [ ] Quick Run 与 Agent Run 是否仍明确分离，未在职责、布局、状态表达上被重新混合
- [ ] 页面 / 导航 / CTA / 面板标题是否遵守 `English / 中文` 命名规则
- [ ] 状态标签、技术标签、代码值、协议方法名是否保持纯英文
- [ ] 支持性板块（状态稿 / 约束稿 / 协议稿）是否使用纯英文命名，并遵守 `<Page> - <State|Constraint>` 规则
- [ ] 中文主译名是否与 `ui/design/DESIGN.md` 的统一术语表一致，未出现语义漂移
- [ ] Design Tokens 变更是否已同步说明到文档，并能落到后续实现映射
- [ ] Loading / Empty / Error / 断连态等状态设计是否已在文档与 `.pen` 中同步体现

## 3. Code Review Checklist

当变更涉及 GUI 实现代码、sidecar 协议、状态管理、组件实现时，代码评审必须检查：

- [ ] 实现是否逐页对照 `ui/design/piproofforge.pen`，而不是只凭 `DESIGN.md` 主观理解
- [ ] 实现是否与 `ui/design/DESIGN.md`、`ui/design/piproofforge.pen` 同时一致
- [ ] 若变更涉及 bridge / sidecar，是否与 `ui/design/contracts/sidecar-rpc.md` 同时一致
- [ ] 若实现改变了页面结构、组件、tokens、状态、协议，设计文档与 `.pen` 是否已同步回写
- [ ] i18n 是否保持单语运行态，未出现 `English / 中文` 双语同屏硬编码
- [ ] 实现命名是否遵守术语表：如 `Resumes / 简历中心` 仅用于页面，`Resumes / 简历版本` 仅用于统计项，`Personal Profile / 个人资料` 不得回退为旧称
- [ ] `Submissions / 投递记录`、`Submissions / 投递次数`、`Failure Detail / 失败详情` 等关键术语是否未被混用
- [ ] Quick Run / Agent Run 的状态、日志、门禁、信息密度是否仍按终版规范分离
- [ ] Evidence artifacts、Submissions screenshots、sidecar 生命周期、错误态是否符合终版约束
- [ ] JSON-RPC schema、错误码、事件流字段变更是否已同步更新文档
- [ ] 若当前仍处于 GUI 首批实施阶段，是否遵守 `docs/plans/gui-first-batch-kickoff.md` 的允许/禁止范围

## 4. 实现验收 Checklist

当变更准备交付或进入验收时，必须检查：

- [ ] 9 页页面结构是否与 `.pen` 一致
- [ ] 共享组件是否与设计资产和文档定义一致
- [ ] 页面名、统计项名、设置分组名、支持性板块名是否全部符合命名规则与统一术语表
- [ ] Design Tokens 是否已映射到实现层（如 CSS variables / Tailwind theme）
- [ ] Loading / Empty / Error / 断连态是否补齐且行为一致
- [ ] 分页 / 排序 / 筛选 / 窗口尺寸 / sidecar 生命周期等约束是否已实现
- [ ] bridge contract 是否与 `ui/design/contracts/sidecar-rpc.md` 一致
- [ ] 若实现与 `DESIGN.md` 一致但与 `.pen` 不一致，或反之，是否已判定为不通过

## 5. 一票否决条件

出现以下任一情况，该次 GUI 变更不得视为完成：

- [ ] `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen` 未同步
- [ ] 实现与文档一致但与 `.pen` 不一致
- [ ] 实现与 `.pen` 一致但与文档不一致
- [ ] bridge / sidecar 实现与 `ui/design/contracts/sidecar-rpc.md` 不一致
- [ ] GUI 评审未显式执行本清单

## 6. 执行要求

- Design review 必须执行第 2 节
- Code review 必须执行第 3 节
- 实现验收必须执行第 4 节与第 5 节
- 若变更同时涉及设计资产和实现代码，三个环节都要执行，不得跳过
