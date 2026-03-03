# 模式：经验管理（官方命名别名）

沉淀、索引与复用项目经验。

> 本文件遵循 AIEF 官方 L1 命名约定。
> 项目完整经验管理规则见：[docs/standards/patterns/experience-management.md](experience-management.md)

## 核心原则（AIEF L3）

```
第 1 次 → 建立经验索引
第 2 次 → 复用经验，降低成本
第 N 次 → 边际成本趋近于零
```

## 经验沉淀触发条件

- 重要变更完成
- Bug 修复后（根因已确认）
- 新模式/反模式被发现
- Pipeline 端到端运行完成

## 经验文件规范

```
路径: context/experience/lessons/YYYY-MM-DD-topic.md
结构:
  1. 背景
  2. 问题
  3. 根因
  4. 解决方案
  5. 验证方式
  6. 可复用结论
```

## 索引维护

每次新增 lesson 后更新 `context/experience/INDEX.md`。
高频主题（≥3 条 lesson）同步更新 `context/experience/summaries/`。
