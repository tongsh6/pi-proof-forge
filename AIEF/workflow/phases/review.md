# 审查阶段

记录评审清单和验收结论。

## 用途

确保实现结果符合设计意图，并满足项目质量要求。

## 评审清单

- [ ] 实现是否覆盖了提案中的所有目标？
- [ ] 是否遵循了现有代码模式？
- [ ] 事实保真：生成内容是否未添加新事实？
- [ ] 是否有新的经验需要沉淀到 context/experience/lessons/？
- [ ] REPO_SNAPSHOT.md 是否需要更新？
- [ ] workflow/INDEX.md 是否需要更新？

### GUI 变更附加清单

当本次变更涉及 GUI 设计、GUI 代码、GUI schema 或 sidecar 集成时，评审必须额外执行 `AIEF/docs/plans/gui-review-checklist.md`，并至少确认：

- [ ] `ui/design/DESIGN.md` 与 `ui/design/piproofforge.pen` 是否同步
- [ ] GUI 实现是否同时对齐文档与 `.pen` 资产
- [ ] Design review / code review / 实现验收 是否都执行了对应 GUI 检查项
- [ ] 若存在文档、`.pen`、实现三方任一不一致，是否已判定该变更不能通过评审

## 输出

- 审查结论（通过 / 有条件通过 / 需返工）
- 沉淀经验记录（如有）

## L3 经验沉淀要求

- 每次重要变更至少添加一条 lessons 记录
- 高频模式同步更新 summaries/
