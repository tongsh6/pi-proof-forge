# Proposal: resume-quality-standard-and-evidence-inference

## Problem

项目的核心产物是**简历**，但当前系统没有回答"一份高质量简历是什么样的"。三个相互依赖的弱点（2026-10-13 ~ 10-17 台账与代码核对）：

1. **质量标准缺位**。`tools/engines/evaluation/rule_evaluator.py` 的维度是代理指标：`quant` = 数字字符数/行数，`clarity` = 长度 ≤ 4000，`citation` = 正文含 `-`。`agent.py` 的 `quality_passed` 以 `evaluation_score ≥ 78` 为参考线。58/58/71 这类分数不能说明简历是否合格、是否对位 JD、哪里突出。标准缺位导致补多少卡都不知道"够不够"。
2. **证据卡时间/角色大面积缺失**。85 张真实卡中缺时间 60、缺职责 63（2026-10-17 只读对账）；51 可用卡仅 5 张满足展示条件。根因不是 AI 能力，而是提炼设计：单文档 ≤ 24k 字、看不到文件名/路径日期/修改时间/其他文档/职业档案任职区间，提示词要求 "Leave role_scope and time_range empty when not explicitly supported"（`tools/sidecar/handlers/evidence.py:600-610`）。10-17 试验证明的是"原文没有逐字句"，测的是字符串相似度而非推理。
3. **简历取舍与表达问题**（10-13 复盘）：首屏定位弱、旧项目挤占、语义夸大。这些是在证据池只有 5 张合格卡下生成的，上限被卡质量封死。

简历引用证据卡的追溯链路（trace 20/20、PDF 不含内部 id）已通，不在本变更范围。

## Goals

1. **用简历文体定义高质量**：简历是面向目标岗位招聘决策者的 1–2 页事实型说服文档，首屏 30 秒决定"是否值得面试"，细读时每句经得起追问。据此建立四层标准：合格（硬门禁）→ 对位（符合目标 JD）→ 优质（表达）→ 突出（相对目标 JD 的差异化证据）。
2. **质量报告替代单一分数**：输出分层 pass/fail + 理由 + 定位到具体 bullet/卡的缺口；"自动质量通过"以四层标准定义，替换 78 参考线。
3. **证据卡带出处推断**：引入可信等级 L1 原文明示 / L2 文档元数据推断 / L3 跨文档推断 / L4 本人陈述 / L5 无依据。提炼与补全可产出 L2/L3 候选（含引用与置信度），进入对账面板由用户批量确认/否决；不自动写卡。
4. **生成保留职责与来源等级**：按 2026-10-20 用户修订，已采纳的 L3 职责保留主导/负责人及责任限定，不因来源等级机械降为参与；L2 时间以年或年月精度呈现，L5 时间卡不进正文。
5. **突出点选择**：相对目标 JD 自动提名 1–2 条差异化证据并置于首屏，每条须 L1/L2 支撑且可被用户替换。

## Non-Goals

1. 不重建材料库、不重写匹配引擎（沿用 85 子项语义评审作为"对位"层输入）。
2. 不做 RAG/向量检索；跨文档推断使用既有 `kb` 索引与 `evidence.reconcile` 的 `date_hints`。
3. 不自动把推断写入证据卡或职业档案；所有 L2/L3 候选必须经用户确认。
4. 不新增上传/投递/平台写操作；不改变 P0-026 唯一 `next`。
5. 不追求通用求职者 rubric；首版标准面向本项目的目标岗位簇（平台/架构/AI 工程），通过配置可调。

## Non-Goals Rationale and Triggers

| Item | 当前判定 | 为什么现在不做 | 进入范围触发条件 |
| --- | --- | --- | --- |
| 重写匹配引擎 | never in this change | 对位层所需的 JD 职责 × 卡支撑矩阵已由语义评审产出，缺的是汇成结论 | 不适用 |
| RAG/向量检索 | later with trigger | `kb` 索引 + 年月线索已够做 L2/L3；向量库增加维护成本且不提升可追溯性 | 材料 > 2 万档且跨文档推断召回 < 50% |
| 自动写卡 | currently out-of-scope | 违反 No Fabrication 的边界只有一步之遥；先用用户确认建立信任 | 连续 3 批次 L2/L3 候选用户接受率 ≥ 90% |

## Scope

- 新增 `specs/resume-quality/spec.md`：四层标准、每层判据、自动通过定义、质量报告结构。
- 新增 `specs/evidence-provenance/spec.md`：可信等级、字段、推断来源、措辞降级规则。
- 修改 `tools/engines/evaluation/`：新增分层质量评估器，规则评估器降为辅助信号；`agent.py` 的 `quality_passed` 改为消费质量报告。
- 修改 `tools/sidecar/handlers/evidence.py`：提炼提示词注入文档元数据与任职区间约束；新增推断候选 RPC；对账面板支持批量确认。
- 修改 `tools/engines/generation/`：按可信等级降级措辞；首屏突出点选择与 JD 职责对齐。
- 修改 `ui/`：证据页推断候选确认区；Quick Run/审批页显示分层质量报告。
- 同步 `ui/design/DESIGN.md`、`ui/design/contracts/sidecar-rpc.md`、`docs/execution-roadmap.md`、`docs/project-ledger.md`。

## Expected Outcomes

1. 任一目标 JD 生成后，App 展示四层质量报告，每条未通过项指向具体 bullet 或证据卡。
2. 真实 85 卡经推断候选 + 用户批量确认后，缺时间/缺角色数显著下降（目标：缺时间 ≤ 15、缺角色 ≤ 20，以 App 实测为准，不以合成夹具为准）。
3. 同一目标 JD（P0-026 当前岗位）重新生成的两页 PDF：合格层全通过、对位层 JD 前三职责均在首屏有支撑、至少 1 条突出点，由用户在真实 App 验收。
4. 任何 L2/L3 字段在 `resume_trace` 中可见其推断依据与用户确认记录。
