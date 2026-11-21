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
- [x] A11 历史只读质量报告校准：对已有成品只读评估，不改生成；保留分层失败与未完成检查的工程结论，个人输入和实际运行产物只留本地。
  - 既有报告未通过全部质量层，裁切及后续模型判项仍有未完成项；历史校准记录不替代当前真实 App、Splash 或 D5 验收。

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
- [x] B6 历史缓存回归：同输入重复评测可复用缓存，保留判项覆盖不足时的失败边界。
  - 既有记录显示缓存命中可避免重复模型调用；要求覆盖不完整仍保持 pending，不把缓存命中解释为判项稳定、质量通过或真实 App 验收。个人输入与实际运行产物只留本地。

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
- [ ] C8 真实数据：对经授权并在 App 分流的样本运行推断，由用户在真实 App 核定；记录确认前后的缺字段变化、接受率与剩余原因，具体个人资料只留本地。
  - 未完成：仍需对应真实 App 操作证据，合成夹具和离线回归不能替代 C8 验收。

## Phase D - 生成按等级降级与首屏重排

- [x] D1 `template_assembler.py`：呈现字段来源等级并保留已采纳职责；按 `time_range_provenance.precision` 格式化时间；L5 时间卡不进正文
  - 实现：真实 `tools/run_generation.py` A/B 模板已消费字段 provenance。2026-10-20 用户修订后，L3 职责和行动保留主导/负责人及明确的参与/协助限定，不按来源等级机械降级；时间规则与 trace 保持。
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

### P0-026 行动/成果状态投影（结果按 I 限定开放，行动正向仍未开放）

- 首片：已有证据的复审可显式采纳或撤销一项行动/成果范围；通用草稿或引文自带状态字段不授予权威。复用已审核事实快照与证据详情投影，不改简历渲染或投递门禁。
- [x] 既有复审已明确采纳“具体事实 + 现行原文引用 + 主体/动作/对象/环境 + 实现和发布状态”。没有可验证的生产者不接生成；不新增事实库、不靠旧数据回填，也不以语义或字词匹配自动确认。实现边界以核心 Pipeline 中“行动与结果的范围”为准。
- 复审显式核对逐事实关系：本人执行、团队牵头、参与协作、同事负责、未知。默认未知且不从整卡角色或原文关键词继承；执行/协作关系与实现、发布分开记录，团队牵头不等于独立实现。同一事实/对象/环境的本人执行与同事负责互相争议时保留各来源，不显示确定归属或更强状态；不把其他事实或牵头/协作自动算作争议。同一动作的旧自由文字不被解释成关系，不补写旧记录；未重新核对的范围仍禁止继承整卡角色。
- 个人正文防误归属：确定性生成事实池和内部定向事实片段不得将已核范围事实挂在整卡角色下。在尚无可判定的逐事实本人归属时，该事实保留在原证据与审计，不进入个人正文；非范围兄弟事实不受影响。主体自由文本不是可判定的归属，尚不解锁任何实现/上线正向表述。独立 Agent 自由改写不在本片。
- 首片即使核定本人执行且已实现，也未直接将证据原文或自由填写的对象写入正文：来源定位不能保证句子未夹带生产上线、独自负责等更强主张。I 仅按下述独立核定开放完整 results，actions scope 约束保持。
- 首片隔离诊断：9 个合成用例中，文本筛选误挡一个「尚未」修饰对象的正确句；现有结构校验可接受人工标注且引文可定位的 9 条支持结论，不等于语义成立。候选句专用输出解析通过 14 个异常负控；本机 Splash 首次请求在 20 秒超时，当时未再请求、未获得可验证结果、未接入产品；I 的后续实际应用验证另行记录。D5 真实 App/PDF 验收仍待完成。
- [ ] 独立验收矩阵：① 已实现重启后续跑尚未落库对象 → 实现可证、发布未知；② 同一动作仅计划或明确尚未实现 → 不形成已实现成果；③ 已实现且明确未上线 → 可呈现实现而非上线；④ 测试环境已完成验证 → 保留测试环境，生产未知除非另有明确证据；⑤ 本人主管总体且实现一条链路、某页由同事负责、另一任务仍在计划 → 三类范围不相互继承；⑥ 同主体/动作/对象/环境互斥断言 → 保留两侧依据、不升级，不同环境不视为同一冲突。
- [ ] **正向正文措辞实验（提案，未接受）**：按 [既有设计 §4.3.1](design.md#431-逐事实正文与结果证据边界p0-026) 的六项固定判据，用同卡独立本人/同事/复合超范围源文经现有复审和正式、内部消费者做最小隔离验证；无法对完整措辞建立来源与范围约束则不实施。此项不替代 D5。
- [ ] 负控须用真实来源校验覆盖：重复字段文字但无法定位具体位置、修改来源修订、未绑定导入建议，以及在普通引用字典中伪造额外状态字段都不能给正式计划或内部预览增加已核状态。无新投递行为。

- [x] R3.2 同文异事实借证修复：`901805a` 仅以真实渲染且 trace 校验的 `results` 计分；`a142c5e` 拒绝缺少精确来源版本、Fact ID 或错误索引的量化加分。包含正式 Markdown 选材/渲染/追溯/量化的离线正反例；不称为真实 JD 或投递验收。
- [x] 结果是否实测的独立纯函数诊断：同卡相同 P95 数字的实测/预测/目标/模拟假设，即使各有精确结果 Fact ID 也均得 R3.2=1.0；另在 `validate_field_sources` 的纯函数对照中，来源文档里的预测/实测两条含同数字引文都可绑定被剪去限定词的卡片结果，故单靠字段引文不足以证明完整已测陈述；未测试这四例的 App 端到端，也未解除任何投递门禁。复现证据及实施验收仍在 [现有设计 §4.3.1](design.md#431-逐事实正文与结果证据边界p0-026)。
- [x] **实测真实性规范与归属对齐**：完整命题、现行原文/修订、测量条件及发生性核定归属现有证据复审；R3.1/R3.2 共同消费核定，预测/目标/假设不得冒充实测，非量化完成成果保留。见 `evidence-provenance` R5 与 `resume-quality` 实施状态；未新增表示字段，未宣称完整实现。
- [x] `2376fc5` 失效 trace 撤权：非语义评测的规则、judge 与四层报告使用一致来源有效性；三种输入/正文版本变化负控及有效正控通过。
- [x] `7881ebf` 逐事实引文唯一性：同文档重复片段不授予状态，跨文档同文允许各自唯一定位；保存失败不部分写入，普通复审不能洗掉旧范围，显式恢复保留兄弟事实。GUI 完成歧义提示和显式撤销的组件行为验证，未完成原生窗口深验。
- [x] **退役独立批量 CLI 业务路径**：删除 `extract-batch` 的独立写卡、修复、批准及计划词表分流；复用 App 的材料导入/引用、精确文档提炼和既有复审保存。只读入池检查归现有 `infra/evidence_pool`，两个原消费者语义不变。先红测证明旧入口可越过复审写入批准，再验证入口移除与 App 正反链；不新增 API、队列或业务实体，自动聚类/断点批量调度仍未实现，Quick Run 的 pipeline 进程隔离保留。
- [x] **切片 F：产品生成与来源 trace 收敛（限定工程范围已完成）**：共同 FactIndex/plan/正文/trace、选中 ID、当前源、原位置/值、实际行和快照字节均已验收，旧自由改写产品策略已移除。有效来源等级规范经反例补齐：正式/guided 选材前排除无时间/L5 时间卡，L2 按获证年/月且日精度封顶月、L3 仅年、L1/L4 保留原精度；含中文空白日期及真实降精度 trace 正控，L5 角色省略但合法动作/结果保留，已采纳 L3 主导与限定保留，trace 可见等级/依据/确认。最终全量 `2561 passed、1 skipped、84 subtests passed`（39.62 秒），工程门禁通过；不影响 Jobs 内部片段或全局 FactIndex。F 不代表间接依赖、全部选材规范、R5 实测、Agent 四层 R3.2 或真实验收完成。
- [x] **切片 G：职业档案关联材料依赖捕获（限定工程范围已完成）**：既有职业档案读取捕获实际关联卡及材料路径/SHA，正式生成与 Agent 共同消费同一 trace。声明字段来源却缺材料指纹、生成前/中变化及同键来源/版本冲突拒绝，生成后变化撤权；同 SHA 副本不替代实际路径，同一实际路径别名、无关材料变化和空 career 正控保留。档案贡献仍为 personal_profile，项目选材及公有 JSON 不变。最终全量 `2577 passed、1 skipped、84 subtests passed`（40.35 秒），架构检查通过；不新增接口/账本，不实现四项选材、R5、Agent 四层评分或真实验收。
- [x] **切片 H：评测消费输入版本绑定（限定工程范围已完成）**：规则、judge 与四层消费同批已核卡/档案/岗位输入；直接卡不会被同 ID 的 career_evidence 覆盖，语义 loader 返回对象须与 trace 绑定的实际 JSON 一致。中途读入新值后恢复原文件仍拒绝，发布前失效不覆盖既有报告；有效正控及初始无效非语义 trace 的既有未验证报告保留。新增 14 个测试案例（计入参数化展开），记录 10 个业务 RED，定向 `105 passed`（1.27 秒）；最终全量 `2591 passed、1 skipped、84 subtests passed`（39.23 秒），架构 v2 约束检查通过。复用现有职责，不新增实体、字段或报告，不改变实测语义或 Agent 四层接入状态。
- [x] **切片 M1：guided Agent 四层报告与固定审核消费（限定工程与合成应用验收完成）**：复用同版来源读取、RuleEvaluationEngine/Scorecard、共同四层与现固定质量快照/API/QualityReportPanel；正文 SHA/目标/实际 PDF 与报告成套校验，来源 ABA、同文未采用结果无信用、缺语义不判无关、跨队列未核报告和失败候选原子性均已验。补本轮显式目标而不伪造线索审批，高旧分不覆盖 pending，分析不增人工批准门禁。最终全量 3016 passed、1 skipped、101 subtests passed（58.93 秒）。最终合成 App 9 RPC、实际 PDF、零模型/应用网络请求，报告篡改拒绝，合法待判质量批准只得到 checked_not_submitted。无新实体、RPC、账本或业务脚本；模型 Agent 语义、原生和真实验收另行推进，详见台账。
- [x] **共享选材契约（K1/K2/K3/K4 限定工程已完成）**：沿 core“目标版本内容取舍”与既有共同选材职责补齐精确引用、预算、摘要、完整补充成果、背景来源与有界语义去重；不因删除旧辅助实现而宣称规范已迁移，不新增持久账本、业务脚本或词表规则。有限合成验收不代表全部语义边界或真实简历验收。
- [x] **K1 精确引用增量与正文预算（限定工程已完成）**：复用已校验 semantic_report/checks/citations、`positive_citations` 与 `_requirement_map`；精确 Fact 为新增进展单位，每候选每父要求取 max(supported=2、partial=1)，不累计重复子项，不以全局 seen_parent/seen_check 或完成检查数丢掉互补引用。移除项目卡数 bonus、整卡 preferred 权重 3 的语义权威和死 card_rank；退役仅由共同 selector/builder 使用的 score_fact/VariantWeights 词表加权，不保留第二选材路径。
- [x] K1 选材/正文责任：语义代表项目最多三项，每项目三条行动、两条成果；selector 决定预算内有序事实，plan 不量化优先再截断真实引用；既有 R2.2 只在已选同组内前置，不改变集合、预算身份或结构出处。同文去重不向未采用的来源授信。正式共同 builder 消费细粒度报告；guided 无该报告沿显式输入稳定顺序和同一结构预算，不得伪造要求支持或 A/B 差异；内部 preview 仍为只读引用片段，不接全量选材/职业档案扩展。
- [x] K1 独立验收：重复父/子引用不抬权、同父不同子和同子多 Fact 互补、父子 partial 限制、预算与稳定顺序、引用非量化不被未引用实测挤出，以及 guided/内部片段边界。以最终正文、rendered claims 与 resume_assessment 核对覆盖/缺口，不能仅断言 Plan.fact_ids；7 个独立业务 RED 已转绿，包括首屏展示不替换预算集合；K1/L1 最终全量 `2696 passed、1 skipped、101 subtests passed`（42.28 秒），架构 v2、TypeScript 通过。两页合成 PDF 的页数、首屏/尾页文字位置、边界及 trace 通过，未宣称全页像素或真人视觉验收。
- [x] **K4a 完整场景呈现（限定工程完成）**：沿现共同 builder/ResumePlan/render_plan 删除固定 120 字背景裁剪及误用成果词表的整段过滤，完整保留尾部条件与已选成果 bullet、实际 claims/trace；保持预算、内部片段及原评分边界，不新增字段/任务/脚本，不将背景 presentation 冒称已具精确 occurrence。3 个业务 RED 转绿，定向 99 passed、来源生命周期/合成 Quick Run/PDF 107 passed，架构 v2 通过；0 模型请求，未重跑全量，完整语义去重仍 pending。
- [x] **K4b1 背景精确来源（限定工程完成）**：复用原 block/plan fact_ids 登记实际 context，renderer 按明确绑定输出原来源与真实行，不借代表卡/同文。独立验收长背景精确覆盖、合并来源、同文不同身份及背景剪限定而全文仍在成果处的标准 trace 反例；非法绑定拒绝，preview 范围说明保原职责，不增字段/对象或模型调用。两组共 13 个业务 RED 转绿，独立 30/17 项通过；最终全量 2946 passed、1 skipped、101 subtests passed（54.83 秒），架构 v2 通过；合成 PDF 与原范围正控保持，K4b2 仍 pending。
- [x] **K4b2 场景语义去重（限定工程与有限合成应用验收完成）**：实际选材后、渲染前以现 TaskRunner 判断同项目完整正文是否已表达背景全部实质信息；只省未被精确岗位正引的冗余背景，完整结果、claims/真实行和来源不动。未知/不可用保全文，严格批次/索引/重复 JSON 键、完整请求预算及来源变化边界已验；原 API 说明实际决定，不增门禁或平行账本。最终全量 2973 passed、1 skipped、101 subtests passed（55.62 秒）。三个合成应用流共 82 RPC/20 次本机 Splash HTTP：首轮问句硬 keep 判据不足的原 2/3 记录保留，随后独有条件保留/完整重复省略的 A/B 对照通过；整体质量仍未通过。Agent 四层与真实验收继续推进，详见台账。
- [x] **K3 精确引用补充成果（限定工程完成）**：完整名称/说明/非空 URL 条目与项目精确正引用同阶段竞争可选预算，最多两项、整条成本、每父 max2/1、稳定同分；保全部限定和真实 claims，预算不足整条缺席。profile_highlights 已有唯一 plan 消费者，原数组前两项/二裁/补字段与死 excluded 退役。独立首轮 `16 failed / 7 passed`，原 16 个业务 RED 修复后连同原正控及后补 3 项控制得到 `26 passed`；新增控制不计作原 RED。相关七文件 `150 passed`，最终全量 `2720 passed、1 skipped、101 subtests passed`（45.54 秒），架构 v2 通过；未改两页合成 PDF 夹具，原页面、首屏/尾页内容、边界与 trace 断言继续通过。实际档案确认/加载、共同正文、逐字段 claims、resume_assessment、guided trace、档案 SHA 和底稿字节均已核验；没有调用模型，不替代真实 JD、正式件、原生或全页像素验收。
- [x] **K2 职业概述（限定工程完成）**：显式摘要、各 current 职责与原首贡献按任职身份完整呈现，无 current 保留显式摘要或实际历史期间；summary_fact_ids 唯一驱动，删除文本副本/无源 fallback，同 Fact 从工作移到摘要，其他同文身份不借证。独立 5 个合成变体先得到 4 failed / 1 passed，原四个业务 RED 修复后同组 5 passed；实际 profile.update→review→加载→共同 builder、正文行/claims、resume_assessment、guided trace 和档案 SHA/原字节均已验证。定向 107 passed；最终全量 `2701 passed、1 skipped、101 subtests passed`（42.41 秒），架构 v2 通过。未改合成 PDF 夹具，原两页 A4、首屏/末页完整文字、边界与 trace 验收继续通过；未宣称全页像素、原生窗口或真实简历验收。 R3.5 阈值与未判状态不变，无新增模型任务。
- [x] **切片 I：完整结果命题核定与共同消费（限定工程范围已完成）**：沿既有 saveDraft 的 results scope 采纳，在 binding/CAS 后由独立语义核验给同一 fact_scope_v1 行附 outcome/measurement_quote/rationale。完整 value 判定、同次完整实测命题锚定、非量化及失败原子性按 R5/设计 §4.3.1 验收；客户端不可写核定，来源/卡变化和核验不可用不部分保存。
- [x] I 共同消费：唯一当前投影接正式正文、内部片段、Fact.has_quant、selector/plan 与 R3.1/R3.2；移除这些结果消费者的数字/影响词表资格，judge result=true 不补权。旧 actions scope 保持；同事归属、明确同 scope 冲突与跨环境强断言负控已验，unknown/无核定/撤销不恢复旧信用；别名跨来源冲突缺口见下项。
- [x] I 复审回显与生命周期：原 panel 在 sources 内只读显示 outcome、完整实测 quote 或无已核定量化、rationale/source，区分未核与 unknown；无新增勾选。待审暂停消费但保留记录；仅标题变、原来源/事实/scope 不变可保留核定再审。组件行为已验，rationale 文案清晰度与原生 UI 未宣称验收。
- [x] I 限定工程验收：业务 RED 覆盖既定生产/消费/失效边界；纯合成材料经真实 Router 上传/saveDraft/get→本机 Splash→两路实际正文消费者→评分。首轮 6/7 后修正通用模态定义，相同七项以七个真实 localhost 请求复验 7/7；不加样例词表，交付伴预测保留正文但量化为 0。最终全量 `2636 passed、1 skipped、84 subtests passed`（41.32 秒），架构 v2、TypeScript 检查通过；原 PDF 文件 `3 passed`，保留物理两页与 trace 断言。不是孤立跑分、完整 preview RPC 或 deep_verified，不替代真实 JD/正式件/投递验收。
- [x] **切片 J：同 Fact 跨来源核验与依据（限定工程范围已完成）**：在原 result_review 增 server-only basis_sha256，绑定协议域、Fact 身份、全部当前同 Fact 精确来源绑定（含未 adopt）及 scope 原声明；全文按现有 SHA 读取，不持久复制集合，不按 target 字面筛 peer。
- [x] J 批核与原子保存：现有 results scope 采纳一次 HTTP 核全部同 Fact 现行行，返回索引一一对应，每行主来源独立支持完整句/自身 quote，他源只作语境和反证；全部成功并重验卡 CAS/来源后原子写，不逐行补点或逐 JD 重核。
- [x] J 当前投影与详情：实际已核输入重算 basis，旧 I 缺依据/失配/新增绑定未复核均不授信用且详情未核，不读时补写；已有 J 依据不变时标题往返保留。退役结果 target/状态集合的语义 veto，保留 actions 原归属/使用约束。matching 只限制既有 scoped results 的个人正证，未 scope 行为不变；false 不证明纯他人/不具备/冲突，仅 false 引用的 conflict 降 insufficient 并保留审计，独立可用真反证仍可成立。当前有效个人完整句保正用，不加字段或词形规则。
- [x] J 独立验收（限定工程范围）：先复现未 adopt 反证与旧行借信，再保住早期预测→后期实测、本人 A/同事 B、不同 Fact 非依赖、标题往返正控；分开完整叙述与当前 scope 量化归属，验证对接保留但不借同事量化，以及有证团队主导/共同成果、上下文隐含主语正控；覆盖别名真实冲突、旧 I 不升级、仅 false 引用的伪 conflict、独立可用真反证、未 scope 匹配正控、按既有 VERSION 拒用内容/输入自洽的旧 v6 正式报告、批索引异常/单项失败及模型期间卡源变动不部分写。纯合成实际应用链首轮 11/12、15 次 localhost 请求暴露本人行借用同事量化；保留失败审计并澄清通用量化责任关系，原 12 场景加 team_lead/contributor 正控复验 14/14、18 次请求通过。原失败完整正文保留且 R3.2=0，时间推进/主导/参与正控为 0.5，全部 trace 有效且 auto_pass=false。最终全量 `2679 passed、1 skipped、94 subtests passed`（48.60 秒），架构 v2、TypeScript 通过。J 验收时，rationale 清晰度、原生 UI、完整预览 RPC、真实 JD/正式件/投递尚未验；四项选材和 Agent 四层当时保持 pending，I 的结果不重复计入 J。后续进展分别见 K1/L1。
- [x] **L1 共享结构合同与完整合成准备预览 RPC（限定工程范围）**：原 LLMClient 为 JSON-object 请求传递调用方完整 schema，保留原生/显式格式与无 schema 行为，不改业务响应、不放宽校验。7 个实际 Request.data RED 转绿；同一合成流程从偏好字段协议失败复验到 28 个真实 Router RPC、6 次本机 Splash 请求完成，4 父要求 supported、5 checks 完成；有限范围预览 input_fresh=true、partial=true、send_ready=false、deliverable=false，3 个正文事实且预览自身 0 模型请求。来源搜索/详情仅协议夹具，真实站点与投递 0；不是正式件或原生 UI 验收。
- [x] **L2 完整请求预算与缓存身份（限定工程范围）**：原 client 准备同一 Request，matching 分批/任务执行器/缓存/发送共同消费；初次与修复均计入 context/schema/provider 参数，不调上限、不剪完整事实，本地准备失败明确拒绝且不饿死其余 checks。原 10 个业务 RED 及另补局部失败 RED 转绿，最终全量 2734 passed、1 skipped、101 subtests passed（42.95 秒）；同一合成真实应用流程 28 RPC、6 Splash 请求通过，matching 实际 4718/5814 字符，预览仍不可投递。详见 Project Ledger；其他直接调用尚不宣称已有契约预算。
- [x] **L3a 业务层协议归属（限定工程范围）**：删除 evidence inference 与 quality judge 重复 URL/provider 参数注入，6 个独立 RED 与 4 个正控全部转绿；全量 2744 passed、1 skipped、101 subtests passed（46.20 秒）。限定合成 inferFields 经 8 RPC、1 次本机 Splash 返回两个有出处候选，卡字节未改且不可入池；索引由既有 builder 非 RPC 初始化，质量真实 Splash 链未补验，详情见 Project Ledger。
- [x] **L3b 配置与共享客户端协议（限定工程范围）**：现字段统一默认/关闭/开启、PATCH 与环境优先级，接通直接调用、结果复审、有界 preparation、Quick Run 和设置页面；退役部署地址/模型名称及 JSON 强制关闭分支，无新增账本/字段。客户端、后端、真实浏览器独立 RED 均转绿；最终全量 2819 passed、1 skipped、101 subtests passed（53.02 秒），架构 v2 通过。同一合成应用程序完成 28 RPC、6 次 Splash，明确关闭实际逐请求生效，内部预览仍有限且不可投递；其他模式/provider 仅 wire 验证，详情见 Project Ledger。
- [x] **L4 推断输入准备与当前来源（限定工程范围）**：现 inferFields 自行准备索引，完整材料/文档/原文版本贯穿读取、解析与缓存；已采用档案单次解析，全批候选发布前复核来源、现行许可与状态版本。独立正反例覆盖无索引/恢复、同文异材料、启停、未刷新来源、模型期间变更、跨卡失效、真实否决及空指纹准入；最终全量 2874 passed、1 skipped、101 subtests passed（50.74 秒），架构 v2 通过。原合成应用移除 bootstrap 后完成 8 RPC、1 次本机 Splash，由 API 创建索引并返回两条有出处候选，原卡未改且未确认；规范见 R4.5，详情见 Project Ledger。无新增字段、接口或业务脚本。
- [x] **L5 推断候选确认（限定工程范围完成）**：沿 R4.6 复用 candidate_hash、原 state/input_basis 与唯一 card_sha 游标，原 attempt 校整份依据；接受复核实际原集合、版本/许可，保住已用档案与同卡两顺序正控，改值 L4 撤余、关闭与否决分责。来源/身份/并发/部分持久化及真实 Chrome 反例转绿，全量 2928 passed、1 skipped、101 subtests passed（55.48 秒），架构 v2通过。实际合成应用 10 RPC、1次 Splash：错误时间引文被丢弃，随后仅确认有效职责，仍 pending/不可入池；原两字段真实模型预期未达，失败证据保留、不重调模型，详情见 Project Ledger。无业务脚本/新RPC/平行账本，不宣称跨文件事务、原生深验、正式件或投递完成。
- [x] 既有事实扩大引文接入来源复审 GUI：保持事实位置、文字和同一来源版本，多行引文不拆为新事实；已有范围由原显式采纳/撤销维护，无目标范围的引用补全可普通保存。实际主页面转发范围指令，普通保存与不完整/待审核状态往返不能清除既有约束；组件、真实草稿操作到保存处理器的合成跨边界验证通过，未完成原生页面深验。
- [x] 保存状态与事实约束分离：不完整/待审核阶段不授予范围权威；当前精确事实与来源未改时复审保留原范围，改引文或事实不能通过普通保存洗掉旧记录。复用同一审核快照，没有新增状态字段或账本。
- [x] 完整事实数组往返：统一现有创建/编辑/草稿/复审/读取 API 的 `actions/results` 有序数组，修复换行拆项及序列化丢失；逐项 UI、来源与范围绑定、正文和内部片段复用原事实身份。拒绝非法类型/空白项，不增加影子字段或兼容支路；结构保真不作为实测语义核定完成。

## 验收清单（整体）

- [ ] 任一目标 JD 生成后 App 展示四层质量报告，每条 failure 指向具体 bullet 或卡
- [ ] 授权真实样本经推断和用户确认后达到本机验收任务约定的缺字段目标；记录实际值与原因，不为测试通过放宽标准
- [ ] P0-026 目标 JD 两页 PDF：合格层全通过、JD 前三职责首屏有支撑、≥ 1 条 L1/L2 突出点，用户真实 App 验收
- [ ] 任一 L2/L3 字段在 `resume_trace` 可见等级、依据与确认记录
- [ ] 无上传/投递/平台写操作；P0-026 仍为唯一 `next`
