"""Actual semantic producer/report consumer contract, not hand-normalized fixtures."""
import copy
import pytest
from tools.engines.matching import semantic_matching as m
from tools.engines.generation.fact_index import build_fact_index
from test_advisory_budget_counterexamples import _fixture, _client


def card():
    return {"id":"ec_0","title":"Service","role_scope":"Developer",
            "results":["Built Java services"],"artifacts":["Report"]}


def test_real_semantic_producer_write_load_maps_citations(tmp_path):
    kwargs=_fixture(tmp_path,count=1)
    client,_,_=_client()
    raw=m.run_semantic_matching(**kwargs,client=client)
    assert raw["requirements"][0]["id"]=="r1"
    path=tmp_path/"report.yaml"
    m.write_semantic_report(path,raw)
    loaded=m.load_semantic_report(path)
    index=build_fact_index([card()],{},loaded)
    fact=index.get("ec_0:results:0")
    assert fact.requirement_ids==("r1",)
    assert fact.support_weight==2


@pytest.mark.parametrize("requirement",[
    {"id":"r1"},{"requirement_id":"r1"},{"id":"r1","requirement_id":"r1"}
])
def test_current_and_unambiguous_legacy_ids_remain_supported(requirement):
    report={"requirements":[{**requirement,"text":"Java"}],
            "assessments":[{"requirement_id":"r1","status":"partial",
                            "citations":[{"fact_id":"ec_0:results:0"}]}]}
    fact=build_fact_index([card()],{},report).get("ec_0:results:0")
    assert fact.requirement_ids==("r1",)
    assert fact.support_weight==1


def test_conflicting_current_legacy_id_is_rejected_not_silently_retargeted():
    report={"requirements":[{"id":"r2","requirement_id":"r1","text":"Java"}],
            "assessments":[{"requirement_id":"r1","status":"supported",
                            "citations":[{"fact_id":"ec_0:results:0"}]}]}
    with pytest.raises(ValueError):
        build_fact_index([card()],{},report)


@pytest.mark.parametrize("scope", [True, None, 0, "false", "missing"])
def test_formal_loader_rejects_advisory_or_unproven_scope(tmp_path, scope):
    kwargs = _fixture(tmp_path, count=1)
    client, _, _ = _client()
    raw = m.run_semantic_matching(**kwargs, client=client, advisory=scope is True)
    if scope == "missing":
        raw.pop("advisory_scope")
    else:
        raw["advisory_scope"] = scope
    if scope is True:
        # A finished advisory report is still advisory.
        assert raw["completed_check_ids"] == ["r1"]
    path = tmp_path / "report.yaml"
    m.write_semantic_report(path, raw)
    with pytest.raises(ValueError, match="^semantic_formal_scope_required$"):
        m.load_semantic_report(path)


def test_incomplete_advisory_report_cannot_be_loaded_for_formal_output(tmp_path):
    kwargs = _fixture(tmp_path, count=1)
    client, _, _ = _client()
    def before(stage):
        if stage == "assess":
            raise ValueError("attempt_budget")

    raw = m.run_semantic_matching(**kwargs, client=client, advisory=True, before_model_call=before)
    assert raw["completed_check_ids"] == []
    path = tmp_path / "report.yaml"
    m.write_semantic_report(path, raw)
    with pytest.raises(ValueError, match="^semantic_formal_scope_required$"):
        m.load_semantic_report(path)


def test_insufficient_child_citation_has_no_formal_positive_weight_or_priority(tmp_path):
    from tools.engines.matching.semantic_review import aggregate_assessments, requirement_checks, select_cards, validate_assessments

    kwargs = _fixture(tmp_path, count=2)
    client, _, _ = _client()
    raw = m.run_semantic_matching(**kwargs, client=client)
    requirements = [{"id": "r1", "text": "Java development; production deployment"}]
    checks = requirement_checks(requirements)
    judgments = validate_assessments({"assessments": [
        {"requirement_id": "r1.c1", "status": "supported", "reason": "Java development recorded",
         "citations": [{"fact_id": "ec_0:results:0"}]},
        {"requirement_id": "r1.c2", "status": "insufficient", "reason": "Java development does not establish deployment",
         "citations": [{"fact_id": "ec_1:results:0"}]},
    ]}, raw["facts"], checks)
    raw.update(requirements=requirements, requirement_checks=checks, criterion_assessments=judgments,
               assessments=aggregate_assessments(requirements, checks, judgments))
    path = tmp_path / "report.yaml"
    m.write_semantic_report(path, raw)
    loaded = m.load_semantic_report(path)
    parent = loaded["assessments"][0]
    assert parent["status"] == "partial"
    assert parent["checks"][1]["citations"][0]["fact_id"] == "ec_1:results:0"
    rows = [card(), {**card(), "id": "ec_1"}]
    index = build_fact_index(rows, {}, loaded)
    assert index.get("ec_0:results:0").support_weight == 1
    assert index.get("ec_1:results:0").support_weight == 0
    assert select_cards([{"id": "ec_0", "score": 1}, {"id": "ec_1", "score": 10}],
                        loaded["assessments"], raw["facts"]) == ["ec_0"]


@pytest.mark.parametrize("children", [[], None, "invalid"])
def test_present_empty_or_malformed_children_do_not_fall_back_to_parent_union(children):
    report = {"requirements": [{"id": "r1"}],
              "assessments": [{"requirement_id": "r1", "status": "partial", "checks": children,
                               "citations": [{"fact_id": "ec_0:results:0"}]}]}
    assert build_fact_index([card()], {}, report).get("ec_0:results:0").support_weight == 0


def test_explicit_conflict_parent_is_not_a_positive_selection_even_with_supported_child():

    fact_id = "ec_0:results:0"
    report = {"requirements": [{"id": "r1"}], "facts": {fact_id: {"source_id": "ec_0"}},
              "assessments": [{"requirement_id": "r1", "status": "conflict",
                               "citations": [{"fact_id": fact_id}],
                               "checks": [{"status": "supported", "citations": [{"fact_id": fact_id}]},
                                          {"status": "conflict", "citations": [{"fact_id": fact_id}]}]}]}
    assert build_fact_index([card()], {}, report).get(fact_id).support_weight == 0


def test_preferred_card_promotion_does_not_turn_negative_only_fact_into_support():
    first, second, neutral = [f"ec_0:results:{i}" for i in range(3)]
    report = {
        "requirements": [{"id": "r1"}],
        "assessments": [{"requirement_id": "r1", "status": "partial",
                         "citations": [{"fact_id": first}, {"fact_id": second}],
                         "checks": [{"status": "supported", "citations": [{"fact_id": first}]},
                                    {"status": "insufficient", "citations": [{"fact_id": first},
                                                                                {"fact_id": second}]}]}],
    }
    index = build_fact_index([{**card(), "results": ["first", "second", "neutral"]}],
                             {}, report, preferred_card_ids=["ec_0"])
    assert index.get(first).requirement_ids == ("r1",)
    assert index.get(first).support_weight > 0
    assert index.get(second).requirement_ids == ()
    assert index.get(second).support_weight == 0
    assert index.get(neutral).support_weight == 3