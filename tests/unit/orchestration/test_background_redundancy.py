"""Current generation flow, real source bindings, and only the final LLM transport controlled.

These tests validate application wiring and bounded decisions, not a model's semantic accuracy.
"""
from dataclasses import replace
import io
import json
from urllib.parse import urlsplit

import pytest

from tests.unit.engines.test_targeted_generation import generation_inputs
from tests.unit.engines.test_generation_engines import write_reviewed_result_sources
from tools.engines.generation.resume_renderer import load_cards
from tools.engines.matching.semantic_matching import (
    load_semantic_report, run_semantic_matching, write_semantic_report,
)
from tools.infra.llm.client import LLMClient
from tools.infra.persistence.review_snapshot import read_generation_trace
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.orchestration.evaluation_flow import EvaluationFlowConfig, run_evaluation_flow
from tools.orchestration.generation_flow import GenerationFlowConfig, run_generation_flow


BASE_URL = "http://127.0.0.1:18041/v1"
MEASURED_RESULT = "在隔离回归环境中，接口 P95 从 200ms 降至 120ms。"
MEASURED_CONTEXT = "隔离回归环境中的接口响应时间有所改善。"
NONQUANT_RESULT = "在隔离回归环境中完成全部接口验收，并归档可复查的验收记录。"
NONQUANT_CONTEXT = "隔离回归环境中的接口验收已经完成。"


def _write_card(inputs, card_id, *, context=MEASURED_CONTEXT, actions=None, results=None,
                measurement_quotes=None, excluded_results=()):
    """Extend the existing explicit reviewed-source fixture; no reviewer is under test."""
    _, _, evidence, _, output = inputs
    actions = actions if actions is not None else ["实现交易接口的请求校验与异常处理机制"]
    results = results if results is not None else [MEASURED_RESULT]
    quotes = measurement_quotes if measurement_quotes is not None else {0: MEASURED_RESULT}
    values = {
        "id": card_id, "title": "交易接口验收" if card_id == "ec-1" else "库存接口验收",
        "time_range": "2024-01 ~ 2024-06", "role_scope": "负责接口实现与联调",
        "context": context, "actions": actions, "results": results,
        "stack": ["Java"], "artifacts": ["合成验收记录"],
    }
    lines = []
    for key, value in values.items():
        if isinstance(value, list):
            lines.append(key + ":")
            lines.extend("  - " + json.dumps(item, ensure_ascii=False) for item in value)
        else:
            lines.append(key + ": " + json.dumps(value, ensure_ascii=False))
    path = evidence / (card_id + ".yaml")
    path.write_text("\n".join(lines) + "\n")
    sources = write_reviewed_result_sources(path, quotes, material_dir=output.parent / "materials")
    if excluded_results:
        # A deliberately nonpersonal scope fixture, with no result verdict granting personal credit.
        doc = parse_simple_yaml(path.read_text())
        reviewed = json.loads(doc["scalars"]["reviewed_facts_json"])
        for row in reviewed["fact_scope_v1"]:
            if row["index"] in excluded_results:
                row["attribution"] = "teammate"
                row.pop("result_review")
        old_line, = [line for line in path.read_text().splitlines()
                     if line.startswith("reviewed_facts_json:")]
        new_line = "reviewed_facts_json: " + json.dumps(json.dumps(reviewed), ensure_ascii=False)
        path.write_text(path.read_text().replace(old_line, new_line))
        view, = load_cards(evidence, [card_id])
        assert {f"{card_id}:results:{index}" for index in excluded_results}.issubset(
            view["personal_claim_exclusions"])
    return path, sources


def _transport(monkeypatch, respond):
    requests = []

    def urlopen(request, *args, **kwargs):
        assert urlsplit(request.full_url).hostname == "127.0.0.1"
        payload = json.loads(request.data)
        data = json.loads(next(message["content"] for message in payload["messages"]
                               if message["role"] == "user"))
        requests.append({"request": request, "payload": payload, "data": data})
        response = respond(data)
        content = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        wire = {"choices": [{"message": {"content": content}}]}
        return io.BytesIO(json.dumps(wire, ensure_ascii=False).encode("utf-8"))

    monkeypatch.setattr("tools.infra.llm.client.request.urlopen", urlopen)
    return requests


def _review(inputs, monkeypatch, *, positive_ids=None):
    """Produce the current semantic report through its real parser, validator, and source capture."""
    profile, job, evidence, report, output = inputs
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_THINKING", "default")
    for key in ("LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "OPENAI_MODEL", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    positive = set(positive_ids or [path.stem + ":actions:0" for path in evidence.glob("*.yaml")])

    def reply(data):
        facts = data["facts"]

        def citations(source=None):
            return [{"fact_id": fact_id, "quote": fact["text"]}
                    for fact_id, fact in facts.items()
                    if fact_id in positive and fact.get("candidate_support") is not False
                    and (source is None or fact_id.startswith(source + ":"))]

        if data["stage"] == "recall":
            return {"cards": [{
                "id": card["id"], "score": 90, "reason": "合成岗位引文",
                "requirement_ids": [requirement["id"] for requirement in data["requirements"]],
                "citations": citations(card["id"]),
            } for card in data["cards"]]}
        assert data["stage"] == "assess"
        cites = citations()
        return {"assessments": [{
            "requirement_id": requirement["id"], "status": "supported" if cites else "insufficient",
            "reason": "按合成原文引用", "citations": cites,
        } for requirement in data["requirements"]]}

    _transport(monkeypatch, reply)
    semantic = run_semantic_matching(
        job_path=job, evidence_files=sorted(evidence.glob("*.yaml")), personal_profile=profile,
        client=LLMClient(BASE_URL, "synthetic-key", provider="openai_compatible", thinking_enabled=None),
        model="synthetic-model", cache_dir=output.parent / "semantic-cache",
    )
    write_semantic_report(report, semantic)
    assert load_semantic_report(report) is not None
    return GenerationFlowConfig(
        matching_report_path=report, output_dir=output, personal_profile_path=profile,
        evidence_dir=evidence, job_profile_path=job, use_llm=True, require_llm=True,
        model="synthetic-model", api_key="synthetic-key", base_url=BASE_URL,
    )


def _decisions(data, decision="omit"):
    return {"decisions": [
        {"project_index": project["project_index"], "decision": decision,
         "rationale": "合成响应仅用于验证呈现合同"}
        for project in data["projects"]
    ]}


def _read(config, version="A"):
    path = config.output_dir / f"resume_{config.matching_report_path.stem}_{version}.md"
    trace, valid = read_generation_trace(path)
    assert valid
    assert trace["generation_strategy"] == "semantic_selection_locked_evidence_fields"
    return path, path.read_text(), trace


def _retained_baseline(config):
    baseline = replace(config, use_llm=False, require_llm=False,
                       output_dir=config.output_dir.parent / "baseline-resumes")
    assert run_generation_flow(baseline) == 0
    return _read(baseline)


def _optional_reason(before, after):
    assert {key: value for key, value in after.items() if key != "reasons"} == {
        key: value for key, value in before.items() if key != "reasons"}
    added = [reason for reason in after["reasons"] if reason not in before["reasons"]]
    assert added and all(isinstance(reason, str) and reason.strip() for reason in added)


@pytest.mark.parametrize("measured", [True, False])
def test_semantic_flow_omits_only_redundant_background_and_keeps_actual_result(
        generation_inputs, monkeypatch, measured):
    result = MEASURED_RESULT if measured else NONQUANT_RESULT
    context = MEASURED_CONTEXT if measured else NONQUANT_CONTEXT
    card, sources = _write_card(generation_inputs, "ec-1", context=context, results=[result],
                                measurement_quotes={0: result if measured else None})
    config = _review(generation_inputs, monkeypatch)
    _, baseline_text, baseline_trace = _retained_baseline(config)
    assert "背景：" + context in baseline_text
    before = {path: path.read_bytes() for path in [card, *sources.values()]}
    requests = _transport(monkeypatch, _decisions)

    assert run_generation_flow(config) == 0
    for version in ("A", "B"):
        path, text, trace = _read(config, version)
        result_claim, = [claim for claim in trace["claims"]
                         if claim.get("fact_id") == "ec-1:results:0"]
        assert result_claim["text"] == result
        assert text.splitlines()[result_claim["render_line"] - 1] == "- " + result
        assert trace["inputs"] == baseline_trace["inputs"]
        assert "背景：" + context not in text
        assert not any(claim.get("fact_id") == "ec-1:context:0" for claim in trace["claims"])
        _optional_reason(baseline_trace["readiness"], trace["readiness"])
    assert len(requests) == 2
    assert all(row["data"]["projects"] for row in requests)
    assert before == {path: path.read_bytes() for path in before}
    quality_path = config.output_dir / "actual-quality.md"
    assert run_evaluation_flow(EvaluationFlowConfig(
        input_path=_read(config)[0], output_path=quality_path, job_profile_path=config.job_profile_path,
    )) == 0
    quality = json.loads(quality_path.with_suffix(".json").read_text())
    assert quality["traceability"]["status"] == "verified"
    assert quality["quality_report"]["tiers"]["strong"]["metrics"]["quant_total"] == (0.5 if measured else 0.0)
    assert quality["quality_report"]["auto_pass"] is False


def test_background_request_uses_only_final_same_project_adopted_body(generation_inputs, monkeypatch):
    actions = [
        "实现交易接口的请求校验与异常处理机制",
        "完成交易接口的幂等控制与重试流程验收",
        "补齐交易接口的故障定位与回归验证记录",
        "预算外行动包含一段不得进入去重判断的详细说明",
    ]
    results = [
        MEASURED_RESULT, "完成交易接口的完整验收记录归档。",
        "预算外成果声称全部场景条件已被表达。",
        "同事负责的生产发布成果不能用作本人正文。",
    ]
    _write_card(generation_inputs, "ec-1", actions=actions, results=results,
                measurement_quotes={0: MEASURED_RESULT, 1: None, 2: None, 3: None},
                excluded_results=(3,))
    other_action = "实现库存对账接口并完成独立的故障恢复验收"
    other_result = "库存模块的回归验收已完成并保留原始记录。"
    other_context = "库存模块有独立的业务范围与验收条件。"
    _write_card(generation_inputs, "ec-2", context=other_context, actions=[other_action],
                results=[other_result], measurement_quotes={0: None})
    config = _review(generation_inputs, monkeypatch, positive_ids=[
        *(f"ec-1:actions:{index}" for index in range(4)), "ec-2:actions:0",
    ])
    _, baseline, baseline_trace = _retained_baseline(config)
    assert actions[3] not in baseline and results[2] not in baseline and results[3] not in baseline
    assert other_action in baseline and other_result in baseline
    requests = _transport(monkeypatch, lambda data: _decisions(data, "keep"))

    assert run_generation_flow(config) == 0
    _, text, trace = _read(config)
    assert text == baseline
    assert len(requests) == 2
    for request in requests:
        projects = request["data"]["projects"]
        first, = [project for project in projects if "ec-1:context:0" in json.dumps(project)]
        second, = [project for project in projects if "ec-2:context:0" in json.dumps(project)]
        first_text, second_text = json.dumps(first, ensure_ascii=False), json.dumps(second, ensure_ascii=False)
        for retained in [MEASURED_CONTEXT, *actions[:3], *results[:2]]:
            assert retained in first_text
        for absent in [actions[3], results[2], results[3], other_action, other_result, other_context]:
            assert absent not in first_text
        assert other_action in second_text and other_result in second_text
        assert "candidate@example.com" not in json.dumps(request["payload"])
    _optional_reason(baseline_trace["readiness"], trace["readiness"])


@pytest.mark.parametrize("fault", ["unknown", "missing", "bool", "duplicate", "outside", "extra"])
def test_incomplete_or_unknown_decision_never_partly_changes_body(
        generation_inputs, monkeypatch, fault):
    _write_card(generation_inputs, "ec-1")
    _write_card(generation_inputs, "ec-2", context="库存接口验收已经完成。",
                results=[NONQUANT_RESULT], measurement_quotes={0: None})
    config = _review(generation_inputs, monkeypatch)
    _, baseline, baseline_trace = _retained_baseline(config)

    def reply(data):
        response = _decisions(data, "unknown" if fault == "unknown" else "omit")
        rows = response["decisions"]
        assert len(rows) == 2
        if fault == "missing":
            rows.pop()
        elif fault == "bool":
            rows[1]["project_index"] = bool(rows[1]["project_index"])
        elif fault == "duplicate":
            rows[1]["project_index"] = rows[0]["project_index"]
        elif fault == "outside":
            rows[1]["project_index"] = max(row["project_index"] for row in rows) + 1
        elif fault == "extra":
            rows[1]["replacement"] = "不得采纳的替代正文"
        return response

    requests = _transport(monkeypatch, reply)
    assert run_generation_flow(config) == 0
    _, text, trace = _read(config)
    assert text == baseline
    assert trace["claims"] == baseline_trace["claims"]
    assert len(requests) == (2 if fault == "unknown" else 4)
    _optional_reason(baseline_trace["readiness"], trace["readiness"])


@pytest.mark.parametrize("failure", ["prepare", "configuration", "transport"])
def test_optional_task_failure_keeps_complete_body_under_require_llm(
        generation_inputs, monkeypatch, capsys, failure):
    _write_card(generation_inputs, "ec-1")
    config = _review(generation_inputs, monkeypatch)
    _, baseline, baseline_trace = _retained_baseline(config)
    prepared = []

    def unavailable(data):
        raise TimeoutError("synthetic unavailable")

    requests = _transport(monkeypatch, unavailable)
    if failure == "prepare":
        def fail_prepare(self, *args, **kwargs):
            prepared.append(True)
            raise ValueError("synthetic preparation failure")
        monkeypatch.setattr(LLMClient, "prepare_request", fail_prepare)
    elif failure == "configuration":
        config = replace(config, model="", api_key="")
    capsys.readouterr()

    assert run_generation_flow(config) == 0
    _, text, trace = _read(config)
    assert text == baseline and trace["claims"] == baseline_trace["claims"]
    assert len(requests) == (2 if failure == "transport" else 0)
    if failure == "prepare":
        assert len(prepared) == 2
    _optional_reason(baseline_trace["readiness"], trace["readiness"])
    assert "background_redundancy" in capsys.readouterr().out


def test_full_prepared_background_request_budget_never_truncates_or_sends(
        generation_inputs, monkeypatch, capsys):
    contexts = []
    for index in range(3):
        context = ("合成场景的完整责任与环境条件必须保留。" * 600) + f"这是第{index + 1}项独立场景。"
        contexts.append(context)
        _write_card(generation_inputs, f"ec-{index + 1}", context=context)
    assert sum(map(len, contexts)) > 24_000
    config = _review(generation_inputs, monkeypatch)
    _, baseline, baseline_trace = _retained_baseline(config)
    assert all("背景：" + context in baseline for context in contexts)
    requests = _transport(monkeypatch, _decisions)
    capsys.readouterr()

    assert run_generation_flow(config) == 0
    _, text, trace = _read(config)
    assert text == baseline and trace["claims"] == baseline_trace["claims"]
    assert requests == []
    _optional_reason(baseline_trace["readiness"], trace["readiness"])
    assert "input_budget_exceeded" in capsys.readouterr().out


def test_disabled_optional_task_keeps_background_without_transport(generation_inputs, monkeypatch):
    _write_card(generation_inputs, "ec-1")
    config = _review(generation_inputs, monkeypatch)
    requests = _transport(monkeypatch, lambda data: pytest.fail("disabled task must not send"))
    config = replace(config, use_llm=False, require_llm=False)
    assert run_generation_flow(config) == 0
    _, text, trace = _read(config)
    assert "背景：" + MEASURED_CONTEXT in text
    assert any(claim.get("fact_id") == "ec-1:context:0" for claim in trace["claims"])
    assert requests == []


def test_source_change_during_optional_task_is_still_a_publication_failure(
        generation_inputs, monkeypatch):
    _, sources = _write_card(generation_inputs, "ec-1")
    config = _review(generation_inputs, monkeypatch)
    material, = sources.values()
    before = material.read_bytes()

    def mutate_source(data):
        material.write_bytes(before + b"\nchanged during model call\n")
        return _decisions(data)

    requests = _transport(monkeypatch, mutate_source)
    assert run_generation_flow(config) == 1
    assert requests
    assert material.read_bytes() != before
    assert not list(config.output_dir.glob("*.md"))
    assert not list(config.output_dir.glob("*.trace.json"))


@pytest.mark.parametrize("duplicate", ["decision", "decisions"])
def test_duplicate_json_keys_never_authorize_background_omission(
        generation_inputs, monkeypatch, capsys, duplicate):
    card, sources = _write_card(generation_inputs, "ec-1")
    config = _review(generation_inputs, monkeypatch)
    _, baseline, baseline_trace = _retained_baseline(config)
    before = {path: path.read_bytes() for path in [card, *sources.values()]}

    def reply(data):
        keep = _decisions(data, "keep")["decisions"]
        omit = _decisions(data, "omit")["decisions"]
        if duplicate == "decisions":
            return '{"decisions":' + json.dumps(keep) + ',"decisions":' + json.dumps(omit) + '}'
        assert len(keep) == 1
        return ('{"decisions":[{"project_index":' + json.dumps(keep[0]["project_index"])
                + ',"decision":"keep","decision":"omit","rationale":"ambiguous decision"}]}')

    requests = _transport(monkeypatch, reply)
    capsys.readouterr()
    assert run_generation_flow(config) == 0
    for version in ("A", "B"):
        _, text, trace = _read(config, version)
        assert text == baseline
        assert trace["claims"] == baseline_trace["claims"]
        _optional_reason(baseline_trace["readiness"], trace["readiness"])
    assert len(requests) == 4
    assert "invalid_json" in capsys.readouterr().out
    assert before == {path: path.read_bytes() for path in before}
