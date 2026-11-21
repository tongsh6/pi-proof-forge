# LLM 任务契约：从「容错补丁」到「能力前置校验」

## 1. 问题域

系统有 5 类 LLM 任务，每类都直接依赖模型能力：

| 任务 | 入口 | 输出契约 | 对模型的要求 |
|---|---|---|---|
| 语义评审 | `semantic_matching.py` | 卡相关性 + 事实引用 | 结构化 JSON + **精确转录事实编号** |
| 方向评估 | `job_preferences.assess_direction` | aligned/needs_review/excluded | JSON + 引用 JD 原文 |
| 画像草稿 | `jobs_profiles.generate_profile_draft` | must_have/keywords | JSON + 语义归纳 |
| 证据提炼与复审 | `evidence.generateDraft` / `evidence.saveDraft`（`evidence_draft.py`） | 未批准草稿 + 精确来源，复审后保存 | JSON + 原文可定位；定位不等于发生性核定 |
| 质量评估 | `quality_report.py` | 分层评分 | JSON + 判断 |

模型不稳定表现为 6 种，当前**分散在 95 处 `except ValueError`/`except Exception`** 里各自处理：

1. 结构化输出漂移（非法 JSON）
2. 标识转录错误（fact_id 不存在）
3. 引用缺失（正分结论无引用）
4. 输出截断（`finish_reason=length`）
5. 服务不可用（超时 / HTTP 400 / 连接断开）
6. 速度不可接受（单批 >10 分钟）

## 2. 现有方案的根本缺陷

不是"没处理失败"，而是**处理方式把失败当异常，而不是当契约的一部分**：

- 每个任务各自决定"失败后怎么办"，策略不一致（有的重试、有的降级、有的整批失败）；
- 失败原因没有统一语义，`semantic_all_cards_degraded` 这类错误码无法回答"是模型不会、还是服务挂了"；
- **最关键**：把"模型不擅长的事"写进任务契约（例如要求模型逐字复制 20 位带冒号的事实编号），然后在失败处层层打补丁。

实测证据：`iq3_s` 能写出准确的相关性分析，却抄不对 `fact_id`，导致 114 卡全部降级；LM Studio 27B 能抄对，但服务不稳定，同一批任务在长 JD 上 HTTP 400。两种失败性质完全不同，却走同一套降级路径。

## 3. 设计：三层职责分离

### 第一层：能力契约（Capability Contract）

每个 LLM 任务声明它对模型的最低能力要求，而不是在失败处猜：

```python
@dataclass(frozen=True)
class Capability:
    needs_json: bool               # 必须输出严格 JSON
    needs_exact_transcript: bool   # 必须逐字复制输入中的标识（高难度，尽量不用）
    max_output_tokens: int         # 单次输出预算
    max_input_chars: int           # 完整已准备请求的逻辑 JSON 字符预算；超限拆批或明确拒绝

@dataclass(frozen=True)
class TaskContract:
    name: str
    capability: Capability
    on_unavailable: Literal["block", "degrade", "skip"]
    degrade_note: str
```

**设计约束**：`needs_exact_transcript=True` 是最后手段。任何任务若能通过"任务分解"消掉这个要求，就不该保留它。


### 输入预算执行（切片 L2，限定工程范围已完成）

`Capability.max_input_chars` 约束每次实际准备发送的完整请求，单位为逻辑 JSON 字符：从已序列化的 UTF-8 `Request.data` 解码 JSON 后，以 `json.dumps(..., ensure_ascii=False)` 计长。该值包括任务消息、共同语境、输出 schema、provider 参数及消息中内层 JSON 的转义；不是 tokenizer token 数、UTF-8 字节或 wire 中 Unicode 转义后的字节数。保留现有 24,000 上限，不通过调大上限掩盖遗漏。

- 请求准备只由 `LLMClient` 完成，复用标准库 `urllib.request.Request` 承载实际 URL、headers 与已序列化 body，不引入 Prepared DTO、`prepared=True`、持久字段或第二预算台账。准备不发 HTTP、不修改调用方数据；发送沿既有 `_open_with_retry`，不重新注入或重建内容。本次预算通过的同一请求对象必须是送入 transport 的对象，准备后的 URL/body 不得由预算、缓存或发送消费者改写。
- L2 实施时查重确认 `semantic_matching` 是 `task_runner.execute` 的唯一生产消费者；其余直接 `post_json` 消费者继续使用“准备→发送”的单一组合入口，不声明已全部接入契约执行器。客户端的准备和发送方法分别由分批/执行器与直接入口消费，不保留 raw/prepared 双轨或旧预算签名。
- 初次与每次修复请求均先准备、再查预算，之后才允许进入发送回调和 `before_model_call`。初次超限为 `input_budget_exceeded`，尝试数 0；首请求已发但修复超限，只保留首请求的尝试，不能把构造反馈计作修复模型调用。不可序列化、循环输入或本地请求准备失败为现有原因集合中的 `invalid_request`，不能按大小 0 放行，也不按模型不可用、输出 JSON 错误或普通 transport 失败解释；构造失败不回发原输入。
- 分批与执行器使用同一完整请求口径。recall 的粗体积提示不作最终准入依据；assessment 沿现有选取顺序尝试完整 Fact/既有来源组合，以完整准备请求是否容纳作准入判断，不用独立差额估算代替检查。某独立 check 与必需档案语境无法构造合法请求或已超限时，它保持完整原文及自身的 invalid_request/input_budget 未评审原因，不参与其他可容纳 checks 的可选事实准入约束；不删除该要求，也不扩成另一套逐 check 事实窗口。候选试算不读写缓存，不增加命中、修复或调度计数。最终接受的批次保留对应 Request，直到首次发送；必要语境或单条完整事实过大时显式保留输入预算/未评审缺口，不裁掉原文或限定，不据“准备过”授予完成或覆盖。
- 原缓存继续承担结果复用并运行原业务 validator；命中结果不调用 HTTP。缓存身份由实际接受的请求 URL、body 与既有输入版本共同确定，不能使用随后重读的 context 或注入前 payload 表示另一份请求；不保留旧 key 的迁移双轨，不新增缓存账本或因本片清缓存。请求预算约束待发请求，不把有效缓存复用算作新发送；本地输入失败不设置 transport 的 budget_exhausted，也不因此授予续审资格。
- 本片保留任务受控修复次数、输出预算与 BoundedLocal 的实际 HTTP 额度、超时、localhost/重定向约束。TaskRun.attempts 表达逻辑调用尝试，BoundedLocal.model_calls 表达实际 HTTP 尝试，两者不能混称。provider/部署能力配置中的既有模型名或端点特例另片治理，本片仅完整计入其当前注入参数。

独立验收先复现 10 个业务反例，修复后保留原生 schema、无 schema、显式格式、中文/转义、完整 Fact、稳定分批、缓存校验和本地 transport 约束正控；审查补出的局部准备失败反例也已转绿。全量与纯合成真实 Router→Splash→内部预览通过，实际 matching 请求按完整逻辑 JSON 字符计量均未超过原上限。详细结果与未完成边界见 [Project Ledger](../project-ledger.md)；不以辅助脚本或孤立模型样本替代应用验收，也不据有限合成规模宣称所有直接调用已有契约预算。

### 正式质量判项接入（切片 L6，限定工程与合成应用验收完成）

查重已确认 `run.quick.start` 经正式 matching/generation/evaluation 消费质量判项，`quality_report` 是现有编排责任，`llm_judge` 是领域判项校验责任，`quality_judge_cache` 是唯一结果缓存，`TaskRunner` 与共享 `LLMClient` 已能承担完整请求准入和发送。guided 的零模型合同保持；仅由 CLI 注入的旧 Agent 引擎不在本片另建语义流程。

- 将现质量判项登记为实际由 `TaskRunner.execute` 消费的任务，保留输出 6,000 tokens、完整准备请求 24,000 逻辑 JSON 字符及一次受控修复。初次与修复均交由共享客户端准备，同一 `Request` 用于预算、身份及发送。修复只请求未完成判项组，不能重发构造失败的原输入，也不能覆盖首轮已核验的完整组。任务次数按实际进入发送回调计，修复预算/构造失败不增加模型次数；共享 transport 重试的物理 HTTP 次数单独观测。
- 缓存键在请求准备后生成，绑定实际 URL/body、当前正文/目标、原输入版本和判项协议版本；共同语境/provider/thinking 通过实际 body 参与，不随后重读 context 拼另一份身份，不包含认证 headers。沿现缓存字段与原子写入保存，仅接受当前版本，不留旧 key 或双格式回退，不清理用户缓存。
- 每次缓存命中都通过当前正文、JD 项、卡与引用的同一领域校验，并复核完整性；持久化的 `judged_sections`、默认空数组或合法 JSON 结构本身不能授予已评权威。无效/不完整缓存按未命中处理。相同实际请求与同版输入的有效缓存为零 HTTP；预算约束待发送请求，不把有效复用算作新发送。严格 JSON 对象解析复用现共同 parser，重复键不能按最后值消解。
- 共享任务执行器按实际响应协议处理 `finish_reason=length`：即使内容恰好闭合为合法 JSON，也属于 `output_truncated`，不得进入领域校验授予完成或写缓存；沿原最多两次尝试受控重试，后续正常完整响应可采纳，耗尽保持未完成。不按模型名称或输出措辞判断截断，不调大输出上限；该边界归共同执行器，质量业务不维护第二份协议判断。
- 判项编排仅合并当轮请求且通过校验的完整组；剩余组继续 pending。修复正常缺项、超预算、构造失败或传输失败，均保留首轮合法组但不缓存整份结果；首轮没有合法组时保持 unavailable。原 `TaskRun` 的实际尝试/耗时和稳定原因沿现 stdout/判项诊断表达，不调用会虚构尝试数的聚合捷径，不新增持久状态或公开 API 字段。
- 上述降级只处理模型分析可用性。实际卡、材料、职业档案、岗位及正式语义报告仍沿 H 的实际读取与发布前校验；缓存或 partial 不解除来源失效阻断，不回写旧报告。已核实量化和非量化结果仍由同一 trace/结果核定承责，judge 不补授 R3.2 信用。质量待判不提升为新的人工批准门禁。

独立质量判项首组 12 failed / 1 passed、追加两反例 2 failed，最终原 15 例全绿；共享截断另两例 RED 转绿。实际 evaluation_flow 的来源变更仍拒绝发布，原报告字节保持；有效缓存、真实结果与 partial 正控均执行。最终全量 3036 passed、1 skipped、101 subtests passed（56.90 秒），工程门禁通过。复用已由 API 核定的纯合成来源，实际 App→Splash 经 11 RPC、5 次本机 HTTP 完成正式 pipeline；质量仅 1 次请求、完整 5580 字符、五组完成，量化 0.5、auto_pass=false。详见 Project Ledger；此请求预算不证明 judge 已读取全部原卡，既有按长度/前五条摘要的输入损失继续另片处理，也不替代原生或真实 JD/正式件验收。

### 第二层：任务分解（让模型只做它擅长的）

职责按能力分配，而不是按"谁方便"分配：

| 子任务 | 执行者 | 理由 |
|---|---|---|
| 语义判断（卡是否相关） | 模型 | 语义理解是模型强项 |
| 摘录支撑原文片段 | 模型 | 自然语言摘录比抄 ID 容易一个数量级 |
| 片段 → 事实编号的定位 | 程序 | 精确匹配是程序强项，且可测试 |
| 编号 → 引用原文的转录 | 程序 | 保证引用天然可核验、无伪造空间 |
| 结论合成（supported/partial） | 程序 | 确定性规则，可单测 |

语义评审因此改为：模型输出 `{card_id, score, reason, evidence_quotes: [片段]}`，程序用 `locate_fact_by_quote` 定位。**定位失败不是异常**，而是"该条结论不可核实"这一明确状态。

### 第三层：确定性合成（确定性优先于概率性）

凡是能用规则算的，不交给模型：

- 引用原文 = 程序从事实库转录（模型永不生成引用文本）；
- 卡相关性排序 = 程序按分数排序（不让模型排序）；
- 要求覆盖度 = 程序统计（不让模型数数）。

### 第四层：状态语义（失败是状态，不是异常）

每个任务输出 `TaskOutcome`：

```python
@dataclass(frozen=True)
class TaskOutcome:
    status: Literal["complete", "partial", "unavailable"]
    reason_code: str          # 稳定的机器可读原因
    detail: str               # 人类可读说明
    result: Any | None
```

下游按状态决策，而不是捕获异常：

- `complete`：正常使用；
- `partial`：使用已完成部分，缺口显式标注（例如 8 条要求只有 5 条评出 → fit 标记为 partial，不阻断投递）；
- `unavailable`：按契约的 `on_unavailable` 处理（block 阻断 / degrade 降级 / skip 跳过）。

### 第五层：能力探测（用前验证，不靠事后重试）

```python
def probe_model(client, model, capability) -> ProbeResult
```

用最小样本（一次 20 token 的请求）验证模型是否满足能力，结果按 `model + capability` 指纹缓存。不使用"先跑，失败了再换模型"的模式——那会让失败发生在用户等待十几分钟之后。

## 4. 与"容错"的区别

| 维度 | 容错补丁（现状） | 任务契约（本设计） |
|---|---|---|
| 失败发生点 | 任何地方，各自 try/except | 契约边界，统一状态 |
| 模型做错事 | 重试 / 降级 / 猜 | **设计上不让它做这件事** |
| 失败语义 | 异常码，含义靠猜 | 状态 + 稳定 reason_code |
| 探测 | 无 | 用前探测，按能力选模型 |
| 可测试性 | 只能测 happy path | 状态机可穷举测试 |

## 5. 实施路径（分批，可独立 review）

- **批次 1**：`task_contract.py`（契约与状态类型）+ `quote_locator.py`（已完成）+ 语义评审接入"摘录→定位"，删除 `needs_exact_transcript` 依赖。
- **批次 2**：`probe.py` 能力探测 + 运行前选模型（语义评审优先用能通过探测的模型）。
- **批次 3**：其余 4 类任务接入统一契约，删除各自分散的 try/except。
- **批次 4**：运行记录与 UI 展示 `TaskOutcome.status`，让"部分完成"对用户可见。

## 6. 验收标准

1. 语义评审在 `iq3_s`（不能抄 ID、能摘录原文）上产出 `partial` 而非 `unavailable`；
2. 任一 LLM 任务的失败都能回答"是模型能力不足，还是服务不可用"；
3. 不存在"模型输出被当作引用原文"的代码路径；
4. 每条降级结论都有稳定 `reason_code`，可在报告中列出。

## 7. 实证（批次 1 完成后）

同一份 2 卡样本、同一个 `iq3_s` 模型：

| 指标 | 改造前（要求模型抄 fact_id） | 改造后（模型摘录 + 程序定位） |
|---|---|---|
| 卡覆盖 | 0/2（整批降级） | **2/2** |
| 降级批次 | 1（全部） | **0** |
| 受控修复 | — | 1 次（结构问题，修复后成功） |
| 错误码 | `semantic_invalid_citation` | 无 |

同一个模型、同一份证据，只是把「精确转录」从模型职责里去掉，结果从"完全不可用"
变成"完全可用"。这就是"理顺前置逻辑"与"容错补丁"的区别：补丁让失败变得可承受，
理顺让失败不发生。

执行器（`infra/llm/task_runner.py`）已接入语义评审，契约从此进入执行路径：
预算超限直接拒绝、服务不可用不重试、结构性错误受控重试一次、每次执行产出
带原因码的 `TaskRun`。
