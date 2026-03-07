# GUI 首批实施包（Kickoff Baseline）

> 状态：active
> 用途：把 GUI 从“规范已冻结”推进到“可以可控开工”，冻结首批脚手架、目录、文件范围、退出条件与禁止范围。
> 适用范围：首次创建桌面 GUI 工程骨架，或后续需要重建 GUI 基线时。

## 1. 目标

GUI 首批实施包只做以下事情：

- 建立 Tauri desktop shell 基线
- 建立 React + TypeScript + Tailwind + Zustand 前端骨架
- 建立 i18n、Design Tokens、App Shell、SideNav、9 页占位路由
- 建立 typed JSON-RPC bridge skeleton
- 建立最小可运行的 GUI 工程结构

本批次明确不做：

- 完整业务页面实现
- Python sidecar 真实业务逻辑
- 完整文件上传、PDF 导出、截图读写链路
- Quick Run / Agent Run 的真实运行流程
- 全量三态与断连态视觉实现

## 2. 开工前必读

开始 GUI 首批实施前，必须阅读并确认以下文档：

1. `ui/design/DESIGN.md`
2. `ui/design/piproofforge.pen`
3. `AIEF/context/tech/GUI_ARCHITECTURE.md`
4. `ui/design/contracts/sidecar-rpc.md`
5. `AIEF/docs/plans/gui-review-checklist.md`

进入编码前，必须显式确认：

- `DESIGN.md` 与 `.pen` 双真源同步规则成立
- 实现必须对照 `.pen` 验收
- design review / code review / 实现验收 三次检查必须执行
- JSON-RPC 字段级 contract 以 `ui/design/contracts/sidecar-rpc.md` 为准

## 3. 首批目录基线

首批 GUI 实施允许创建以下目录与文件：

```text
ui/
  package.json
  tsconfig.json
  vite.config.ts
  tailwind.config.ts
  postcss.config.js
  index.html
  src/
    main.tsx
    App.tsx
    app/
      routes.tsx
      providers.tsx
    components/
      shell/
        AppShell.tsx
        SideNav.tsx
    pages/
      overview/
      evidence/
      jobs/
      quick-run/
      agent-run/
      resumes/
      submissions/
      policy/
      system-settings/
    styles/
      tokens.css
      globals.css
    state/
      app-shell-store.ts
      sidecar-store.ts
    i18n/
      en.json
      zh.json
      index.ts
    lib/
      rpc/
        types.ts
        client.ts
        transport.ts
  src-tauri/
    Cargo.toml
    tauri.conf.json
    src/
      main.rs
```

说明：

- 页面目录在首批只放占位 screen，不承载完整业务逻辑
- `lib/rpc/` 在首批只负责 typed bridge 与 envelope，不实现完整 sidecar 功能
- `state/` 只建立全局 shell state 与 sidecar connection state，不提前下沉完整页面 store

## 4. 首批允许实现的内容

首批允许的实现内容仅限：

- Tauri 启动、窗口配置、前端载入
- AppShell 总体布局
- SideNav 及 9 页占位路由
- i18n 基础切换能力
- Design Tokens 到 CSS variables / Tailwind theme 的映射
- JSON-RPC envelope、transport interface、typed method stubs
- sidecar connection store 的最小状态机：`starting / ready / degraded / reconnecting / disconnected / stopped`

## 5. 首批禁止实现的内容

以下内容不得在首批混入：

- 真实的 Evidence CRUD
- 真实的 Job Leads / Submissions / Resume 数据拉取
- 完整 JSON-RPC 方法业务实现
- sidecar 进程管理以外的复杂 Rust 原生能力扩展
- 未经 contract 冻结就并行实现 UI 调用层与 Python sidecar handler
- 未经 `.pen` 对照直接自由发挥页面结构

## 6. 首批退出条件

首批实施包完成时，至少满足：

1. GUI 工程可启动到桌面窗口
2. 9 页导航可切换，顺序与设计一致
3. SideNav、AppShell、页面占位结构与 `.pen` 主框架一致
4. i18n 可切换单语运行态
5. CSS variables 与 Tailwind theme 已接通，核心 token 可用
6. JSON-RPC client 已有统一 envelope、transport interface、typed method stubs
7. sidecar 连接状态 store 已建立
8. GUI review checklist 已在开工与收口时各执行一次

## 7. 首批不通过条件

出现以下任一情况，本批次不算完成：

- 只起了前端脚手架，但没有 Tauri shell
- 只起了页面目录，但没有 AppShell / SideNav / 9 页路由
- JSON-RPC bridge 没有统一 envelope 与 typed 接口
- Token 没有真正接入 CSS variables / Tailwind
- 实现与 `DESIGN.md` 或 `.pen` 任一不一致
- 未执行 `AIEF/docs/plans/gui-review-checklist.md`

## 8. 推荐实施顺序

1. 建立 `ui/` 与 `ui/src-tauri/` 工程骨架
2. 接通 Tailwind、tokens、globals
3. 建立 AppShell + SideNav + 9 页占位路由
4. 建立 i18n 基础能力
5. 建立 RPC envelope/types/transport/client
6. 建立 sidecar connection store
7. 对照 `.pen` 做首轮结构校验

## 9. 后续批次切分建议

首批完成后，再进入以下批次：

1. Shared components batch：DataTable / FormField / Modal / OfflineIndicator
2. Page shell batch：Overview / Evidence / Jobs 主态页面
3. Runtime integration batch：Quick Run / Agent Run bridge + event stream
4. State completion batch：Loading / Empty / Error / 断连态
5. Full acceptance batch：按 `.pen` 与 checklist 做终验
