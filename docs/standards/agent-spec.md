# Agent 规范

## 目标
定义 Agent 在本项目中的职责边界与输入输出约束。

## 角色
- Extractor Agent：原始语料 -> evidence card
- Matcher Agent：job profile + evidence cards -> matching report
- Generator Agent：matching report -> resume A/B
- Evaluator Agent：resume -> scorecard

## 必须遵守
- 不编造事实。
- 输出格式必须符合对应 schema 或模板。
- 缺失信息必须进入 gaps/task，而不是补写事实。
