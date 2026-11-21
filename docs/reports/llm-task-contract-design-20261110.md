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
    max_input_chars: int           # 单次输入预算（超了必须拆批）

@dataclass(frozen=True)
class TaskContract:
    name: str
    capability: Capability
    on_unavailable: Literal["block", "degrade", "skip"]
    degrade_note: str
```

**设计约束**：`needs_exact_transcript=True` 是最后手段。任何任务若能通过"任务分解"消掉这个要求，就不该保留它。

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
