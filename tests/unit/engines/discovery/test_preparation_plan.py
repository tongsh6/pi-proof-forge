"""每日准备只读计划：选的是待验证工作，不是发送授权。"""
from copy import deepcopy
from importlib.util import find_spec

import pytest


def plan(profiles, maximum=3, attempted_keys=()):
    name = "tools.engines.discovery.preparation_plan"
    assert find_spec(name) is not None, "每日准备选择器尚未实现"
    from tools.engines.discovery.preparation_plan import build_preparation_plan
    return build_preparation_plan(profiles, maximum, attempted_keys)


def profile(pid, state="promising", **changes):
    item = {
        "job_profile_id": pid, "company": "Example", "title": pid,
        "preparation_key": f"sealed-key-{pid}",
        "status": "active", "source_jd": "完整 JD：Java 服务",
        "platform": "liepin", "platform_job_type": "2", "platform_job_id": pid,
        "source_url": f"https://www.liepin.com/job/{pid}.shtml",
        "native_pdf_delivery": {"supported": True, "reason": ""},
        "fit_precheck": {"state": state, "rank": -100, "source": "rule"},
    }
    item.update(changes)
    return item


@pytest.mark.parametrize("maximum", [0, 4, -1, True, False, 1.0, "2", None])
def test_maximum_is_exact_integer_between_one_and_three(maximum):
    with pytest.raises(ValueError, match="invalid_preparation_maximum"):
        plan([], maximum)


def test_orders_by_state_not_supplied_rank_and_does_not_mutate():
    rows = [profile("1"), profile("2", "consider"), profile("3", "recommended"),
            profile("4", "recommended")]
    before = deepcopy(rows)
    result = plan(rows, 3)
    assert [x["job_profile_id"] for x in result["selected"]] == ["3", "4", "2"]
    assert result["deferred"][0]["reason"] == "preparation_limit"
    assert result["selected"][0]["reason"] == "semantic_review_required"
    assert result["selected"][0]["channel"] == "generated_pdf"
    assert result["maximum"] == 3 and result["shortfall"] == 0
    assert result["send_ready"] is False
    assert rows == before


def test_shortfall_does_not_promote_low_unknown_or_hold():
    result = plan([profile("1"), profile("2", "low"), profile("3", "unknown"),
                   profile("4", "hold"), profile("5", "caution")])
    assert [x["job_profile_id"] for x in result["selected"]] == ["1"]
    assert result["shortfall"] == 2
    assert len(result["deferred"]) == 4
    assert all(x["reason"] == "fit_not_promising" for x in result["deferred"])


@pytest.mark.parametrize("change,reason", [
    ({"status": "draft"}, "profile_review_required"),
    ({"source_jd": "  "}, "jd_missing"),
    ({"native_pdf_delivery": {"supported": False, "reason": "job_review_required"}},
     "job_review_required"),
    ({"native_pdf_delivery": {"supported": False, "reason": "manual_import"}},
     "manual_import"),
    ({"native_pdf_delivery": {}}, "channel_unavailable"),
    ({"preparation_key": ""}, "job_identity_missing"),
])
def test_hard_prerequisites_are_explained_without_losing_rows(change, reason):
    result = plan([profile("1", **change)])
    assert not result["selected"]
    assert result["deferred"][0]["reason"] == reason
    assert result["shortfall"] == 3


def test_platform_resume_route_is_retained_without_claiming_pdf_support():
    result = plan([profile("1", native_pdf_delivery={
        "supported": False, "reason": "platform_default_only"
    })])
    assert result["selected"][0]["channel"] == "platform_default"
    assert result["send_ready"] is False


def test_same_identity_uses_better_fit_but_keeps_duplicate_in_deferred():
    rows = [profile("old", "promising", preparation_key="shared-key"),
            profile("new", "recommended", preparation_key="shared-key")]
    result = plan(rows)
    assert [x["job_profile_id"] for x in result["selected"]] == ["new"]
    assert result["deferred"][0]["job_profile_id"] == "old"
    assert result["deferred"][0]["reason"] == "duplicate_job"


def test_any_attempted_identity_is_excluded_regardless_of_fit_or_version():
    result = plan([profile("123", "recommended"), profile("456")],
                  attempted_keys=("sealed-key-123",))
    assert [x["job_profile_id"] for x in result["selected"]] == ["456"]
    assert result["deferred"][0]["reason"] == "already_attempted"


def test_adapter_identity_is_authoritative_without_rederiving_urls():
    first = profile("one", preparation_key="shared-url-key", source_url="https://WWW.liepin.com/job/12.shtml?track=1#top")
    second = profile("two", preparation_key="shared-url-key", source_url="https://www.liepin.com/job/12.shtml?track=2")
    result = plan([first, second])
    assert len(result["selected"]) == 1
    assert result["deferred"][0]["reason"] == "duplicate_job"
    attempted = plan([first], attempted_keys=("shared-url-key",))
    assert attempted["deferred"][0]["reason"] == "already_attempted"


def test_same_numeric_id_on_different_job_type_is_not_merged():
    result = plan([profile("one", platform_job_id="12"),
                   profile("two", platform_job_id="12", platform_job_type="1")])
    assert len(result["selected"]) == 2


def test_empty_input_reports_shortfall_without_ready_claim():
    assert plan([], 1) == {"maximum": 1, "selected": [], "deferred": [],
                           "shortfall": 1, "send_ready": False}
