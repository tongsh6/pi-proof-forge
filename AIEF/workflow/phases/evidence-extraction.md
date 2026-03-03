# 证据提炼流程

## 目的
从原始语料产出可用 evidence cards，并生成缺口任务。

## 步骤
1. 收集语料（周报/复盘/PR/监控/压测）
2. 运行提炼（工具或 LLM）
3. 结构校验（results/artifacts 字段必须存在）
4. 缺口任务输出
5. 回填与复核

说明：候选池门控在匹配前执行，仅 `results` 与 `artifacts` 均非空的证据卡进入候选池。

## 产出
- evidence_cards/*.yaml
- gaps 清单
