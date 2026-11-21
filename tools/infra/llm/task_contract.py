"""LLM 任务契约：把「模型能力」与「失败语义」变成可声明、可校验的类型。

设计见 docs/reports/llm-task-contract-design-20261110.md。要点：

1. 任务先声明能力要求（`Capability`），再决定用什么模型，而不是失败后猜；
2. `needs_exact_transcript=True` 是最后手段——能通过任务分解消掉就消掉；
3. 失败是状态（`TaskOutcome`），不是散落各处的异常捕获；
4. 下游按状态决策，稳定 `reason_code` 让"模型不会"与"服务挂了"可区分。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TaskStatus = Literal["complete", "partial", "unavailable"]
UnavailableAction = Literal["block", "degrade", "skip"]

# 稳定的不可用原因；新增原因必须在这里登记，禁止临时字符串。
REASON_MODE_MISSING = "model_unavailable"
REASON_INVALID_JSON = "invalid_json"
REASON_INVALID_REQUEST = "invalid_request"
REASON_TRANSCRIPT_FAILURE = "transcript_failure"
REASON_OUTPUT_TRUNCATED = "output_truncated"
REASON_TIMEOUT = "timeout"
REASON_CAPABILITY_PROBE_FAILED = "capability_probe_failed"
REASON_PARTIAL_COVERAGE = "partial_coverage"
REASON_QUOTE_UNRESOLVED = "quote_unresolved"
REASON_INPUT_BUDGET_EXCEEDED = "input_budget_exceeded"

KNOWN_REASONS = frozenset(
    {
        REASON_MODE_MISSING,
        REASON_INVALID_JSON,
        REASON_INVALID_REQUEST,
        REASON_TRANSCRIPT_FAILURE,
        REASON_OUTPUT_TRUNCATED,
        REASON_TIMEOUT,
        REASON_CAPABILITY_PROBE_FAILED,
        REASON_PARTIAL_COVERAGE,
        REASON_QUOTE_UNRESOLVED,
        REASON_INPUT_BUDGET_EXCEEDED,
    }
)


@dataclass(frozen=True)
class Capability:
    """任务对模型的最低能力要求。"""

    needs_json: bool = True
    # 是否要求模型逐字复制输入中的标识（如 fact_id）。高难度，优先用任务分解消掉。
    needs_exact_transcript: bool = False
    max_output_tokens: int = 4096
    # 完整已准备请求的逻辑 JSON 字符，不是 token 或 UTF-8/wire 字节。
    max_input_chars: int = 24_000

    def __post_init__(self) -> None:
        if self.max_output_tokens < 1 or self.max_input_chars < 1:
            raise ValueError("invalid_capability_budget")


@dataclass(frozen=True)
class TaskContract:
    """一个 LLM 任务的能力要求与不可用时的处理方式。"""

    name: str
    capability: Capability
    on_unavailable: UnavailableAction = "degrade"
    degrade_note: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("task_name_required")
        if self.on_unavailable not in {"block", "degrade", "skip"}:
            raise ValueError("invalid_unavailable_action")
        if self.on_unavailable == "degrade" and not self.degrade_note.strip():
            raise ValueError("degrade_note_required")


@dataclass(frozen=True)
class TaskOutcome:
    """任务结果：状态 + 稳定原因码 + 人类可读说明。"""

    status: TaskStatus
    reason_code: str = ""
    detail: str = ""
    result: Any = None

    def __post_init__(self) -> None:
        if self.status not in {"complete", "partial", "unavailable"}:
            raise ValueError("invalid_task_status")
        if self.reason_code and self.reason_code not in KNOWN_REASONS:
            raise ValueError(f"unknown_reason_code:{self.reason_code}")
        if self.status != "complete" and not self.reason_code:
            raise ValueError("non_complete_outcome_requires_reason")

    @property
    def usable(self) -> bool:
        return self.status in {"complete", "partial"}


def unavailable(contract: TaskContract, *, reason_code: str, detail: str = "") -> TaskOutcome:
    return TaskOutcome(
        status="unavailable",
        reason_code=reason_code,
        detail=detail or contract.degrade_note or reason_code,
        result=None,
    )


def partial(*, reason_code: str = REASON_PARTIAL_COVERAGE, detail: str = "", result: Any = None) -> TaskOutcome:
    return TaskOutcome(status="partial", reason_code=reason_code, detail=detail, result=result)


def complete(result: Any) -> TaskOutcome:
    return TaskOutcome(status="complete", result=result)


# ---- 已登记的任务契约（新增 LLM 任务必须在这里登记） ----

SEMANTIC_MATCHING = TaskContract(
    name="semantic_matching",
    capability=Capability(
        needs_json=True,
        needs_exact_transcript=False,
        max_output_tokens=6144,
        # 保留 24k 上限，按完整已准备请求的逻辑 JSON 字符准入；
        # 共同语境、schema 与 provider 参数均计入，不以注入前体量代替。
        max_input_chars=24_000,
    ),
    on_unavailable="degrade",
    degrade_note="语义评审不可用时回退规则模式，简历仍可生成但与 JD 对位精度下降",
)

BACKGROUND_REDUNDANCY = TaskContract(
    name="background_redundancy",
    capability=Capability(
        needs_json=True,
        needs_exact_transcript=False,
        max_output_tokens=2048,
        max_input_chars=24_000,
    ),
    on_unavailable="degrade",
    degrade_note="背景冗余核验不可用时保留完整背景，不改动已选行动和成果",
)

DIRECTION_REVIEW = TaskContract(
    name="direction_review",
    capability=Capability(needs_json=True, needs_exact_transcript=False, max_output_tokens=1024),
    on_unavailable="degrade",
    degrade_note="方向评估降级为 unknown，不阻断主评审",
)

JOB_PROFILE_DRAFT = TaskContract(
    name="job_profile_draft",
    capability=Capability(needs_json=True, needs_exact_transcript=False, max_output_tokens=2048),
    on_unavailable="skip",
    degrade_note="画像草稿生成不可用时保留手工填写路径",
)

EVIDENCE_EXTRACTION = TaskContract(
    name="evidence_extraction",
    capability=Capability(needs_json=True, needs_exact_transcript=True, max_output_tokens=4096),
    on_unavailable="skip",
    degrade_note="证据提炼不可用时保留规则模式的项目规模卡",
)


@dataclass(frozen=True)
class ContractRegistry:
    """任务名 → 契约；用于运行时查询与文档生成。"""

    contracts: dict[str, TaskContract] = field(default_factory=dict)

    def register(self, contract: TaskContract) -> None:
        if contract.name in self.contracts:
            raise ValueError(f"duplicate_contract:{contract.name}")
        self.contracts[contract.name] = contract

    def get(self, name: str) -> TaskContract:
        try:
            return self.contracts[name]
        except KeyError:
            raise ValueError(f"unregistered_task:{name}") from None


def default_registry() -> ContractRegistry:
    registry = ContractRegistry()
    for contract in (
        SEMANTIC_MATCHING,
        BACKGROUND_REDUNDANCY,
        DIRECTION_REVIEW,
        JOB_PROFILE_DRAFT,
        EVIDENCE_EXTRACTION,
    ):
        registry.register(contract)
    return registry
