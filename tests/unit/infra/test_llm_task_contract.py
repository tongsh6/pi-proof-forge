"""任务契约：能力声明、失败状态与原因码必须可校验。"""
import pytest

from tools.infra.llm.task_contract import (
    EVIDENCE_EXTRACTION,
    REASON_INVALID_JSON,
    REASON_PARTIAL_COVERAGE,
    REASON_QUOTE_UNRESOLVED,
    SEMANTIC_MATCHING,
    Capability,
    TaskContract,
    TaskOutcome,
    complete,
    default_registry,
    partial,
    unavailable,
)


def test_semantic_matching_no_longer_requires_exact_transcript():
    # 引用定位由程序承担，模型不再需要抄写 fact_id。
    assert SEMANTIC_MATCHING.capability.needs_exact_transcript is False


def test_evidence_extraction_still_declares_transcript_requirement():
    # 提炼要求事实必须在原文可定位，是已知的高要求任务，显式登记而不是隐藏。
    assert EVIDENCE_EXTRACTION.capability.needs_exact_transcript is True


def test_invalid_capability_budget_rejected():
    with pytest.raises(ValueError):
        Capability(max_output_tokens=0)


def test_degrade_contract_requires_note():
    with pytest.raises(ValueError):
        TaskContract(name="t", capability=Capability(), on_unavailable="degrade")


def test_non_complete_outcome_requires_reason():
    with pytest.raises(ValueError):
        TaskOutcome(status="partial")
    with pytest.raises(ValueError):
        TaskOutcome(status="unavailable", reason_code="")


def test_unknown_reason_code_rejected():
    with pytest.raises(ValueError):
        TaskOutcome(status="partial", reason_code="something_new", detail="x")


def test_outcome_helpers_produce_expected_status():
    assert complete({"a": 1}).status == "complete"
    assert complete({"a": 1}).usable is True
    part = partial(reason_code=REASON_QUOTE_UNRESOLVED, detail="2 条引用无法定位")
    assert part.status == "partial" and part.usable is True
    dead = unavailable(SEMANTIC_MATCHING, reason_code=REASON_INVALID_JSON, detail="模型输出不是 JSON")
    assert dead.status == "unavailable" and dead.usable is False
    assert dead.detail == "模型输出不是 JSON"


def test_registry_contains_all_registered_tasks():
    registry = default_registry()
    assert set(registry.contracts) == {
        "semantic_matching",
        "quality_judge",
        "background_redundancy",
        "direction_review",
        "job_profile_draft",
        "evidence_extraction",
    }
    with pytest.raises(ValueError):
        registry.get("unknown_task")
