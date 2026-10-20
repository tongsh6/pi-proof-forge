# Design: resume-quality-standard-and-evidence-inference

## 1. 总体思路

三个弱点是一条依赖链，但实施顺序反过来：**先定标准 → 标准反推证据字段与等级 → 再改提炼与生成**。否则补卡没有"够不够"的判据，改生成没有"好不好"的判据。

```
 ┌──────────────┐    反推字段/等级     ┌──────────────────┐    提供材料     ┌──────────────┐
 │ 质量标准(R1-4)│ ───────────────────▶│ 证据可信等级(L1-5)│ ◀────────────── │ 材料库 + kb   │
 └──────┬───────┘                     └────────┬─────────┘                 └──────────────┘
        │ 质量报告                               │ 推断候选 → 用户确认
        ▼                                       ▼
 ┌──────────────┐    等级降级措辞       ┌──────────────────┐
 │ 分层评估器    │ ◀─────────────────── │ 生成器(模板+改写) │
 └──────────────┘                      └──────────────────┘
```

## 2. 现有能力与复用点

2026-10-20 提示词接续：公共产品语境集中在 `tools/prompts/context.py`，由现有 `LLMClient` 统一加入 system 消息；不复制用户口语，不让资料正文成为指令。职责归属结合上下文主动分析，不以字面第一人称作为唯一门槛；待确认推断、已审核事实和岗位要求保持各自用途。公共语境内容指纹参与四类已有缓存，质量判项有界接收 actions 并将完整行动字段纳入缓存指纹。

| 需要 | 现状 | 处理 |
| --- | --- | --- |
| JD 条目 × 证据支撑矩阵 | `tools/engines/matching/semantic_review.py` 已产出 11/8/85 子项与 `all_requirements_supported` | 复用；只增加"正文是否呈现 / 位置"两列 |
| 独立追溯 | `resume_trace`、PDF 无内部 id | 复用为 R1.1、R1.6 |
| 固定 PDF 与质量摘要同版本绑定 | 2026-10-13 已接入 `resume_sha256` | 质量报告替换质量摘要内容，绑定方式不变 |
| 年月线索 / 最接近原句 | `handle_evidence_reconcile` 的 `date_hints`、`verbatim_candidates` | 作为 L2 线索来源；L3 增加跨文档聚合 |
| 文档选择与检索 | `kb` CLI（find/grep/read/refs/person-docs） | 跨文档推断的检索层，不新建索引 |
| 分流与指纹绑定 | `evidence.triage.set` + `evidence_triage.json` | 推断候选与否决记录沿用同一绑定方式 |
| 任职区间 | 已确认职业档案（`profile.py`） | 作为 L2 约束与 R1.2 一致性校验来源 |
| 规则评估器 | `rule_evaluator.py` 代理指标 | 降级为 `legacy_scores`，不删除 |
| 自动通过 | `agent.py:836` `quality_passed` | 改为读取 `quality_report.auto_pass` |

## 3. 质量评估器设计

### 3.1 模块

`tools/engines/evaluation/tiered_evaluator.py`（新），实现 `EvaluationEngine` 协议，返回 `Scorecard` 扩展字段 `quality_report`。内部四个纯函数各判一层，便于单测：

```
evaluate_eligible(resume, profile, career_profile, cards, trace) -> TierResult
evaluate_fit(resume, semantic_review, jd_items, first_screen) -> TierResult
evaluate_strong(resume, cards, filler_lexicon) -> TierResult
evaluate_distinct(resume, jd_items, cards, highlights) -> TierResult
```

- 首屏定义：Markdown 正文按模板的 `<!-- first-screen-end -->` 标记切分；PDF 渲染后用页面高度二次校验（已有两页无裁切检查）。
- 量化判定：bullet 中的数字必须能在其 trace 到的卡 `results` 中找到相同数值，才计为"可验证量化"。
- 空话词表：`config/quality/filler_lexicon.yaml`，中英文，可由用户编辑。
- LLM 判项（R1.4、R2.1、R3.1、R3.5、R4.1）走受控 JSON：输入 bullet 列表 + 证据卡摘要 + JD 条目，输出必须含引用；缺引用的项按失败处理。缓存键 = `resume_sha256 + job_profile_id + cards_fingerprint`。

### 3.2 突出点提名

```
候选 = { card ∈ 正文使用卡 | 存在 jd_item 使 card 支撑 jd_item 且 exceeds(card, jd_item) }
exceeds 维度：规模(数量级/并发/品牌数)、难度(根因/迁移/高可用)、范围(跨团队/跨品牌)、稀缺组合(JD 两项以上同时满足)
过滤：time_range.level ∈ {L1,L2} ∧ role_scope.level ∈ {L1,L4}
排序：exceeds 维度数 > JD 条目权重 > 置信度
输出：top-2，附理由与引用
```

用户否决写入 `app-data/quality_decisions.json`（按 `resume_sha256`），重算时排除。

### 3.3 与审批页/Quick Run 的接口

- Scorecard JSON 增加 `quality_report`；RPC 响应不破坏现有字段。
- 审批页：四层折叠区，每条 failure 可点击跳到 bullet 或卡；`legacy_scores` 置于折叠"对比"区。
- `readiness.quality_passed = quality_report.auto_pass`；`reasons` 由 failures 生成，不再写"低于参考线 78"。

## 4. 证据推断设计

### 4.1 单文档提炼增强（L1/L2）

`_llm_draft_prompt` 增加 `document_metadata` 段：

```
# Document metadata (for date inference only; do not treat as content)
path: materials/worklog-private/2023/08/2023-08-15.md
filename_dates: [2023-08-15]
first_heading_date: 2023-08-14
modified_at: 2023-08-16
employment_window: 2022-06 ~ 2024-03   # 来自已确认档案，按材料所属公司
```

提示词改为：时间若原文明示 → `time_range` + `provenance.level=L1` + 引用句；否则若元数据可推 → `level=L2` + 引用元数据键；否则留空。角色同理但只允许 L1（上下文主体明确，包括人物/角色章节，不要求逐句出现“我”），跨文档归属的 L3 由 4.2 负责。

### 4.2 跨文档推断（L3）

新 RPC `evidence.inferFields`：

```
输入: card_ids[]（默认 = 分流为"值得补"且缺字段的卡）
步骤:
  1. kb 索引检索：已绑定且指纹一致的原文、绑定材料中的职业汇总优先，再按卡标题/背景相关性排序（限 20 篇，排除设计资料类来源）
  2. 聚合：保留每篇前 1000 字符及截断标记、日期线索、第一人称关键句与计数；计数只是辅助，不裁掉省略主语的原文语境
  3. LLM 一次调用：输入聚合结果 + 卡摘要 + 关联的已确认任职职责 + 任职区间，输出 time_range/role_scope 候选、等级 L3、置信度、每条依据的 document_id+excerpt
  4. 校验：时间在任职区间内；依据 excerpt 可在文档原文回读；否则丢弃该候选
输出: candidates[] 写入 app-data/evidence_inference.json（按卡指纹 + 文档集合指纹 + 已确认任职上下文 + 公共指令指纹 + 任务版本）
```

不写卡。对账面板新增"待确认推断"列：接受 → `evidence.update` 写字段与 provenance；修改后接受 → L4；否决 → 记录 `(card_fp, candidate_hash)`。

### 4.3 生成器消费等级

`template_assembler.py`：按 2026-10-20 用户修订，已采纳的 L3 职责、行动和限定保持原义，来源等级不再机械决定“负责人/参与者”；时间继续按 `precision` 格式化。`llm_rewriter.py` 保留不得超出原职责范围与时间精度的约束。当前 Quick Run 使用锁定字段的模板链；自由改写组件的词数检查不能证明所有责任限定均已受到保护。

## 5. 实施顺序

```
Phase A  标准与报告（无 LLM 变化）：specs → tiered_evaluator 规则部分 → quality_report 结构 → agent.py 接入 → 审批页展示
Phase B  LLM 判项与突出点：R1.4/R2.1/R3.1/R3.5/R4.1 → 提名与否决 → 真实 JD 回归（0 模型调用缓存路径）
Phase C  证据推断：provenance 字段/指纹 → 单文档元数据注入 → inferFields → 对账面板确认 → 用户在真实 85 卡上确认
Phase D  生成降级措辞与首屏重排 → P0-026 目标 JD 重新生成 → 真实 App 两页 PDF 验收
```

A 可独立验收；B 依赖 A；C 与 A/B 并行开发但验收依赖用户确认；D 依赖 B、C。

## 6. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| L3 推断把任职期当项目期（10-17 试验已见） | 任职区间只作上限约束不作候选值；要求多文档共现才产出区间；置信度 < 0.5 折叠 |
| LLM 判项不稳定导致 auto_pass 抖动 | 判项缓存按版本指纹；同版本同输入不重判；失败项必须有引用，无引用判失败 |
| 标准过严导致永远不通过 | 阈值进 `config/quality/`；质量报告先于 auto_pass 上线一轮，观察真实分布再定阈值 |
| 用户确认负担 | 候选按置信度排序、支持批量接受高置信候选；每卡只提名一次，否决不重复 |
| 过渡期两套分数混淆 | `legacy_scores` 仅在折叠区显示，文案明示"不参与通过判定" |

## 7. 文档同步

- `ui/design/DESIGN.md`：证据页"待确认推断"列、审批页四层质量报告。
- `ui/design/contracts/sidecar-rpc.md`：`evidence.inferFields`、`evidence.update` provenance 字段、Scorecard `quality_report`。
- `docs/execution-roadmap.md`：在 P0-026 下记录本变更为"简历质量修复"实施载体，不新增 `next`。
- `docs/project-ledger.md`：按阶段记录真实数据结果（缺字段计数、真实 JD 质量报告）。
