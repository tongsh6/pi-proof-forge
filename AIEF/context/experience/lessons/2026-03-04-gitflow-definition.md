# 先定义 GitFlow，再推进自动化实现

**日期**：2026-03-04
**场景**：仓库已公开到 GitHub，用户要求先定义 GitFlow 流程以规范后续协作与发布。

## 问题

缺少统一分支策略时，`feature/release/hotfix` 边界不清晰，容易出现：
- 直接向主分支推送
- 发布修复未回流 `develop`
- 历史可追踪性弱（版本与变更路径断裂）

## 处理

- 新增 `docs/standards/gitflow.md`，明确：
  - 分支模型（`main/develop/feature/release/hotfix`）
  - 命名规范
  - PR 门禁与校验要求
  - 发布与热修闭环（含回合并）
- 更新 `docs/standards/INDEX.md`，将 GitFlow 纳入标准入口

## 经验

- 开源初期优先固化“协作协议”（分支与发布）比先堆功能更重要
- 文档需同时给“规则 + 可执行命令示例”，否则团队执行一致性会下降
