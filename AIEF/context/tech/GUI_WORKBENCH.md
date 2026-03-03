# GUI 工作台（初版）

## 目标
- 提供可视化入口执行 pipeline，降低 CLI 使用门槛。
- 在单页内完成输入、执行、结果预览与快速迭代。

## 页面结构
1. 输入区：多目录/多文件原始语料、岗位画像导入与编辑、run_id、LLM 选项
2. 执行区：四阶段状态（提炼/匹配/生成/评测）
3. 过程区：Reasoning Trace（执行日志流）
4. 结果区：Match Report、Resume A、Resume B、Scorecard 标签页

## 关键交互
- `执行 Pipeline`：触发完整流程并展示阶段状态
- `使用 LLM 增强`：启用 LLM 模式
- `严格 LLM`：启用 require-llm，不允许回退
- Tabs 切换：在四类结果之间快速审阅
- `中文/EN`：统一页面语言切换

## 原型文件
- `ui/prototype/index.html`
- `ui/prototype/REVIEW.md`
