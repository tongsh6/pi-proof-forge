# 上下文加载

## 目标
在执行前加载最小必要上下文，保证输出稳定与一致。

## 加载顺序
1. `AGENTS.md`
2. `context/INDEX.md`
3. 对应 phase 文档（workflow）
4. 对应模块文档（context/tech）
5. 经验库（context/experience）

## 场景映射
- 提炼任务：加载 `context/tech/EVIDENCE_EXTRACTION.md`
- 匹配任务：加载 `context/tech/SCORING.md`
- 生成任务：加载 `context/tech/GENERATION.md`
- 评测任务：加载 `context/tech/EVALUATION.md`

## 约束
- 不相关上下文不加载。
- 优先加载可执行文档（workflow + tools）。
