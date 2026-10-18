# Tasks: resume-quality-standard-and-evidence-inference

> 设计依据：`design.md` 第 3–5 节；标准依据：`specs/resume-quality/spec.md`、`specs/evidence-provenance/spec.md`
> TDD 约束：每项先写失败测试再实现；合成夹具只验结构与规则，"质量达标"只能由真实 App 验收得出
> 边界：无上传/投递/平台写操作；不改变 P0-026 唯一 `next`

---

## Phase A - 标准与分层质量报告（规则部分）

- [x] A1 `config/quality/`：新增 `thresholds.yaml`（R3.2 比例、R4.4 置信度等）与 `filler_lexicon.yaml`（中英文空话词表）
- [x] A2 `tools/domain/models.py`：`Scorecard` 增加 `quality_report` 字段（可选，向后兼容）；新增 `TierResult`、`QualityFailure` 值对象
- [x] A3 `tools/engines/evaluation/tiered_evaluator.py`：实现 `evaluate_eligible`（R1.1–R1.3、R1.5–R1.8）规则判项
  - 依赖 `resume_trace`、已确认职业档案、PDF 页数/裁切检查
  - 测试：时间缺失卡进入正文 → R1.3 失败并指向 bullet 与卡 id
- [x] A4 `evaluate_fit` 规则部分：消费 `semantic_review` 矩阵，增加"正文呈现 / 首屏"列；R2.2、R2.4
  - 首屏切分标记 `<!-- first-screen-end -->` 加入 A/B 模板
- [x] A5 `evaluate_strong` 规则部分：R3.2（数字须回溯到卡 `results`）、R3.3、R3.4、R3.6
- [x] A6 `evaluate_distinct` 规则部分：R4.2 位置、R4.3 等级过滤（等级字段在 C1 前默认按 L1 处理）
- [x] A7 `quality_report` 组装与 `auto_pass`；`rule_evaluator` 结果写入 `legacy_scores`
- [x] A8 `tools/sidecar/handlers/agent.py`：`quality_passed` 改读 `auto_pass`；`reasons` 由 failures 生成；删除"低于参考线 78"文案；回归既有审批测试
- [x] A9 `ui/`：审批页与 Quick Run 四层折叠区、failure 跳转、`legacy_scores` 对比折叠区；GUI 合同测试
- [x] A10 同步 `sidecar-rpc.md`、`DESIGN.md`；`tsc --noEmit` 与全量回归通过
- [x] A11 真实数据只读验收：对现有最新一版目标 JD PDF 生成质量报告（不改生成），记录四层结果到台账，作为阈值校准基线
  - 结果（2026-10-18）：latest resume A `9c93df84…` / target JD PDF 2 页；合格层通过（裁切未自动校验）、对位失败 R2.2/R2.3/R2.4、优质失败 R3.2、突出失败 R4.2；auto_pass=false（7 项 LLM 判项待 Phase B），legacy 52/68、17 项 gap；证据 `outputs/acceptance/resume-quality-20261018/validation.json`

## Phase B - LLM 判项与突出点提名

- [x] B1 受控 JSON 判项通道：输入 bullet 列表 + 卡摘要 + JD 条目，输出带引用；无引用项按失败处理；缓存键 `resume_sha256 + job_profile_id + cards_fingerprint`
  - 实现：`tools/engines/evaluation/llm_judge.py`（提示词 + 受控 JSON 校验，无引用项丢弃、无 JSON 视为无效）+ `tools/infra/quality_judge_cache.py`（键 `resume_sha256 + job_profile_id + cards_fingerprint + model + prompt_version`，只缓存通过校验结果）。
- [x] B2 R1.4 角色措辞强度判定（结合 C 阶段等级；C 未完成前只检测"负责/主导"是否有 L1 支撑）
  - 实现：R1.4 强措辞 bullet 必须出现在判项中；`supported=false` 或无判项都记失败，不静默通过。
- [x] B3 R2.1 状态细化（supported/weak/absent + bullet_ref）、R3.1 三段判定、R3.5 摘要判定
  - 实现：R2.1 必须覆盖全部 JD 条目才生效（覆盖后回写矩阵状态/bullet_ref/首屏）；R3.1 逐经历 bullet 三段判定，缺失按失败；R3.5 摘要行数/角色规模匹配/通用形容词。
- [x] B4 R4.1 突出点提名：`exceeds` 四维度、top-2、理由与引用；否决写 `app-data/quality_decisions.json` 并在重算时排除
  - 实现：R4.1 提名 0–3 候选（scale/difficulty/scope/scarcity、L1/L2），排序后取 top-2；否决/替换写 `app-data/quality_decisions.json`（按 resume sha，同一候选 reject/select 互斥），重算时排除/优先。
- [x] B5 审批页突出点区：展示理由、替换、否决；GUI 合同测试
  - 实现：四层报告突出点/候选区展示理由、引用与超出维度；「否决」「设为突出点」按钮经 `quality.decideHighlight` 落盘，提示重新评测后生效；Quick Run 与固定 PDF 审批接入。
- [x] B6 真实 JD 回归：同岗位重跑验证缓存命中（目标 0 模型调用），记录判项稳定性；台账记录
  - 结果（2026-10-18）：本机 LM Studio `qwen/qwen3.6-35b-a3b`（`qwen3.8-flash-next` 加载 SIGSEGV 后换用）；首次 miss 58.0s，判项段 `r1_4/r3_1/r3_5/r4_1`，`r2_1` 仅覆盖 16/18 条目按 fail-closed 保留 pending；同输入第二次 hit **0.112s**、判项段一致，即 0 模型调用。证据 `outputs/acceptance/resume-quality-20261018/judged/validation.json`。不宣称判项稳定；R2.1 覆盖不完整仍 pending。

## Phase C - 证据可信等级与推断候选

- [x] C1 证据卡 schema：`time_range_provenance`、`role_scope_provenance`（含 level/precision/evidence/confidence/confirmed_by_user）；缺省兼容；卡指纹纳入 provenance
  - 实现：卡 YAML 新增 `time_range_provenance_json`/`role_scope_provenance_json`（字段级等级，缺省 L1/L5；结构 L1–L5 见 `tools/infra/evidence_provenance.py`），卡文件 sha256 指纹自然覆盖 provenance。
- [x] C2 `validator.py` / `store.py`：读写与校验；旧卡加载不报错；测试覆盖 L1–L5 各一例
  - 实现：EvidenceCard/引擎 store/validator 与 sidecar evidence handler 读写、校验 provenance；旧卡缺字段按 L1/L5 兼容；手工改时间/角色自动降级 L4。
- [x] C3 单文档提炼增强：`_llm_draft_prompt` 注入 `document_metadata`（路径、文件名日期、首个日期标题、修改时间、任职区间）；要求按 L1/L2 输出时间并给依据；角色仅 L1
  - 实现：`_llm_draft_prompt` 注入 `document_metadata`（路径/文件名日期/首个日期标题/修改时间/任职区间 keys），要求 L1/L2 时间候选与引用；角色仅 L1。无依据候选丢弃并记 `provenance_warnings`。
  - 测试：有文件名日期的文档 → L2 时间候选 + 依据键；无任何线索 → 留空
- [x] C4 `evidence.inferFields` RPC：kb 检索（限 20 篇、排除设计资料来源）→ 规则聚合（年月、第一人称句分类）→ LLM 一次调用 → 校验（任职区间内、excerpt 可回读）→ 写 `app-data/evidence_inference.json`
  - 实现：`tools/infra/evidence_inference.py` + RPC `evidence.inferFields`：kb 索引按标题/标签/技术栈检索（限 20 篇、排除设计资料与合成夹具）→ 日期/第一人称句聚合 → 每卡一次 LLM → 校验任职区间内且 excerpt 可回读 → 写 `app-data/evidence_inference.json`；按卡指纹+文档集合缓存，否决项不再提名。
  - 测试：候选时间超出任职区间被丢弃；excerpt 不可回读被丢弃；否决过的候选不再提名
- [x] C5 对账面板"待确认推断"列：接受 / 修改后接受（转 L4）/ 否决；批量接受高置信候选；低置信折叠
  - 实现：RPC `evidence.confirmInference`（接受/修改后接受/否决；修改后接受记 L4；写卡后进入待审核）；对账面板「待确认推断」列支持单条接受/否决、修改值、批量接受高置信候选与低置信折叠；证据页 `.pen` 同步该行。
- [x] C6 系统设置：推断开关；关闭时只显示规则 L2 线索
  - 实现：系统设置新增「证据推断」开关（`policy.local.yaml` 持久化，默认开启）；关闭时 `evidence.inferFields` 只返回规则 L2 时间线索且不调用模型；UI 同步。
- [x] C7 同步 `sidecar-rpc.md`、`DESIGN.md`、`.pen`（证据页列变更）；全量回归与 `tsc`
  - 实现：`sidecar-rpc.md`、`DESIGN.md`、`ui/design/piproofforge.pen`（证据页待确认推断行）已同步；全量回归与 `tsc` 通过。
- [ ] C8 真实数据：对 85 卡（先经用户分流）运行推断，用户在真实 App 批量确认；台账记录确认前后的缺时间/缺角色计数与接受率
  - 阻塞（2026-10-18）：真实数据需用户先在 App 证据页对缺字段卡分流为「值得补」，当前本机无 `app-data/evidence_triage.json`、用户未在真实 App 操作；本轮未运行真实 85 卡推断，不以合成夹具冒充 C8 验收。

## Phase D - 生成按等级降级与首屏重排

- [x] D1 `template_assembler.py`：按 `role_scope_provenance.level` 选动词组；按 `time_range_provenance.precision` 格式化时间；L5 时间卡不进正文
  - 实现：`tools/engines/generation/template_assembler.py` 增加字段级渲染（L1/L4 保留负责/主导；L3 动作/结果降级参与/推动；L5 时间卡不进入正文；年精度只呈现起始年），并接入真实 `tools/run_generation.py` 的 A/B 模板拼装。
- [x] D2 `llm_rewriter.py`：约束"不得提高角色强度、不得增加时间精度"；改写后规则比对动词组，违规回退模板句
  - 实现：`llm_rewriter.py` 增加 `level_context` 约束；改写后规则复核强措辞与月份精度，发现提升则回退模板原文；测试覆盖“变强/变精细被拒、合规改写通过”。
- [x] D3 首屏组织：突出点（B4）置于摘要或第一条经历；JD 前三职责对应 bullet 进入首屏；无关经历压缩规则（R2.4）
  - 实现（确定性部分）：按 JD 语义引用排序证据卡（引用优先、未引用压缩为最多 4/最少 2 条），首屏标记移到第一条经历之后，使 JD 前三条职责对应的 bullet 进入首屏。B4 突出点由评估阶段提名、生成先于评估，正文回填突出点需评估后二次生成，本轮未实现，留作后续切片（已在台账记录边界）。
- [x] D4 `resume_trace` 增加字段等级、依据与确认记录
  - 实现：生成 trace 的 claims 对时间/角色携带 `provenance`（等级、依据、确认记录），trace 顶层新增 `field_provenance`（含字段等级）；评估器读取卡 JSON provenance，R1.4 对真实卡生效。
- [ ] D5 P0-026 当前目标 JD 重新生成两页 PDF：质量报告四层结果、突出点、trace 全量记录；用户真实 App 验收
  - 阻塞（2026-10-18）：需用户在真实 App 用 P0-026 目标 JD 重新生成两页 PDF 并验收（生成/评测/固定 PDF 与用户审核）。本轮已完成 D1–D4 代码与合成夹具测试，未执行真实生成，不以合成夹具冒充 D5 验收。
- [ ] D6 路线图与台账收口：在 P0-026 下记录本变更结果；阈值按真实分布调整并写入 `config/quality/thresholds.yaml`

---

## 验收清单（整体）

- [ ] 任一目标 JD 生成后 App 展示四层质量报告，每条 failure 指向具体 bullet 或卡
- [ ] 真实 85 卡经推断 + 用户确认后缺时间 ≤ 15、缺角色 ≤ 20（以 App 实测为准；达不到时记录实际值与原因，不放宽标准）
- [ ] P0-026 目标 JD 两页 PDF：合格层全通过、JD 前三职责首屏有支撑、≥ 1 条 L1/L2 突出点，用户真实 App 验收
- [ ] 任一 L2/L3 字段在 `resume_trace` 可见等级、依据与确认记录
- [ ] 无上传/投递/平台写操作；P0-026 仍为唯一 `next`
