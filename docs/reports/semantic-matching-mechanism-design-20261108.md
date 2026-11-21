# 语义匹配机制设计（2026-11-08）

> 背景：App Quick Run 语义评审失败 `semantic_quote_not_in_source:ec_0f6287d2:actions:1`。
> 处理原则（用户明确）：**不从优化 prompt 着手，而从整体机制、项目逻辑、业务算法设计**。
> 本文只描述机制与算法层面的现状问题、目标设计与迁移策略，不涉及提示词调优或模型参数调整。

## 一、现状机制梳理

1. **证据编号**：证据卡字段展开为 `fact_id = "{card_id}:{field}:{index}"`，`facts[fact_id] = {text, source_id, field, source_role, source_qualifiers}`。
2. **两阶段评审**：
   - recall：每卡相关度（0-100）+ requirement_ids + citations；
   - assess：每个「原文检查项」→ status（supported/partial/insufficient/conflict）+ citations + reason。
3. **引用契约**：模型必须输出 `{fact_id, quote}`，`quote` 必须逐字出现在 `fact['text']` 中，否则整批校验失败；两次尝试（原始 + 一次纠错）后仍失败 → 抛错。
4. **失败传播**：单批校验失败 → `run_semantic_matching` 整体失败 → matching 回退规则（CLI）或 Quick Run FAILED（App 的 `require_llm`）。
5. **缓存**：按「批请求指纹」缓存成功响应；失败不缓存。
6. **下游消费**：
   - 质量报告 fit 层消费 requirements/assessments（R2.1/R2.2）；
   - 生成阶段用 `selected_card_ids` 做语义选材；
   - `resume_assessment` 用 citations 判断「事实是否出现在简历正文」（present 检测）。
7. **附属校验**：direction（求职方向，建议层）评估失败会中断主评审；证据池含未入池/缺 results/artifacts 的卡会整体拒绝（`semantic_ineligible_evidence`）。

## 二、机制问题（为什么 prompt 层无法根治）

| # | 问题 | 机制根因 | 后果 |
| --- | --- | --- | --- |
| M-1 | 引用校验脆弱 | 把「事实核验」建立在「模型逐字复制原文」的准确度上；模型输出漂移（空白/标点/截断/改写）不可避免 | 单条引用失败 → 整批评审失败 → 整次 Quick Run 失败（用户实际遇到） |
| M-2 | 失败粒度粗 | 批次是原子成功单元，没有单卡/单检查项隔离与降级 | 一张卡异常拖垮全部语义结果 |
| M-3 | 资格耦合 | 不合格卡（未入池/缺 results/artifacts）导致整体拒绝 | 边界输入直接失败而非过滤 |
| M-4 | 建议层耦合 | 方向评估失败中断主评审 | 非门禁的建议层异常阻断主链路 |
| M-5 | 呈现检测依赖模型引用 | `present()` 用模型 quote 在简历正文中匹配 | 模型引用精度影响 resume_score 计算 |
| M-6 | 重试成本 | 失败不缓存、成功按批缓存；一次失败后重跑需重新评审全部批次 | 用户重试代价高 |

**结论**：quote 复制是模型的「转录任务」，不是「判定任务」。把转录质量作为事实门禁，是把不确定能力放在关键路径上。正确机制是：**模型只负责判定与事实选择（fact_id），事实文本由程序从证据库转录（程序取证）**。

## 三、目标机制设计

### M1 判定/取证分离（核心）

- 引用契约改为：`citations = [{fact_id}]`；模型可附带 `quote` 但仅作诊断线索，**不参与校验**。
- 校验只检查：fact_id 存在、属于该卡（recall）或允许集合（assess）、引用数量上限。
- **quote 由程序转录**：`quote = facts[fact_id]['text'][:160]`。
- 事实核验回到程序：引用的事实编号必须来自证据库 → 引用内容天然是原文，不存在伪造或漂移。
- schema 同步：citations required = `[fact_id]`，quote 可选。
- 语义报告版本升级 `evidence-semantic-v4`（契约变更，旧缓存自动失效并重算）。

### M2 失败隔离与降级

- recall：批次重试 1 次后仍失败 → 该批卡标记 `degraded_card_ids`（不进入 ranked、不参与选材），继续后续批次；**全部卡降级**时才显式失败（回退规则）。
- assess：批次失败 → 该批检查项标记 `degraded`（status=insufficient、reason=「评审服务降级」、citations=[]），按检查项补位后继续聚合，**不伪造 support**。
- 报告记录 `degraded_cards` / `degraded_checks` / statistics；下游 fit 层自然按 insufficient 处理。

### M3 资格过滤

- 不合格卡（`status != saved_eligible`、缺 results/artifacts）→ 过滤 + 记录 `excluded_card_ids`，继续评审合格卡；过滤后为空 → 明确错误 `semantic_no_eligible_evidence`。

### M4 方向评估解耦

- 方向评估（建议层）异常 → `direction_review = {status: unknown, reason: ...}`，继续主评审；方向结论不影响门禁。

### M5 呈现检测独立算法

- `present()` 不再依赖模型 quote：用 fact 原文与简历 claims 的**公共连续片段（≥8 字）**判定呈现；字段/来源匹配条件保留。
- resume_score 只由程序算法决定。

### M6 缓存与版本

- 成功批次继续按请求指纹缓存；失败批次不缓存（保留重试余地）；
- 契约版本升级后旧缓存与旧报告失效（显式 `semantic_report_changed`），重跑自动重算。

## 四、迁移与验收

- 版本：`evidence-semantic-v4`；旧 `.semantic.json` 因 method 不匹配失效（安全失败，重新评审）。
- 验收：
  1. 构造「引用只给 fact_id」的响应 → 通过且 quote 为程序转录原文；
  2. 构造「未知 fact_id / 跨卡引用」→ 失败（事实核验保留）；
  3. 单批持续失败 → 降级该批，其余批正常产出，报告含 degraded 信息；
  4. 不合格卡混入 → 过滤并继续；
  5. 方向评估异常 → 主评审继续；
  6. 全量单测通过、App Quick Run 语义模式可在模型偶发漂移下完成。
- 非目标：不改提示词质量、不调模型参数、不降低事实边界（引用仍必须来自事实编号）。

## 五、与既有规范的关系

- 事实保真：引用→fact_id→原文由程序转录，事实边界比「模型复制」更严格（不可能出现模型编造引用文本）。
- 显式回退：降级信息写入语义报告与运行日志；`require_llm` 语义保持（CLI 可要求严格语义失败；App 改为失败回退规则并显示提示）。
- 质量报告：fit 层把降级/过滤项按 insufficient 计，不把缺失当通过。
