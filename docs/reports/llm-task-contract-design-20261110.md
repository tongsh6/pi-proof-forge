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
- 查重确认 `semantic_matching` 是 `task_runner.execute` 的唯一生产消费者；其余直接 `post_json` 消费者继续使用“准备→发送”的单一组合入口，不声明已全部接入契约执行器。客户端的准备和发送方法分别由分批/执行器与直接入口消费，不保留 raw/prepared 双轨或旧预算签名。
- 初次与每次修复请求均先准备、再查预算，之后才允许进入发送回调和 `before_model_call`。初次超限为 `input_budget_exceeded`，尝试数 0；首请求已发但修复超限，只保留首请求的尝试，不能把构造反馈计作修复模型调用。不可序列化、循环输入或本地请求准备失败为现有原因集合中的 `invalid_request`，不能按大小 0 放行，也不按模型不可用、输出 JSON 错误或普通 transport 失败解释；构造失败不回发原输入。
- 分批与执行器使用同一完整请求口径。recall 的粗体积提示不作最终准入依据；assessment 沿现有选取顺序尝试完整 Fact/既有来源组合，以完整准备请求是否容纳作准入判断，不用独立差额估算代替检查。某独立 check 与必需档案语境无法构造合法请求或已超限时，它保持完整原文及自身的 invalid_request/input_budget 未评审原因，不参与其他可容纳 checks 的可选事实准入约束；不删除该要求，也不扩成另一套逐 check 事实窗口。候选试算不读写缓存，不增加命中、修复或调度计数。最终接受的批次保留对应 Request，直到首次发送；必要语境或单条完整事实过大时显式保留输入预算/未评审缺口，不裁掉原文或限定，不据“准备过”授予完成或覆盖。
- 原缓存继续承担结果复用并运行原业务 validator；命中结果不调用 HTTP。缓存身份由实际接受的请求 URL、body 与既有输入版本共同确定，不能使用随后重读的 context 或注入前 payload 表示另一份请求；不保留旧 key 的迁移双轨，不新增缓存账本或因本片清缓存。请求预算约束待发请求，不把有效缓存复用算作新发送；本地输入失败不设置 transport 的 budget_exhausted，也不因此授予续审资格。
- 本片保留任务受控修复次数、输出预算与 BoundedLocal 的实际 HTTP 额度、超时、localhost/重定向约束。TaskRun.attempts 表达逻辑调用尝试，BoundedLocal.model_calls 表达实际 HTTP 尝试，两者不能混称。provider/部署能力配置中的既有模型名或端点特例另片治理，本片仅完整计入其当前注入参数。

独立验收先复现 10 个业务反例，修复后保留原生 schema、无 schema、显式格式、中文/转义、完整 Fact、稳定分批、缓存校验和本地 transport 约束正控；审查补出的局部准备失败反例也已转绿。全量与纯合成真实 Router→Splash→内部预览通过，实际 matching 请求按完整逻辑 JSON 字符计量均未超过原上限。详细结果与未完成边界见 [Project Ledger](../project-ledger.md)；不以辅助脚本或孤立模型样本替代应用验收，也不据有限合成规模宣称所有直接调用已有契约预算。

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
