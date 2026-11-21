# Project Ledger

Last updated: 2026-11-22

本台账记录应用实现、工程验证和未完成边界。个人履历、原始职业材料、真实岗位候选、投递记录及其运行产物留在本地数据区，不作为应用仓库资产。应用示例和设计稿中的候选人、公司、材料及成果均使用明确的合成数据。

## 2026-11-21 应用资产发布边界整理

- 应用资产链从已核实的远端基线 `f568034` 建立。阶段 A 的 11 个逻辑提交截止 `5fd056d`；阶段 B 的独立打包改动为 `9887399`。原本地 `develop` 的 `0bb14ab` 及其 148 个未推送提交未并入新链，原工作区和完整历史保留。
- 应用树移除真实职业资料、运行数据与个人职业审计，保留源码、测试、工程规范、设计、构建配置与明确合成示例。知识索引取消私人材料白名单及其事实权威，继续使用具体来源绑定、原文指纹和既有相关性召回。
- 阶段 B 的资源配置与准备流程仅携带应用代码和依赖，不携带运行数据或演示输入。源码合成样例保留供显式 CLI 演示，空库由既有 sidecar 承接；隔离回归覆盖旧资源清理、样例同名私人数据排除及资源根、父目录和叶目录链接边界。
- 最终阶段 A 快照 `5fd056d`：全量 `2466 passed、1 skipped、59 subtests passed`。最终阶段 B 代码快照 `9887399`：全量 `2472 passed、1 skipped、59 subtests passed`；架构、路线图、AIEF、TypeScript 与补丁格式检查通过。这些结果来自重建后的实际快照。
- 阶段 A/B 均已正常快进推送到远端 `develop`，完成时回读到 `56ce9af`；未推送原本地私人历史。资源准备与空库行为的隔离回归不等于安装包构建；本次未做 CI、原生页面、真实 JD + Splash、正式简历或实际投递验收，也未清除远端既有历史中的个人资料。

## 2026-11-21 引文复审接通与范围约束保留

- 既有 actions/results 的引文扩充保留 field/index/value、当前材料/文档/SHA 和其它来源绑定。新引文完整包含旧引文、多行条件不拆成新事实；唯一定位仅证明引用位置，不证明实测。
- 目标已有范围时，通过原显式采纳/撤销维护；目标原本只有来源引用时，可普通复审保存扩充引文，不因此新增归属、环境或实施结论。主页面此前漏传范围指令，现已接通原保存入口。
- 复现并修复普通“不完整”保存清除范围、仅改标题进入待审核后普通复审丢范围的问题。现有快照在所有保存模式中维护约束；未批准使用时不投影权威，精确事实及原文版本未变的重新审核保留旧范围，已有范围绑定的事实或引用改变时必须显式修复。
- 五个合成跨边界场景调用真实 TypeScript 草稿操作并交给现有保存处理器：覆盖仅补来源、含糊旧范围显式重采纳、陈旧卡指纹、实际来源变更和绑定/采纳引文不一致。拒绝场景卡文件不变，成功场景保持多行引文、原 Fact ID 与合法兄弟范围。
- 最终全量验证：2494 passed、1 skipped、59 subtests passed；其中两份 GUI 行为测试 21 passed、来源复审处理器测试 52 passed（包含上述五个跨边界场景）。架构、路线图、AIEF、TypeScript、补丁格式和设计文件 JSON 检查通过；保存状态、主页面指令与原文读取回归均保留先失败再修复的证据。
- 本切片未调用模型、未访问招聘站、未生成正式投递件；组件和处理器验证不能替代原生页面验收。完整命题、测量发生性及正文/评分共享核定仍未完成。
- 阶段 C 的三个分组提交已正常快进推送并回读为 `bffc71ad`，应用发布链合计 16 个提交。规范中的个人材料统计与历史授权记录已在新提交内通用化；原私人提交链未并入，远端既有历史未重写。

## 2026-11-21 产品 API 与完整事实项往返

- 项目宪法新增产品化约束：业务由现有领域模块、应用用例和 API 承责，案例用于检验通用契约，不设私人身份、样例数字或模型措辞特判。业务脚本中的有效能力须归回应用并删除重复路径；测试、构建和开发检查仅承担工程职责。
- 现有创建、详情、编辑、提炼草稿及复审保存统一使用 `actions/results: string[]`。界面逐项编辑、显式增删；保存及回读保留单项换行、文字、顺序和重复值，非法类型或空白项拒绝且不写入，空数组沿原不完整保存规则处理。没有影子原值、额外事实实体或字符串写入兼容支路。
- 既有序列化改用标准字符串编码，修复换行及看似 YAML 结构的事实文字被解析成新项或字段的问题；仅改标题不再破坏事实位置。现有来源读取校验同时供复审保存和普通编辑使用，完整结果必须来自一个授权原文单元，不能跨两个文档的拼接边界借证。
- 合成链通过实际 API 保存/读取以及正式 Markdown、内部预览消费者，确认完整条件与原 Fact ID 保留；范围往返和合法兄弟事实继续有效。GUI 同时验证逐项编辑、原始数组字节、标量原有归一化契约、完整来源引文和陈旧操作拒绝。
- 最终全量回归：`2519 passed、1 skipped、84 subtests passed`（38.77 秒）；受影响 GUI 36 项通过。架构、路线图、AIEF、TypeScript、补丁格式及设计 JSON 检查通过。原生页面与设计稿视觉渲染未验收，本片没有调用模型、访问招聘站或生成正式投递件。
- 阶段 D 的规范提交 `7dcdf0d` 与实现提交 `11415332` 已正常快进推送；远端与本地 `develop` 回读一致，应用链合计 18 个提交。28 个功能文件与全量验证快照逐项一致；原私有归档及其历史未并入，既有远端历史未重写。
- 本片验收时已定位的后续边界为批量 CLI 独立批准、写卡及计划词表分流，随后按下一节退役；完整命题的语义核定和正文/R3.2 共享消费仍未完成，结构保真不等于实测真实性。

## 2026-11-21 退役独立批量提炼业务

- 先用真实 CLI 入口和隔离合成材料复现：旧批量批准命令把待审卡直接写成 approved/eligible，卡文件字节快照负控失败。修复后旧命令拒绝且材料、卡与进度文件均不变；两个旧模块实际删除，模块解析也不再可达。
- 删除独立批量写卡、修复、批准和仅该命令消费的目录统计卡、计划词表分流等实现；没有转发入口、兼容路径、新 API 或新队列。仍被 Jobs 与岗位语义准备使用的完整性预检查归回现有 evidence_pool，两个读消费者与原候选池状态口径保持。
- 复用既有 App 目录材料/精确文档 → 未批准草稿 → 显式复审保存的正控，并保留来源变化、伪造结果和跨文档借证的拒绝边界。公共检查只读完整性，不授予批准或实测资格。
- 工程验收：受影响七份测试 128 passed；最终全量为 `2498 passed、1 skipped、84 subtests passed`（41.72 秒）。架构、路线图、AIEF 与差异检查通过。保留并迁移公共检查测试，删除 22 项仅服务已退役实现的测试，新增 1 项真实入口负控，因此相对上一片净减少 21 项；没有通过删掉应用反例来制造通过。
- 本次修改的规范与命令文档继续移除继承的具体真实成品指纹、运行批次路径和投递示例标识，保留工程结论及未验收边界；未重写已发布历史，未处理本地个人业务数据。
- 自动遍历聚类、断点续跑与批量调度尚未由 App 承接，明确保留能力缺口。完整命题和测量发生性核定仍未完成；本次无真实模型、原生页面、真实 JD、正式简历或投递验收。

## 2026-11-21 产品生成与来源 trace 收敛（切片 F，限定工程范围已完成）

- 修复前核实活 API guided batch 的 domain card 转换丢失 actions、角色、当前来源与逐事实约束，随后进入旧模板 renderer；模型自由改写也消费该旧基线。该入口固定 dry run、零外部投递，此缺陷不是已发生的投递门禁绕过。
- 先在既有 core、Agent 设计、RPC 合同和质量设计中固定独立期望。工程验收覆盖完整事实正控、原事实位置/值与实际正文行、范围排除与兄弟事实、未选卡隔离及选中 ID 归属、来源变化和失效 trace；快照发布前同时绑定实际正文/trace 字节，导出期间变化不能发布有效快照。
- 已共用正式 FactIndex/plan/正文/trace，按选中 ID 读取当前源，移除旧自由正文改写产品策略。ResumeOutput 传递同一 generation_trace，由规则评价与审核快照实际核验消费，不新增平行事实账本。CLI 回归显式传入临时合成 evidence/profile/job，不依赖仓库业务数据。
- 消费者复核发现时间精度、无时间/L5 时间正文准入、L5 角色省略和 provenance trace 的有效产品负控遗漏后，恢复这些规范并补独立正反例。最终全量 `2561 passed、1 skipped、84 subtests passed`（39.62 秒），工程门禁通过；这是限定范围的离线验收，未进行真实 Splash、正式简历或实际投递验收。
- 规范核对确认 2026-10-20 仅修订 L3 职责机械降级，时间及追溯合同仍有效。正式/guided 选材前排除无时间/L5 时间卡；L2 按获证年/月且日精度封顶月，L3 仅年，L1/L4 保留日精度；中文空白日期及真实降精度后的 trace 正控已验。L5 角色省略且合法动作/结果保留，已采纳 L3 主导及限定保留，trace 显示等级、依据与确认记录。修复未扩大到 Jobs 内部片段或全局 FactIndex，F 按此限定工程范围完成。
- F 验收范围为直接采用卡与实际 profile/JD 文件。职业档案关联材料的间接来源捕获由 G 接续；来源依赖不等于项目选材，既有档案贡献不因未选其关联项目卡而被删除。
- 另列共享选材契约的四项 pending：父要求新增覆盖、摘要当前职责与首条代表贡献、按引用选择个人补充成果、同项目完整成果的正文去重及独立 claims。旧辅助选材逻辑未形成生产消费，不能将其删除视作契约等价迁移；这些缺口与 G 分开，F 不宣称全部产品规范完成。
- P0-026 仍在进行，R5 的完整结果命题及实测发生性核定尚未实现，Agent 规则评价未接入四层 R3.2；外部授权边界不变。

## 2026-11-21 职业档案关联来源捕获（切片 G，限定工程范围已完成）

- 修复前合成复现为 `6 failed、1 passed`：B 的职业贡献在正文且归 personal_profile，直接项目仅 A，但 trace 漏掉 B 材料；声明字段来源却缺材料指纹、生成前/中材料变化未拒绝，生成后变化未撤权，同 SHA 副本可能使 trace 绑定另一卡路径。无关材料变化及空 career 的原正控保持。
- 已由现有职业档案读取捕获实际关联卡及材料路径/SHA，正式生成与 Agent 共同消费同一 trace。声明字段来源却缺材料指纹、生成前/中变化和同键来源/版本冲突拒绝，生成后变化撤权；同 SHA 副本不替代实际路径，同一实际路径的别名正控保留。公有 JSON、项目 Fact/claims 及已有档案贡献选择不变，未新增接口或账本。
- G 净增 16 项测试，受影响定向验证 `142 passed`（2.47 秒）；最终全量 `2577 passed、1 skipped、84 subtests passed`（40.35 秒），架构 v2 约束检查通过。结果仅证明实际 career 关联来源捕获与失效边界；四项选材、R5 实测、Agent 四层评分及真实 Splash/正式件/投递验收仍未完成。

## 2026-11-21 评测消费输入版本绑定（切片 H，限定工程范围已完成）

- 卡、档案、岗位的实际解析字节与 trace 路径/SHA 绑定，规则、judge 与四层复用同批已核输入；职业档案内部关联来源也核对实际捕获版本。同 ID 的 career_evidence 不覆盖直接项目卡，原量化 1.0 正控保持。
- 既有 semantic loader 继续校验 schema/content/inputs，返回对象另与 trace 绑定的实际 JSON 核对；中途读入新值后恢复原文件仍拒绝。评测期间来源失效不发布或覆盖既有 Markdown/JSON 报告；初始无效非语义 trace 继续产出未验证报告。
- 新增 14 个测试案例（计入参数化展开），记录 10 个业务 RED；定向 `105 passed`（1.27 秒），最终全量 `2591 passed、1 skipped、84 subtests passed`（39.23 秒），架构 v2 约束检查通过，独立审查无阻塞。不新增实体、字段或报告，不完成 R5 实测、Agent 四层接入或真实验收。

## 2026-11-21 完整结果核定与共同消费（切片 I，限定工程范围已完成）

- 既有 saveDraft 在精确来源绑定/CAS 后独立核验完整结果，三字段 result_review 留在同一 fact_scope_v1 来源行；当前投影共同供正式正文、内部片段、Fact.has_quant/选材/plan 与 R3.1/R3.2 消费。客户端不写核定，失效/撤销不退回数字或整卡信用；真实非量化成果保留，judge 不能补授缺失证明。
- 纯合成材料经真实 Router 上传、保存/详情、本机 Splash（local/Q4-PLE4）、实际两路正文消费者及评分。首轮 6/7 发现交付伴预测被误拒；通用模态修正要求至少一项已发生成果，并逐命题保留自身时态/条件/模态，同七项以七个真实 localhost 请求复验 7/7。非量化及交付伴预测在两路保留、R3.2=0；三个实测正控为 0.5，同数预测及混合过强断言不进结果正文、R3.2=0；全部 trace 有效且 auto_pass=false。
- 最终全量 `2636 passed、1 skipped、84 subtests passed`（41.32 秒），架构 v2 与 TypeScript 检查通过；原 PDF 测试文件 `3 passed`，物理两页与 trace 断言保留。原 panel 逐来源只读回显的组件行为已验；说明仍出现内部字段名，不称 rationale 文案或原生 UI 已验收。
- 真实归属/发生性冲突必须拒绝的标准不变。I 验收时已覆盖同一明确对象/环境 scope，尚未完成自由文本别名的跨来源复核；后续 J 的有限覆盖另行记录，不以字符串相似合并，也不宣称全部语义完成。内部片段使用明确合成选材输入，没有伪造 fresh/grounded 审计；本次不代表完整 jobs.previewPreparation RPC、deep_verified、真人资料、真实 JD、正式投递件或实际投递。四项共享选材及 Agent 四层接入仍 pending。

## 2026-11-21 同 Fact 跨来源核验与依据（切片 J，限定工程范围已完成）

- 原 saveDraft 对同 Fact 当前全部绑定与 scope 一次批核，包括未 adopt 的来源；各原行的主来源独立支持完整句和自身实测。server basis_sha256 绑定同批原始依赖，正文、片段、选材、评分与详情共用当前投影；旧 I 无依据或集合失配不借旧信用，不读时补写。matching 仅限制已有 scoped results 的个人正证，false 不作纯他人或冲突证据；正式语义报告沿现 VERSION v7 失效旧 v6，不加接口、队列或平行账本。
- 纯合成资料经原 Router 上传、复审保存/详情、本机 Splash 和实际两路正文/评分消费者。首轮 12 场景 11/12，共 15 次真实 localhost 请求，发现本人非量化对接错误借用同事的实测；保留失败审计。按通用量化责任关系澄清后，原 12 场景加真实 team_lead/contributor 两正控复验 14/14，共 18 次请求，原实测正控同时保住隐含主语。
- 原失败的完整分工句在两路保留且个人 R3.2=0；同事行可独立核实测，但不能给本人借用。别名责任纠正反例不进个人结果正文、R3.2=0；时间推进、主导及参与正控保留正文、R3.2=0.5。全部 trace 有效、auto_pass=false，既保住非量化价值，也未加样例词表或要求亲手测量/独自完成。
- 最终全量 `2679 passed、1 skipped、94 subtests passed`（48.60 秒），架构 v2 与 TypeScript 检查通过。J 仅完成限定工程和有限合成覆盖，不证明全部语义边界；J 验收时尚未覆盖完整 jobs.previewPreparation RPC，后续 L1 的合成协议范围验证见下文。rationale 清晰度、原生 UI、deep_verified、真实 JD/真人正式件/投递仍未验，P0-026 继续推进。

## 2026-11-21 精确引用增量与正文预算（切片 K1，限定工程范围已完成）

- 正式共同 builder 以精确引用 Fact 的新增支撑选材，同一父级按最大支持计入，重复子项及同卡数量不抬权；落实最多三项目、每项目三行动两成果。selector 决定有限有序事实，plan 不再量化优先二次截断真实引用；内部预览仍保持只读引用片段职责。
- 7 个业务 RED→GREEN，包含原六项及 R2.2 正文预算集合对照；验收核实际 rendered claims 与 resume_assessment，不以 Plan.fact_ids 代替正文。K1 验收时，摘要、精确引用补充成果和场景内完整成果去重仍待后续。
- 合成 PDF 的四卡输入保持，末页完整引用断言随实际选择的第三项目定位；物理两页 A4、首条引用位于首页上半页、末页唯一完整引用及页面边界断言通过。该结论限于排版和内容断言，未完成全页像素视觉或原生窗口验收。

## 2026-11-21 共享结构合同与合成准备 RPC（切片 L1，限定工程范围已完成）

- 首次真实合成流程执行 13 个 RPC、2 次本机 Splash 请求后，在偏好生成处阻塞：调用方已传 schema，共享客户端仅在原生 LM Studio 路径消费，JSON-object 请求缺完整字段合同；模型返回错误字段，既有严格校验正确拒绝。修复由共享 client 传递同一完整 schema，保留原生协议、显式格式、无 schema 行为与请求不可变性，不增加字段别名或补写响应。
- 7 个实际 Request.data wire RED→GREEN；客户端及四类现消费者定向验证合计 `251 passed、55 subtests passed`。同一隔离合成流程随后完成 28 个真实 Router RPC、6 次本机 Splash 请求，覆盖上传、证据核定、偏好生成/确认、档案审核、线索转换、assessPreparation、matchPreparation 与 previewPreparation。搜索和详情使用明确的外部协议 fixture；真实招聘站访问与投递均为 0，资料、凭据及缓存均隔离。
- 准备评估为 prepared，来源要求 grounded；匹配一轮完成 5 个 check、4 个父要求均 supported，无 degraded、deferred、unassessed、预算缺口或 continuation。预览返回 preview_partial_ready，`partial=true` 表示本次有限评审范围（可见事实 10/18）；3 个正文事实保留完整非量化结果，`input_fresh=true`，`send_ready=false`、`deliverable=false`、`active_target_eligible=false`，预览自身没有模型请求。
- 实际请求逐条核对捕获字节摘要，本组合成规模未观察到预算越界或截断。共同语境/schema 注入前统计输入预算在 L1 时仍是独立既存缺口，本片未修复，后续见 L2；未清理有效缓存或修改语义合同版本。此链路不代表正式 K1 选材、rationale 文案、原生 UI、全页像素视觉、deep_verified、真实 JD 或正式件/投递验收。
- K1/L1 最终全量 `2696 passed、1 skipped、101 subtests passed`（42.28 秒），架构 v2 与 TypeScript 检查通过。P0-026 仍为唯一 next/in_progress，当时其余三项选材与 Agent 四层接入继续推进；摘要后续见 K2。

## 2026-11-21 职业概述与任职来源（切片 K2，限定工程范围已完成）

- 保留显式已确认摘要与各 current 任职的完整职责、原首贡献，按各自身份显示公司/职务/期间；较新但已结束的任职不替代当前，JD 前置的局部贡献仍在工作经历。没有 current 时使用显式摘要，或带实际期间的既有历史履历，不称现任。
- 摘要仅由原 summary_fact_ids 驱动，删除与 Fact ID 重复的 summary 文本副本和无来源 fallback；逐 Fact 登记真实行和来源，同一首贡献从工作职责移入摘要而不重复，另一个同文身份不借证。摘要与履历共用任职上下文显示，实际日期各有来源 claim；底稿不修改。
- 独立 5 个合成变体先得到 4 failed / 1 passed，原四个业务 RED 修复后同组 5 passed；实际 profile.update→review→加载→共同 builder、正文行/claims、resume_assessment、guided trace 和档案 SHA/原字节均已验证。定向 107 passed；最终全量 `2701 passed、1 skipped、101 subtests passed`（42.41 秒），架构 v2 通过。未改合成 PDF 夹具，原两页 A4、首屏/末页完整文字、边界与 trace 验收继续通过；未宣称全页像素、原生窗口或真实简历验收。
- 长限定与并行任职保留原文，R3.5 阈值及未判状态不变；本片没有新增模型任务，也不宣称物理摘要行数、跨字段语义一致性或高质量正式件已经达标。K2 验收时其余选材仍待后续；完整补充成果后续见 K3，场景语境去重、Agent 四层与真实验收继续推进。

## 2026-11-21 完整补充成果的精确选材（切片 K3，限定工程范围已完成）

- 项目与完整 extras 条目使用同一正向候选循环、精确引用和可选 Fact 预算，每父取最大支持后合计，同分稳定。名称、完整说明及非空链接原子采用；预算不足整条缺席，不能只留标题/链接而丢个人、本机或非生产限定，也不按收益成本比或 URL 加分。
- 原 profile_highlights 已由 selector 产出真正选中字段并由 plan 唯一消费，删除 raw extras[:2]、plan 二裁/补字段及无生产消费者的 excluded 诊断。最多两项归 selector；必要履历、摘要、教育与工作软 minimum 保持职责，不把可选预算冒充全文 claims/PDF 行数限制。
- 独立首轮 `16 failed / 7 passed`，原 16 个业务 RED 修复后连同原正控及后补 3 项控制得到 `26 passed`；新增控制不计作原 RED。相关七文件 `150 passed`，最终全量 `2720 passed、1 skipped、101 subtests passed`（45.54 秒），架构 v2 通过；未改两页合成 PDF 夹具，原页面、首屏/尾页内容、边界与 trace 断言继续通过。实际档案确认/加载、共同正文、逐字段 claims、resume_assessment、guided trace、档案 SHA 和底稿字节均已核验；没有调用模型，不替代真实 JD、正式件、原生或全页像素验收。
- 三个正向条目稳定选两项，第三项保留 not_present；同父同 check 的项目+extras 互补引用在预算允许时共同保留，缺一个就保真实缺口。合法结构 URL 与行动句过滤各守职责，旧噪声镜像测试迁为真实选集和正文负控。
- K3 验收时场景完整陈述语境去重、Agent 四层接入及注入后请求预算继续推进，预算后续见 L2；本片不修改 skills/stack、K2 摘要、评分或投递权限。

## 2026-11-22 完整请求预算与缓存身份（切片 L2，限定工程范围已完成）

- 请求准备归原 LLMClient，使用标准库 Request 承载实际 URL 和已序列化 body；matching 最终批次、执行器预算、缓存身份和首次发送共用同一对象，post_json 仍为准备与原 transport 的组合。没有新 DTO、持久字段、平行计账、旧签名或缓存迁移双轨。契约执行器的真实生产消费者仍只有 matching，不把其他直接客户端调用记为已有契约预算。
- 原 24,000 上限按 Request.data 解码后的逻辑 JSON 字符计量，包含共同语境、schema、provider 参数和内层转义，不等于 token 或 wire 字节。初次/修复超限均不进入对应 HTTP；不可序列化、循环或本地准备失败为 invalid_request，不按 0 放行或重发原输入。不可容纳的独立 check 保持完整原文及自身原因，不饿死其余合法 checks 的完整 Fact 准入；不增加逐 check 平行事实窗口。
- 独立首轮共 10 个业务 RED，原组修复后为 11 passed（含原修复正控）；审查另补 1 个局部准备失败 RED 并转绿，不冒计为原反例。覆盖同 Request 身份、原输入/客户端配置变化后发送不变、缓存实际 body/URL 身份、缓存校验与 0 HTTP、超长 check 隔离、修复计数和失败原因。相关 100 passed、55 subtests；既有调度与应用回归 118 passed。
- 首次全量的 7 个失败来自尚未迁移的旧 post_json mock/裸客户端夹具；三处迁为实际客户端到最终 HTTP 的合成响应边界，原业务断言保留，196 passed。该轮耗时 117.89 秒的原因未单独证明，未据此修改生产算法；最终全量为 2734 passed、1 skipped、101 subtests passed（42.95 秒），架构 v2 通过，包含 TypeScript 和未改的物理两页 PDF/内容边界/trace 用例。
- 复用同一隔离合成应用流程，一次完成 28 个真实 Router RPC、6 次本机 Splash HTTP 200，贯穿材料上传、证据核定、偏好确认、档案审核、来源线索转换、准备评估、匹配和内部预览。来源搜索/详情仅为外部协议 fixture，真实招聘站、正式件与投递均为 0；审核与 freshness 来自真实应用处理器。未修改请求、响应或业务断言来使验收通过。
- 6 份已捕获请求的完整逻辑 JSON 字符依次为 5013、1969、2420、2746、4718、5814；后两份为 matching recall/assess，均不超过 24,000。按当前客户端序列化重建的字节 SHA 与实际 wire 捕获一致；相应 wire 大小为 20198、7739、9110、8906、14478、18699 字节。单轮匹配完成 5 checks、4 父要求 supported，无 degraded/deferred/unassessed、预算耗尽或 continuation；有限视野为 10/18 facts，不以此证明全部事实评审完成。
- 内部预览为 preview_partial_ready，input_fresh=true、partial=true，3 个正文事实保留非量化结果；send_ready=false、deliverable=false、active_target_eligible=false，预览自身 0 模型调用。该结果不代表原生 UI、全页像素、deep_verified、真实 JD、正式简历或投递验收。业务层重复协议注入、部署能力配置特例、场景语境去重和 Agent 四层接入继续推进。

## 2026-11-22 业务调用的协议适配归属（切片 L3a，限定工程范围已完成）

- 证据字段推断与质量判项都已删除业务层的 URL 子串和 provider 参数重复注入，共删除 9 行生产代码。沿现规范由唯一 LLMClient 适配实际配置；未把子串判断替换为“本机服务必然支持 reasoning”，也未新增模型、端点、用户或样例特例。
- 两真实业务入口的实际 Request 对照先得到 6 failed / 4 passed：远端路径含 localhost、未知 loopback、DeepSeek 明确关闭但处于 loopback 均被错误加入 none；已核 Splash/Strata 为正控。删除后原组 10 passed，相关四文件 128 passed、55 subtests；最终全量 2744 passed、1 skipped、101 subtests passed（46.20 秒），架构 v2 通过。客户端显式参数保护、严格业务校验、有限修复、缓存及原两页 PDF/trace 回归保持通过。
- 限定合成 inferFields 应用验收先因验证程序漏传 saveDraft 公开 review 参数在第 5 个 RPC 拒绝，0 模型请求；该调用错误完整保留，不归为生产缺陷。仅补公开确认参数并增加实际材料回读后，新临时目录完成 8 个真实 Router RPC、1 次本机 Splash HTTP 200，返回时间与职责各 1 个 L3 候选；出处保留真实导入文档身份、SHA 和原文摘录。
- 真实请求为 3086 个完整逻辑 JSON 字符、10656 个 wire 字节，字节 SHA 回验一致；shared client 仍供应已核 Splash 的 none，完成状态 stop。此直接调用的计量不冒称统一 TaskRunner 预算。最终回读证明卡字节未变，time_range/role_scope 仍空，candidate_pool_eligible=false；未确认候选，未生成正式件或投递。
- 合成索引使用既有 build_index/save_index 做非 RPC 初始化，不能称索引生命周期已接入产品。查重确认现生产构建入口仍只有 knowledge CLI，而 inferFields 消费该索引；后续应归回现有应用职责，不能依赖开发者脚本维持日常业务。质量侧本片验证实际 wire 与既有 flow 集成，没有补跑真实 Splash 的 quality_judge 应用链；原生 UI、真实 JD 和投递未验。
- 本片未改共享 client 的既有 Splash 部署/LM Studio 型号默认，未裁定 DeepSeek 开启配置与 JSON 默认覆盖的旧规范差异。后续 L3b 先对齐同一 thinking 配置的默认、关闭、开启、PATCH 与环境传播，再完整移除特例，不创建能力账本或并行字段。

## 2026-11-22 配置三态与统一请求控制（切片 L3b，限定工程范围已完成）

- 先在 core、provider 规范与 RPC 合同中对齐现有 thinking_enabled/thinking_effort：默认、明确关闭、明确开启分别为 null/false/true；显式 payload 优先，JSON 输出格式不覆盖明确配置。共享 client 删除 Splash 地址与 LM Studio 三型号的模式判断，保留真实 provider 协议与原生 schema；无能力表、新持久字段、删参重试或平行请求路径。
- App 缺省/null 不继承父进程模式；同部署 PATCH 省略保持、null 重置，实际 provider/有效地址改变时只重置未明确提供的控制，仅模型别名变化保留。直接调用、独立结果复审、有界 preparation/historical 与 Quick Run 共用该配置，Quick Run 用原 on/off/default 覆盖父环境。页面沿同字段提供三态，只有明确开启显示强度；完整保存提交当前地址，空地址沿已有 API 校验拒绝，原配置和凭据不部分写入。
- 独立客户端对照先为 20 failed / 3 passed；后端初组 14 failed / 7 passed，另补结果复审和 historical 两个入口 RED；页面真实浏览器初组 19 failed / 8 passed，补合法地址前置后同组结果不变，另补清空地址却显示成功的 1 个 RED。各组原断言全部转绿，空地址真实 Router 另有 2 个既有拒绝正控。页面最终 28 个行为案例经过真实 React、API/RPC 与 Tauri transport，到合成 IPC 边界；测试不接真实原生后端，不据此宣称原生窗口或 deep_verified。
- 首次全量为 2813 passed / 6 failed；六个失败都来自旧 Splash 测试中明确开启却预期地址强制关闭/其他地址省略的过时规范。按新合同迁移明确关闭/默认的测试前置，保留原方向结果、单次调用、800 输出预算、结构与不可变断言，不改生产使旧特例回归。最终全量 2819 passed、1 skipped、101 subtests passed（53.02 秒），架构 v2 通过，包含 TypeScript、28 个浏览器行为及未改的两页 PDF/正文边界/trace 回归。
- 原隔离合成应用程序保持同一源码 SHA（425d369785bf057b399a37623c0df667a7cde8bfc42223bf82bded2ad3e40445）与业务断言，一次完成 28 个真实 Router RPC、6 次本机 Splash HTTP 200。原公开设置已明确 false/high，六份实际 Request 均为 reasoning_effort=none、无 thinking；逻辑 JSON 字符为 5013/1969/2420/2746/4718/5814，对应字节 SHA 均独立回验，后两份 matching 请求保持在 24,000 上限内。
- 匹配完成 4 个父要求、5 个 checks，无预算耗尽、延后或未评估项；partial 仍表示 10/18 facts 的有限视野。内部预览 code=preview_partial_ready，input_fresh=true，3 条正文事实保留 established/null 的非量化成果；预览自身 0 模型调用，send_ready/deliverable/active_target_eligible 全 false。运行记录 SHA 为 9bd9788f1378a7a134584efaf4077a4f6a1ce41cef1a4a387c15c5171c68d6e5。
- 真实模型仅验证明确关闭的合成 preparation 链；默认/开启与其他 provider 仍是 wire 对照。来源搜索/详情仅协议 fixture，真实招聘站、正式件和投递为 0。索引生命周期、场景完整语境去重与 Agent 四层接入继续推进，本片不提升 P0-026 完成状态。

## 2026-11-22 推断索引应用接入与候选发布（切片 L4，限定工程范围已完成）

- 既有 inferFields 先定位实际目标，有目标才直接复用原 builder 准备当前派生索引；无索引、损坏索引和跳过后恢复的正文不再要求工程 CLI 初始化。索引元数据、正文和实体摘要来自各自实际解析字节，保留原 asset_inventory；index.json/INDEX.md 使用既有单文件原子写。删除空缓存隐式 merge_text 补读，不把导航或全库 verify 视为事实权威。
- 原来源读取、聚合、解析及缓存贯穿 material_id/document_id/sha256，同文档不同材料不再借身份。新召回保留整份 manifest 准入；有效且未变化的既存精确绑定可窄复验，空或损坏材料指纹不授该资格。不自动 refresh，不新增持久字段、接口、来源副本或业务脚本。
- 任职窗口和职责上下文来自同次实际已确认档案，只采用与目标卡相关的约束；其间接材料依赖也复核当前许可。原 ValidatedSourcePaths 捕获卡、来源与已使用档案版本。整批候选在内存暂存，缓存返回及最终发布复核全部实际输入、现行根许可和原状态版本后才一次写原 state；后卡失败不留下前卡新状态，模型边界中真实 API 否决不会被旧整份状态恢复。不宣称跨进程 CAS 或多文件事务。
- 独立 Router 组先为 19 failed / 4 passed，另补空指纹准入 1 failed / 1 passed；仅在最终 HTTP 边界提供合成响应，实际上传、引用管理、来源读取、档案确认和候选否决均走应用。推断内部原组为 13 failed / 5 passed；索引有 10 个行为 RED 及 2 个原子发布机制控制。各组均转绿，合法缓存、真实来源、窄复验与已确认任职正控保留；前置不成立的夹具失败及旧读取替身类型失效单独排除，不计业务 RED。
- 最终全量 2874 passed、1 skipped、101 subtests passed（50.74 秒），架构 v2、路线图、AIEF 和差异检查通过。包含 25 个新生命周期 RPC 用例、32 个推断单元、原 11 个确认/否决/连续确认/协议对照，以及未改的两页 PDF、正文边界、trace、TypeScript 和浏览器组件行为。
- 原隔离合成应用程序仅移除非 RPC 的索引 bootstrap，增加 API 前后索引只读断言；原公开 false/high 与 8 RPC、1 次 localhost HTTP 上限保持。程序 SHA 为 e029840ca141a1c61029e17af1a52fa151981c5fb00372b231f6bd6433a4d6e3，一次完成 8 个真实 Router RPC、1 次本机 Splash HTTP 200。API 前索引不存在，inferFields 自行创建两个索引文件，返回时间和职责各一条 L3 候选；完整材料/文档/SHA、引文及已存候选状态均独立回读一致。
- 实际请求为 3086 个逻辑 JSON 字符、10656 个 wire 字节，明确关闭沿 shared client 发为 reasoning_effort=none，无 thinking/chat_template_kwargs，finish_reason=stop。实际请求 SHA 为 5a3298daeebfe76df2757baed47ab365523cfa5184e185aeafc48414812c01f5，运行记录 SHA 为 d1d0408e5fe3726284f066e5fc0fde84803ec9897223452a98bedb5c12e8dd8f，均已独立重算。此直接调用计量不冒称 TaskRunner 预算。
- 原卡前后字节完全一致，时间/职责仍空、candidate_pool_eligible=false，没有确认候选。真实招聘站、正式生成与投递均为零；原生 UI、quality judge 真实模型链及 confirmInference 的末端来源复核未由本片验收。下一片核定候选接受的原始依据与连续确认版本接续，P0-026 继续进行。

## 2026-11-22 质量判项的完整输入与实际采用事实（切片 L7，限定工程与合成输入验收完成）

- 先查原质量 loader、标准 trace/claims、matches_fact_occurrence、current_result_reviews 与证据详情 project_fact_scope；复用现职责，不重建生成 FactIndex、不增 RPC、持久字段、来源账本或业务脚本。现 quality_report/llm_judge 保完整角色/provenance、背景、原行动/成果及当前范围语境，去掉字符与前 N 条裁剪；原语境可以核验已表达职责，不能补正文未写的成果或岗位信用。
- 唯一 claims 投影保原身份和实际行，actions/results 从精确原数组位置取得完整 index/value；bullets 仅补 render_line。cards.result_reviews 仅含本次实际采用且完整匹配的当前原 row；fact_scope_review 用同次 doc/documents 投影，不另读来源或接受陈旧核定。合法日期降精度保持，头部联系方式不加入判项；原 cards/trace 不变，prompt version 升至 6，L6 的 24k/6000/两次尝试、缓存身份及 H/strong 保持。
- 独立 RED 共四例：真实生成→标准 trace→当前评测→最终 HTTP 的第六条成果非量化/实测两例为 2 failed / 85 deselected（0.16 秒），同文 action/未采用同事 result 一例为 1 failed / 87 deselected（0.14 秒），完整责任/环境/行动的纯 prompt 一例为 1 failed / 9 deselected（0.02 秒）。初次两例因夹具漏 artifacts 在 matching 准入失败，补回后才取得上述业务 RED，不混计。首失败前真实结果资格与来源围栏已成立，不能称 R3 门禁绕过。
- 冻结的四例修复后 4 passed / 94 deselected（0.16 秒），两测试文件 98 passed（0.40 秒），测试、夹具与业务预期未放宽；全部后置身份、原 row、尾部条件与来源不变断言实际执行。实测/非量化/同文负控 R3.2 分别保持 0.3333/0/0，均 auto_pass=false。最终全量 3040 passed、1 skipped、101 subtests passed（56.96 秒），架构 v2 通过。
- 新鲜合成资料通过真实材料上传/文档读取、saveDraft 结果复审、档案确认、岗位保存和 Quick Run API 完成 22 RPC（含状态观察）、6 次本机 Splash HTTP：结果核定一次、匹配两次、背景两次、质量一次。质量实际请求 13664 逻辑 JSON 字符/42019 bytes、输出预算 6000、明确关闭推理模式，响应 stop。完整 role 118 字、context 186 字、result 255 字进入请求；六条原结果留作核验语境，实际结果身份仅为原 results:5，当前同 row 为 established/无实测引文/test/not_released，A/B 正文均在第 22 行完整呈现。
- 独立语义审查保留部分失败：行动 bullet#2 的本人模块主导获支持；结果 bullet#3 末尾也有合法本人主导，却被 R1.4 遗漏，最终报告已记该行缺少角色判定。元数据仍声称五组完成、llm_pending 为空、没有修复且写入缓存，故不宣称 R1.4 整体通过；下一片核逐项覆盖与完成状态。R4 空列表符合完整 JD/档案/正文，没有超出岗位维度，也没有借未采用的 37%、平台架构或生产发布。模型给行动行 result=true，strong 仍按实际结果身份撤回；非量化成果保留，量化为 0、auto_pass=false。
- 运行记录 SHA 为 08b6968ecc4b4d2ffd1391e77119c0ff815a2eda58b5190c9662928953454ceb，质量请求/响应 SHA 分别为 40e9fd96aeb61804ae21b4fca9ad756d943127d05d8cd07fb2225b6203919830 / 405ab793872e987db0d0b11676e85e1567c5b59a178f8b862fe5e503baba01f6，A/B 正文 SHA 同为 16b8ae009e55726ec8faa9a4361ac9be80667831d2e850eaddd96807bf598db7。六对 wire、7 项 trace 输入、5 项原始来源和 241 个生产文件均独立核验；不调用生产 key 函数重算的缓存身份一致，缓存内容保留上述缺项，没有隐藏失败。父/实际 pipeline 子进程均加载 loopback 限制，无外部连接或拒绝事件。
- 本片完成输入与限定采用职责，不证明 R1/R4 全语义正确；真实 JD/正式件/投递、原生页面及全部来源语境仍待验收，P0-026 保持唯一 next/in_progress。matching 的短引用另经实际 HTTP 核对，results:5 与职责在请求中完整，160 字 quote 只是报告简写，不能误报成模型输入截断。

## 2026-11-22 正式质量判项请求、缓存与有界修复（切片 L6，限定工程与合成应用验收完成）

- 查重沿现 Quick Run 正式 pipeline、quality_report/llm_judge、唯一质量缓存、TaskContract/TaskRunner 和共享 LLMClient 补齐实际消费者。登记 quality_judge，保输出 6,000 tokens 与完整已准备请求 24,000 逻辑 JSON 字符，同一 Request 决定预算、身份和发送；不另建 Agent 模型入口、RPC、业务脚本或平行账本，guided 仍零模型。
- 原缓存键改为实际 URL/body、当前正文/岗位、trace 输入版本、卡字段与协议；删除二次 context 读取和旧 key 入口，原缓存 schema 升为 2，旧缓存仅 miss、不删除或迁移。命中先核完整版本/声明，再按当前正文/JD/引用重验且保留组逐项一致；默认空数组、坏引用或自报完整不能授信，重复 JSON 键由共同 parser 拒绝。历史 rejected_items 仅为严格类型的诊断，不补信用；认证 headers 不参与身份，稳定同请求有效缓存零 HTTP。
- 修复只请求并合并未完成组，不覆盖首轮合法结论。修复超预算、不可构造、传输失败或仍缺项，都保首轮已核完整组、其余 pending，不缓存整份；没有有效组则不可用。次数按实际发送回调计，准备失败不计模型调用；TaskRun 保真实原因/耗时，完整诊断沿 stdout，原 meta.error 使用稳定原因，不增持久/API 字段。来源变更仍沿 H 拒绝发布，不借 partial 降级回写旧报告。
- 独立质量首组 13 例旧生产为 12 failed / 1 passed（0.30 秒）：两 provider 的 raw 小于上限而 prepared 超限仍各发 2 HTTP，修复超限仍发第 2 次，准备失败虚计次数，发送失败丢首轮合法组，端点/推理模式变更及三类坏缓存仍 hit。请求头变化和稳定缓存正控通过。实际 flow 首 HTTP 变更卡后，原来源 fence 已正确拒绝且原报告字节保持；该例后因多发修复 HTTP 失败，不能称来源绕过。
- 追加两例旧生产 2 failed（0.14 秒）证明未请求修复组覆盖旧结论，以及 normalized partial 缓存借默认数组冒充完整。原 15 例最终 15 passed（0.14 秒），全部此前失败点后的计数、pending、无 partial cache、真实结果和来源断言执行。共享 Runner 另两例先 2 failed（0.04 秒），再由原协议责任拒绝 finish_reason=length 的闭合 JSON，截断不进 extract/validate；后续 stop 正控与连续截断原因通过。Runner/缓存完整组 30 passed（0.06 秒）；缓存新控制是候选后的验证，不混计旧 RED。
- engine 整文件首轮 79 passed / 6 failed 均为旧 FakeClient 缺 prepare/send；只迁真实共享准备与最终发送替身后 85 passed。稳定诊断协议随后仅使旧 exact 字串断言 1 failed / 84 passed，按新 invalid_json 原因迁一行后最终 85 passed（0.33 秒）；其他新旧业务预期不变。CLI 旧替身另 1 failed / 1 passed，同类接口迁移后 2 passed，免密 2 次/在线缺 key 零构造原断言保持。全量首轮 1 failed / 3035 passed 仅因注册集合未列新任务；补既定名称后最终 3036 passed、1 skipped、101 subtests passed（56.90 秒）。架构 v2、路线图、AIEF 与差异检查通过。
- 实际应用复用 K4b2 已经真实上传、结果复审、档案确认和岗位保存的纯合成资料，保持原来源字节；通过现 settings、profile/evidence 与 run.quick.start/get 完成 11 RPC、5 次本机 Splash 请求。matching 两次、背景两次、质量一次；质量完整请求 5580 字符、输出预算 6000、明确关闭推理模式，五组判项完成且 llm_pending 为空。正文完整实测句/限定及精确 trace 保持，量化 0.5、auto_pass=false；没有用请求成功补绿质量或授予投递。
- 应用记录 SHA 为 4fe6190c1e6317b7e7af5438c2c24f4cdfcf6ac4a1828f167de474d9801ca3fd；五对请求/响应 wire、实际正文/trace/Scorecard/缓存均已独立重算；未调用生产 key 函数，以实际请求与原输入重算的缓存身份与文件/API 一致。质量请求 SHA 为 d2907b0dc193a192b5b50a98bb9ab8efd713b404e36d4c028d7f3b064b8ec9dc，A/B 正文 SHA 同为 49a9cef9da69163e02cc8cfa791c1d638279af3ce78965c6748d49728abd4ae4；5 项原始来源及 241 个生产文件摘要保持。API 只按既有 PDF 检查叠加已知页数 1，同一质量判项未变，裁切仍未知；该投影差异不计产品失败。父进程和实际 pipeline 子进程均加载 loopback 限制，拒绝数零；生产 Python 源前后未变。实际应用本片只验证单一配置的一次质量请求，不冒称 live 缓存命中或实际模型修复已触发；这些边界由真实客户端/最终 HTTP 的独立对照覆盖。
- 24k 准入覆盖实际 prepared request，不代表 judge 已见完整原卡。只读发现原摘要仍截断角色/背景/行动/成果及前五条，可能遗漏正文已选的 results:5 或尾部职责/环境限定；下一片先核现 trace 与结果投影的正证/核验语境职责，不另建事实账本。尚未实测模型因此误判，R3.2 的精确已核结果边界仍保持。真实 JD/正式件/投递、原生 UI 与全部语义语境继续 pending，P0-026 不关闭。

## 2026-11-22 guided Agent 四层质量与固定审核（切片 M1，限定工程与合成应用验收完成）

- 查重复用 RuleEvaluationEngine、同次版本读取、共同四层计算、Scorecard.quality_report、ReviewSnapshotStore 和现 QualityReportPanel；没有新 Engine、RPC、持久实体或业务脚本。RuleEvaluationEngine 直接消费 trace 绑定的实际卡/职业档案/岗位字节，同批输入用于旧参考指标和四层报告，报告绑定正文 UTF-8 SHA 与目标，Scorecard 保入口版本标签。实际读取校验与末端 trace 复核共同防换值后恢复；独立无岗位绑定的诊断能力不补造岗位事实。
- guided 不注入模型或拼造正式 semantic；没有当前正文映射时保留未判，不再从空矩阵推出所有项目无关。有效已评映射的真正未覆盖负控保持。已呈现的实测结果沿共同 R3.2，旧规则或 LLM 覆盖参考不改 auto_pass。原显式 LLMEvaluationEngine 只保传报告，该 CLI-only 能力不冒称新的 App 语义能力。
- AgentLoop 将本次已有 Scorecard 传入现 Store.create；Store 在唯一 PDF 导出前捕获报告副本，核入口标签/目标、报告正文 SHA/目标，导出后用实际 Markdown/PDF 字节封入原 quality_snapshot/quality_sha256 与 manifest。全部成功后才回填候选；失败不污染调用方。native 的同类摘要/产物校验收归同一 Store，旧 digest 转发路径退役。已有 native report=null 仍诚实表示未记录判项，不由旧分数补绿；新 guided 必须有实际报告。
- 初次独立引擎 18 例为 15 failed / 3 passed（0.26 秒），guided API 原真实来源用例另 1 failed（0.10 秒）：缺四层报告、目标冲突、评估返回后变源和空矩阵误判均已复现。三个实际 SHA reader 的 ABA 与四层期间变源钩子当时因未接消费者尚未触发，不宣称旧实现曾实际读到 B；GREEN 时 consumed/evaluated 均实际执行并拒绝。原组 18 passed（0.16 秒），后补显式 LLM 高覆盖不改四层的控制后全文件 70 passed（0.26 秒）。同文未采用结果量化 0，实际采用实测正控 0.5；原前置 fixture 错误不计业务 RED。
- 独立快照/API/页面首组 11 failed / 5 passed（0.37 秒），实际覆盖发布前绑定错配、发布后只改/删报告、pending/恢复执行与实际组件无四层；原组转 16 passed。后补八项 Scorecard 构造控制验证单次导出、报告预捕获、身份/缺报告拒绝和失败原子性；只作为追加控制。五个受影响文件 67 passed（0.59 秒）；两条 native 原负控仅把错误归属迁为 review_snapshot_invalid，禁止上传及队列字节断言保留。
- 集成复验曾出现两例 REVIEW_SNAPSHOT_BLOCKED：既有合法线索未单独声明岗位关联，本轮明确目标没有传入审核候选。保留原线索夹具，在 AgentLoop 只补本轮实际目标，非空冲突仍拒；不补造 JD 状态、来源指纹或审核批准。真实 guided 文件 2 passed（0.98 秒），完整正文/来源/量化/目标/实际 PDF 和摘要断言全部执行。测试曾预期重复 quality_passed 包装字段，按既有 generic 合同仅移除该冗余半句，保留 report.auto_pass 与全部未判断言。
- 独立审查补出跨队列 all_pending 原样返回未核报告的 API 缺口；当前 UI 不消费此字段，批准/恢复本来仍会拒绝，未称投递绕过。新增两份真实队列的合法/篡改对照先 2 failed（0.07 秒），再用同一 ready/invalid 投影逐个按本队列 ID 核 Store；合法保报告，失效移除报告并清正文，不改磁盘队列。审批 API 与 Node 页面 27 passed（0.41 秒）。页面复用真实 TypeScript 组件显示四层/未判/建议及封存参考分，旧裸分不盖过报告；该证据不是 Chrome 或原生窗口深验。
- 最终全量 3016 passed、1 skipped、101 subtests passed（58.93 秒），TypeScript、架构 v2、路线图、AIEF 与差异检查通过。现审批仍以事实/快照和授权为边界，不因 auto_pass=false 新增分析硬阻断；缺失的正式语义判项与 PDF 裁切校验诚实保留。
- 合成实际应用先验证显式岗位关联，再以缺关联线索复验最终候选；复用 K4b2 经真实 API/本机模型复审的纯合成材料、档案和岗位，只在外部线索输入边界准备本地合成 lead，未伪造来源批准或访问招聘站。两次各 9 个真实 Router RPC、实际 PDF 导出，应用 HTTP/socket/model 请求均为零。最终流在质量报告仍 pending/auto_pass=false、量化 0.5 时返回 ready；完整结果、guided 完整背景和精确 trace 保持。仅改报告后 pending=invalid，批准返回 review_snapshot_invalid 且队列/正文/PDF 不被更改；恢复原记录后批准返回 checked_not_submitted、success=false，最终 REVIEWED_CHECK_ONLY。目标关联正确而 jd_status/source_jd_sha256 仍空，原 lead、卡、档案与岗位文件字节保持。
- 最终应用运行记录 SHA 为 32041068abf4f74ff0ec127cd42955b64bfeab008b188dcf0142a2fd687a9af0，Markdown 为 5eb0d87e75c2bd0e531c495b2e558d1ddce9f8416795de6d2b940ffc5d0f8098，PDF 为 e9bc7a71dd18ed8b36501a11472720822b85e84f223cc3a6a8fb8d014103380f，质量快照为 36eac020ea276b13cf65e434bd84c3a1aa259567a75f8518e1009ff7f79b577b；记录、实际产物、manifest 与 canonical 质量摘要已独立重算一致，生产 Python 源前后未变。原生页面、真实 JD/正式件/实际投递仍未验收，P0-026 继续进行。
- 下一片先核正式 Quick Run 的质量判项请求/缓存职责；该路径有实际 API 消费者。当前显式模型 Agent 仅从 CLI 注入，guided API 仍零模型；不能把升级旧 evaluator 或接入内部 advisory 报告冒充 App 正式语义闭环。

## 2026-11-22 实际正文的有界背景语义去重（切片 K4b2，限定工程与有限合成应用验收完成）

- 查重沿现 Quick Run 配置、generation_flow、共同 builder/ResumePlan/renderer、TaskContract/TaskRunner 与 readiness.reasons 的真实消费者补齐。模型在实际选材完成后只看同项目最终标题/期间/角色/所属工作、完整背景与实际行动/成果，返回 keep/omit/unknown；不引入预算外、范围排除或别的项目事实。精确岗位正引背景保护，合法 omit 只移除背景及 block/plan 原 context IDs，完整结果与自己的 claims/实际行保持。guided 不注入该能力、零模型调用，无新 RPC、持久账本、缓存或业务脚本。
- 完整已准备请求限 24,000 逻辑 JSON 字符、输出 2,048 tokens；每版至多两次任务尝试，不把共享 transport 重试计为同一物理 HTTP 上限。准备失败或初始超预算零请求；索引缺漏、重复、布尔冒充整数、越界或额外字段均整批不采纳；未知/不可用保全文并沿原 API 说明，不抬缺证或 quality gate。来源/卡/档案/报告中途变化仍拒绝生成。renderer 原显式来源绑定及内部信息校验先于省略，不能靠删背景洗掉错误。
- 独立真实 flow 首组 2 failed / 1 passed，其余十二项 12 failed：前者是实际量化/非量化背景省略行为 RED；后者证明任务、预算与降级诊断尚未执行，不能说旧版已经接受非法响应或绕过来源门禁。builder 首轮 6 项缺回调 TypeError 不计业务 RED，后续两处 fixture 缺要求 text 修正后全部断言执行，独立 20 passed。原断言保持，guided 正控禁止 HTTP。
- 额外反例证明 JSON 同对象相反重复键被“最后一个值”吞掉：实际背景 flow 两项 RED、共享 runner 两项 RED。复用原结果核验唯一键 parser，移到现 TaskRunner 响应解析职责供两处真实消费者共用；不写任务专属解析器。最终 flow 加原真实 HTTP 组 18 passed；runner/结果核验 30 passed、10 subtests passed，原合法结果核验正控保留。
- 第一次完整回归为 1 failed、2972 passed、1 skipped、101 subtests passed（57.75 秒）：唯一失败是旧 CLI FakeClient 构造只收 kwargs、不支持真实已有位置参数及 prepare/send 合同。仅修测试替身，在最终 send_request 边界控制响应，保持空 key/无 Authorization/原在线缺 key 阻断断言；该文件 2 passed。最终全量 2973 passed、1 skipped、101 subtests passed（55.62 秒），架构 v2、路线图、AIEF 与差异检查通过。
- 首轮全合成 App→本机 Splash 经真实上传、逐事实复审、档案确认、岗位保存及 run.quick.start/get，完成 39 个 Router RPC、8 次本机 HTTP，A/B 各一次背景任务。非量化重复背景省略、独有环境条件保留；原“提问背景必须保留”预期两版却为 omit，原始预期仍记 2/3。两份独立反审确认，剩余标题/期间/职责/核验过程和完整实测结论已覆盖该问句实质信息；不能把“问题不能证明结果”的方向反用于保结果后的背景去重。未为此修改生产 prompt、添加问句或否定词规则，也未改写原记录为当时全通过。
- 随后先冻结更强的正反对照：相同背景包含输出一致/错误率、脱敏回放及生产适用性未验证；这些条件仅在背景出现时须保留，完整结果已经表达时可省。两次单项目实际 App 流分别完成 21/22 个 Router RPC、各 6 次本机 HTTP，A/B 均分别 keep/omit。父进程与实际 pipeline 子进程都加载 loopback 限制，实际连接记录均在本机、拒绝数为零；首轮 guard 只在子进程生效的验证程序问题保留说明，不冒称首轮父进程也受该 guard 约束。
- 两次对照的完整结果、精确 claims/实际行、标准 trace、卡字节及生产 Python 源前后均一致；正文/API 可回读决定理由，两个报告的量化比例均 0.5，quality_passed/auto_pass 均 false。原三例报告也非自动通过；PDF 只确认单页导出、裁切仍未验证，未借呈现省略补绿整体质量。正反运行记录 SHA 分别为 5608e3d8bcb0f81a33eb50f5601fd7a082ce883393a88c9e0030ad000fd0d05c、8c2a1d1af17b7b4bd57deb16a01f05d6e69ee11392c3bec4ab0c127e378e38b5；每份请求/响应 wire SHA 已独立重算一致。
- 三次合成链合计 82 个 Router RPC、20 次本机 HTTP，其中 6 次背景判断。有限语义对照不替代全部来源语境、原生页面或真实 JD/正式件/投递验收。下一片复用现 Scorecard.quality_report、共同四层输入和固定审核快照接通 guided Agent 的质量解释，保持零模型、零外部投递；P0-026 继续进行。

## 2026-11-22 背景自身的精确事实来源（切片 K4b1，限定工程范围已完成）

- 查重确认现 ProjectBlock.fact_ids/ResumePlan.fact_ids、FactIndex 和 renderer.from_fact 已有真实职责。生产仅改 plan 与 renderer：在结构装配时保留真实 context Fact，同次取得背景全文和身份，登记原 block/plan IDs；合并项目不借首张代表卡或同文。renderer 按实际索引核显式绑定的唯一性、类型、完整展示值和两处一致性，并在真正背景行记录来源、字段和 Fact ID。无新增字段、接口、来源副本或业务脚本。
- 背景是原结构事实，不增加可选 Fact 配额；只有自己的真实呈现可满足其精确岗位引用，非 bullet 背景不借 results 或 R3.2。正式与 guided 沿同一 producer，背景实际来源随 evidence claim 据实进入现 trace 输入；不因旧计数省去合法依赖。内部 preview 只有 actions/results 身份，范围拼接说明保留 presentation，不扩成完整背景。
- 独立真实链先 `5 failed / 25 passed`（0.11 秒），显式 renderer 输入组先 `8 failed / 9 passed`（0.07 秒），无夹具错误；共 13 个业务 RED。强反例把 context 与结果设为同文，删去背景环境限定、重算整体正文 hash而不改 claims，原全文仍在 result bullet，旧 trace错误通过；修复后以真实背景行拒绝。另验长背景、合并 B来源、同文 A/B引用分离、未知/多/非证据/空/不完整/单边绑定拒绝，保同文未采用结果无信用及原 preview 正控。
- 原断言和夹具冻结后，独立两组分别 `30 passed`（0.10 秒）、`17 passed`（0.04 秒）；此前被首断言挡住的完整来源/文本/实际行检查全部执行。最终同树全量 `2946 passed、1 skipped、101 subtests passed`（54.83 秒），架构 v2、路线图、AIEF 与 diff 检查通过，含既有两页合成 PDF/首屏/尾页边界与 trace。
- 本片没有 Splash 或外部模型请求、真实招聘访问、真人正式件或投递。没有把所有身份被人为删掉后与合法 preview 形状一致的对象冒称可辨，也没有新增通用防篡改框架。下一片 K4b2 在实际选材之后纳入有界语义呈现，现卡选择/岗位匹配/事后 judge 不能借作其权威；未知或不可用保全文，精确岗位正引 context保留。Agent 四层与原生/真实验收继续 pending。

## 2026-11-22 完整项目场景呈现（切片 K4a，限定工程范围已完成）

- 对齐 core、设计与任务摘要原先相反的去重方向：保留已选完整成果 bullet 和独立来源，只可省经完整语义判断确认冗余的背景；未知保留双方。语义去重仍 pending，不以字符串包含、同卡或结果核定代授信用。
- 查重确认固定 120 字裁剪只有共同 ResumePlan 一个消费者。生产仅改原 plan：删除该常量和孤立 helper，背景直接保留既有 FactIndex 中的完整 context。独立对照另复现合法“尚未”背景被成果词表整段过滤，因此同时撤除该背景处误用，不加措辞特例；其他字段、预算、来源/范围准入及 renderer 内部信息拒绝保持职责。
- 首轮 `5 failed / 5 passed` 含两项测试前置/精度问题：沿用旧 result_reviews、未考虑现四位小数。修正真实夹具并保留原否定句后，原生产 `3 failed / 7 passed`（0.07 秒）：共同和 guided 长背景尾部责任/环境丢失，合并项目合法否定背景被整段过滤。三项业务 RED 全部转绿；背景/成果同文的实测、已核非量化、未核三控继续区分真实结果信用，不把背景算成量化 bullet。
- 最终五文件定向 `99 passed`（1.56 秒）；实际来源加载/生命周期、生成 trace、评测和合成 Quick Run/PDF 三文件 `107 passed`（3.61 秒）；架构 v2、路线图、AIEF 与 diff 检查通过。原两页合成 PDF、首屏/末页完整文字、页面边界及 trace 未改断言。按此次单一生产模块风险验证，未重跑全量；上一片 2928 项全量不冒充当前树的全量结果。
- 无新增字段、任务或业务脚本，0 模型请求；没有真实招聘站、真人正式件或投递。当前背景仍按原 presentation 输出，未宣称具精确 Fact occurrence 或新增防篡改能力。下一片复用原 block.fact_ids 与 from_fact 补背景自身身份，再在最终选材之后接完整语义呈现；Agent 四层、原生与真实样本验收继续 pending。

## 2026-11-22 推断候选确认的来源依据与接续（切片 L5，限定工程范围已完成）

- 沿现 inferFields/confirmInference 和候选 state 补齐，复用既有 candidate_hash 选择身份、card_sha256 作为唯一同卡确认进度。查重确认候选引用与旧不可逆摘要不能恢复全部实际输入；在原 state 增唯一 input_basis，记录实际已核路径/SHA、原采用文档三元身份及现协议/公共上下文摘要，无原文副本、平行账本、新 RPC 或业务脚本。现 attempt_fingerprint 改为整份原 basis 的 canonical 摘要，防止只删去一组依赖后仍接受旧候选；确认只复核原集合，不重检索全库或补造旧依据。
- 接受匹配请求/当前卡/服务端状态三个版本，复核来源、当前许可和原采用档案及间接依赖。原样接受只推进现卡 SHA，原 basis/attempt 不改，保住已采用职业档案的两字段双顺序连续确认；目标同一实际文件的受控自变更不扩展为跨卡豁免。改值记 L4 并撤同卡余项，不计否决；精确否决不授事实信用，来源失效仍可撤回。关闭后不接受旧 L3；显式空或非字符串修改值拒绝，不回落原值。
- 原 writer 复用单文件原子写并返回本次实际写入字节的 SHA；同一原卡 raw 用于解析与保留字段。写卡前复核来源/卡/state；卡写失败不改状态，卡写成而 state 保存失败则明确失败、保留真实待审核卡及原/并发状态，旧 cursor 阻止 fresh-client 重放。UI 精确移除已操作候选、L4 撤余并同步计数，错误后刷新实际详情/对账且保当前选卡；设置读取错误不隐藏证据，迟到推断不恢复已关闭 L3。不宣称两文件事务或跨进程 CAS。
- 独立 API 首轮 28 failed / 4 passed，复核后准确分类为 26 个业务 RED、1 个卡原子发布机制 RED、1 项前置不成立：原跨卡原文反例没有 field_sources，职业档案只读另一卡而未采用其原文。通过真实 saveDraft 补实际绑定并断言被采用路径/SHA后，该项作为追加有效控制，不补造历史 RED。原断言保留，连同实现后新增的五项显式值控制，确认组 37 passed。推断内部四项旧协议/缺依据 RED及一项完整结构删依赖 RED转绿，稳定对照保留。Chrome 原七项与后补两个异步 RED转绿，actions 15 项（含四个原 Node正控）与原 settings 28 项共 43 passed；6 个旧页面 fixture 仅补真实 settings 消费者，原 19 项断言保留。
- 同树最终全量 2928 passed、1 skipped、101 subtests passed（55.48 秒），架构 v2、路线图、AIEF、TypeScript 与差异检查通过。包含原两页 PDF、首屏/末页内容边界与 trace；不是原生 Tauri 页面深验，也不扩称模型语义全部完成。
- 实际合成 App→本机 Splash 首次 7 RPC、1 次 HTTP 200：模型把原时间引文的 2023-06 写成 2023-6，应用因非原文引文丢弃时间候选，保留有效 L3 职责。原“两字段均有效”验收未达预期，失败记录保留；没有改写响应、补来源或重复调用模型。随后在同一隔离应用数据上追加 3 个真实 RPC 回读来源、确认有效职责、读取卡，0 网络请求；职责保持 L3/原出处/用户确认，卡转 pending 且不可入池，时间仍空，原 basis/attempt 不变、cursor 与实际文件 SHA一致、候选清空。两字段连续确认的正控本片由独立 API/Chrome覆盖，本次真实模型仅确认了一个有效字段。
- 实际请求为 3086 逻辑 JSON 字符、10656 wire 字节，SHA 59e8acf1aa58bdb95fc727dffda52aca26f34c47a025240931bb6519fbba4927；首次程序/记录 SHA 分别为 55e0bb165abb5e1463d3b648502cf2b204534ffea16c972c9d3abd3907efb58c / 0c6d9d87c0f3b2202bd32066a05c051ed888afd817920e2e2572c32ea501bd1d，后续确认程序/记录 SHA 为 ee1bed28b61d252bd0d029fca81a3e3180b5cdc241a29beb1882be0d2a5d6b6b / f02e23e4f571f65380a3a67af841f6b87e1ce809b474b56ddd84655bad87a9b6。程序、wire、两记录、原文件及持久 state 已独立回读。资料全合成，总计 10 RPC、1 次本机模型请求；真实招聘站、正式生成和投递为零。
- P0-026 继续进行。下一片先核场景/成果去重的完整语境、呈现与评分职责，不能用同卡、同文或字符串包含替代语义；Agent 四层、原生与真实样本验收仍按原任务队列推进。

## 2026-11-21 简历结果证据边界

- R3.2 只消费正文实际采用、经精确 trace 校验的结果 Fact。同卡同文 action 不能借用未呈现的 results。受控负例的量化比例从 1.0 降为 0.0，实际采用结果的正控保持 1.0；两种原始样例均未 auto_pass，不构成投递门禁绕过。
- 非语义评测与规则评测共用来源有效性判断。即使结果原句未变，卡片、材料或正文版本失效后，旧 trace 不能继续为 judge 或四层报告提供权威。
- 逐事实范围的引文必须在所绑定文档内唯一定位；不同文档可各自拥有相同引文。普通复审不得静默擦除旧无效范围；显式撤销或重新采纳只修复目标，保留合法兄弟范围。
- 来源歧义沿既有 source_error 和证据复审入口展示。组件行为已覆盖歧义提示、显式撤销及既有事实扩大引文后的重新采纳；原生页面深验尚未完成。
- 完整结果命题和是否实测的核定归属既有证据复审；正文与 R3.2 必须共享同一现行证据。I 已接通完整结果核定与共同消费，J 已补当前同 Fact 来源集合及别名责任纠正、时序和真实分工的有限合成覆盖；不能据此宣称全部来源语境已解决。唯一引文、results 字段、implemented/released 状态均不是实测证明。
- 源代码基线验证：新增回归先失败再修复；全量单测 2365 passed、1 skipped、59 subtests passed；架构、路线图、AIEF 与 TypeScript 检查通过。该记录是整理前代码基线，不代替整理后的验证，也不代表真实 App/Splash 或正式简历验收。

## 每日准备与语义匹配的已实现机制

- 来源搜索和详情读取保留预算、来源身份及原文指纹；成功零结果、来源不可核验、预算耗尽和执行失败分别表达，不把引擎返回误当作整轮完成。
- 重新打开每日准备时，沿既有状态和显式继续动作恢复；页面或进程重启不重置已执行轮次。岗位详情可只读回看已存 JD，但不能把已存文本当成刚核验的在线页面。
- 有界语义评审保留条款来源、逐事实引用及实际完成范围。缺证据、未评估、部分支撑和冲突不升级为已支持；模型只能判断已有证据，不能产生候选人的事实。
- 正式匹配报告与内部定向片段各自保持用途；只有精确的正向事实引用参与正文选材。已确认归属、完整来源及实际正文位置共同约束覆盖结论。
- 精确引用不因无关材料变化失效；与结论相关的卡片、来源修订或正文发生变化时必须撤销其权威。补证与重审沿既有来源合并和复审边界处理。
- 这些机制的单测与组件验证不证明主动发现已持续产出合适岗位，也不代替目标岗位、真实材料和本地模型的 App 端到端验收。

## 生成、来源与投递的工程边界

- 生成以事实级选材与独立 trace 连接证据、正文和质量报告。匹配排序可改变既有组内的 Markdown 证据顺序；合成样本的两页 PDF 检查只证明对应排版路径。
- 结果正文保留责任主体、环境、实施阶段和来源限定，不用字数、版式或量化比例作为增强事实的理由。已完成的非量化交付仍是有价值的结果。
- 引用式材料使用冻结清单和内容指纹检测源变化。知识索引只负责导航、召回和回读，不能通过私人材料白名单赋予事实权威。
- 岗位、简历版本、审批、实际发送内容与回执必须可追溯；未知发送状态保留未知，不靠重试、换版本或切换通道制造成功。
- 外部访问、上传、正式投递及联系招聘方均服从当次明确授权；应用功能存在、测试通过或质量建议不授予这些权限。

## 当前未完成项

1. P0-026 仍为唯一 next 且在进行；已完成工程切片的边界与证据见上文。L7 已补齐正式质量判项的完整来源语境和精确采用身份，实际合成流程保住非量化与不借同事成果，R1.4 合法职责正控仅部分完成。下一片处理逐项覆盖、完成状态与缓存/修复一致性；不能由组名齐全推断全部所需判项齐全。有限模型失败记录保持，不新增业务脚本、平行账本或关键词分类；自动批量调度和正式模型 Agent 语义仍未产品化。
2. 继续原生页面验收，核对已接通的引文扩充、显式采纳/撤销、兄弟事实保留与错误恢复；不以组件测试替代实际窗口结果。
3. 在另行授权范围内完成真实 JD + Splash 的内部预览、正式简历与实际投递验收；当前工程验证不能代替这些结果。
4. 保持自动匹配的语义判断职责，不把每日岗位判断转交为逐岗位人工代审，也不以投递数量替代合适性与可追问的事实质量。

## 设计与历史机制记录

- [执行路线图](execution-roadmap.md)：当前 WIP、依赖与验收口径。
- [架构与执行路径审计](reports/architecture-and-execution-path-audit-20261107.md)：分层、入口和运行记录的历史根因。
- [语义匹配机制设计](reports/semantic-matching-mechanism-design-20261108.md)：判断与取证职责、引用与失败边界。
- [LLM 任务契约](reports/llm-task-contract-design-20261110.md)：结构化输出、能力边界与失败语义。
- [简历质量与证据推断设计](../openspec/changes/resume-quality-standard-and-evidence-inference/design.md)：正文实际采用的证据、完整命题与实测核定。
