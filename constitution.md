# PiProofForge 项目宪法

> spec-kit constitution — 定义本项目不可妥协的工程原则。

## 核心使命

构建 **evidence-first** 框架：将原始工作材料转为结构化证据，生成事实保真的目标文档（简历等）。

---

## 不可妥协的原则

### 1. Evidence-First（证据优先）
- 任何输出必须可追溯到 Evidence Card。
- 没有对应证据的内容不得生成。
- `results` 或 `artifacts` 缺失的 Evidence Card 不进入候选池。

### 2. 事实保真（No Fabrication）
- 生成阶段严禁引入新事实。
- 所有匹配维度必须可解释（分项得分 + 缺口清单）。
- 输出质量反驱证据补全，而非降低标准。

### 3. 规范驱动开发（Spec-First）
- 新功能必须先写 OpenSpec spec，再驱动实现。
- 设计文档保存至 `AIEF/docs/plans/`，并经过用户确认后方可实施。
- 使用 `/opsx:propose` 启动新功能提案流程。

### 4. 测试驱动（TDD）
- 无失败测试不写生产代码。
- 红-绿-重构，不跳过任何步骤。
- Bug 修复必须先有复现测试。

### 5. 外部自动化驱动真实页面验收
- 场景化验收必须由外部自动化驱动真实页面、真实桌面壳或真实浏览器边界。
- 纯 handler/unit/contract/源码 marker 只能作为辅助证据，不能单独证明 `deep_verified`。
- 深度验收必须覆盖用户真实动作链，并留下可审计的页面事件、运行日志和 artifact。
- 审计层可以汇总证据，但不能替代页面级场景验收。

### 6. 最小化原则（YAGNI + DRY）
- 只实现当前需要的功能，不预留"未来可能用到"的扩展。
- MVP 不包含：全自动投递、重型 UI 平台、复杂多 Agent 辩论工作流。

---

## 工具链约定

| 工具 | 职责 |
|------|------|
| OpenSpec | 规范驱动：先写 spec，再实现 |
| superpowers | AI 执行质量：brainstorm → plan → TDD → review |
| spec-kit | 项目原则守护：本文件即入口 |

---

## 工作流入口

- 新功能：`/opsx:propose "你的想法"` → brainstorming skill → writing-plans skill
- 实现阶段：`test-driven-development` skill 强制执行 TDD
- 完成阶段：`requesting-code-review` skill 触发代码审查
- 归档变更：`/opsx:archive` 将已实施 spec 移至 archive

---

## 违规处理

发现以下情况，立即停止并重新规划：
- 代码先于 spec 被提议
- Evidence Card 无 results/artifacts 进入生成
- 生成输出中存在无证据支撑的内容
- 测试在实现之后补写
- 用纯内部调用、源码 marker 或页面加载替代外部自动化驱动真实页面的场景验收
