# Evidence Card Schema（经历卡）

## 目标
- 定义最小可用字段，支持证据门控与可追溯生成。

## 最小字段（MVP）
- `id`：唯一标识
- `title`：战役名（一句话）
- `time_range`
- `context`：业务场景与约束
- `role_scope`：职责边界（Owner/Tech Lead/执行）
- `actions`：3–5 条关键动作
- `results`：至少 1 条量化结果
- `stack`：强相关技术栈
- `artifacts`：PR/监控截图/压测报告/复盘/设计文档（文件名或链接）
- `tags`：性能/稳定性/交付治理/DDD/数据治理/活动营销/门店等
- `interview_hooks`：面试深挖点与反问点

## 约束规则
- `results` 不能为空
- `artifacts` 不能为空
- `actions` 至少 3 条
- `time_range` 必填

## 示例（YAML）
```yaml
id: "ec-2026-001"
title: "高峰期订单系统稳定性治理"
time_range: "2025-10 ~ 2026-01"
context: "峰值 5k QPS，跨 6 个系统，容灾窗口极短"
role_scope: "Owner"
actions:
  - "梳理核心链路并拆分熔断策略"
  - "引入灰度与回滚流程"
  - "建立告警分级与响应手册"
results:
  - "故障率下降 43%"
stack:
  - "Java"
  - "Redis"
  - "Kafka"
artifacts:
  - "postmortem-2025-11.pdf"
  - "dashboard-slo.png"
tags:
  - "稳定性"
  - "治理"
interview_hooks:
  - "为何选择分级告警而非单一阈值？"
```
