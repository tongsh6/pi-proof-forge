"""Independent stage-budget counterexamples; real engine/client, synthetic HTTP only."""
import io
import json

from tools.engines.matching import semantic_matching as engine
from tools.infra.llm.bounded_local import BoundedLocalClient
from tools.sidecar.handlers.preparation_semantic import _safe_summary


def _fixture(tmp_path, count=4):
    job = tmp_path / "jp.yaml"
    job.write_text('target_role: "Engineer"\nmust_have:\n  - "Java services"\n')
    paths = []
    for index in range(count):
        path = tmp_path / f"ec_{index}.yaml"
        path.write_text('title: "Service"\nrole_scope: "Developer"\nresults:\n  - "Built Java services"\nartifacts:\n  - "Report"\n')
        paths.append(path)
    return dict(job_path=job, evidence_files=paths, personal_profile=None,
                model="fixture", cache_dir=tmp_path / "cache", batch_size=1)


def _client(*, invalid_recalls=0):
    client = BoundedLocalClient(model="fixture", api_key="")
    seen = []

    class Transport:
        def open(self, req, **kwargs):
            nonlocal invalid_recalls
            payload = json.loads(req.data)
            data = json.loads(payload["messages"][1]["content"])
            seen.append(data["stage"])
            if data["stage"] == "recall" and invalid_recalls:
                invalid_recalls -= 1
                result = {"cards": []}
            elif data["stage"] == "recall":
                result = {"cards": [
                    {"id": card["id"], "score": 80, "requirement_ids": ["r1"],
                     "citations": [{"fact_id": next(k for k in card["facts"] if ":results:" in k)}],
                     "reason": "Relevant"}
                    for card in data["cards"]]}
            else:
                fid = next(k for k in data["facts"] if ":results:" in k)
                result = {"assessments": [
                    {"requirement_id": r["id"], "status": "supported",
                     "citations": [{"fact_id": fid}], "reason": "Built services"}
                    for r in data["requirements"]]}
            response = {"choices": [{"message": {"content": json.dumps(result)}, "finish_reason": "stop"}]}
            return io.BytesIO(json.dumps(response).encode())

    client._opener = Transport()

    def before(stage):
        if stage == "recall" and client.model_calls >= 2:
            client.budget_exhausted = True
            raise ValueError("semantic_stage_budget_deferred")

    return client, seen, before


def test_two_recall_http_still_allow_assessment(tmp_path):
    kwargs = _fixture(tmp_path)
    client, seen, before = _client()
    result = engine.run_semantic_matching(**kwargs, client=client, advisory=True, before_model_call=before)
    assert seen == ["recall", "recall", "assess"]
    assert client.model_calls == 3
    assert set(result["budget_deferred_card_ids"]) == {"ec_2", "ec_3"}
    assert result["criterion_assessments"]
    assert not result["degraded_check_ids"]


def test_cache_is_consulted_even_after_recall_reservation_threshold(tmp_path):
    kwargs = _fixture(tmp_path, count=2)
    first, _, before = _client()
    engine.run_semantic_matching(**kwargs, client=first, advisory=True, before_model_call=before)
    cached, seen, _ = _client()
    hook_calls = []

    def forbidden(stage):
        hook_calls.append(stage)
        raise AssertionError("A validated cache hit must not request network budget")

    result = engine.run_semantic_matching(**kwargs, client=cached, advisory=True, before_model_call=forbidden)
    assert cached.model_calls == 0
    assert seen == hook_calls == []
    assert result["statistics"]["cache_hits"] >= 3


def test_repair_counts_against_recall_http_not_batch_count(tmp_path):
    kwargs = _fixture(tmp_path, count=3)
    client, seen, before = _client(invalid_recalls=1)
    result = engine.run_semantic_matching(**kwargs, client=client, advisory=True, before_model_call=before)
    assert seen == ["recall", "recall", "assess"]
    assert client.model_calls == 3
    assert result["statistics"]["repair_calls"] >= 1
    assert set(result["budget_deferred_card_ids"]) == {"ec_1", "ec_2"}


def test_no_valid_recall_never_invents_supported_assessment(tmp_path):
    kwargs = _fixture(tmp_path, count=3)
    client, seen, before = _client(invalid_recalls=100)
    result = engine.run_semantic_matching(**kwargs, client=client, advisory=True, before_model_call=before)
    assert seen == ["recall", "recall"]
    assert client.model_calls == 2
    assert not result["card_reviews"]
    assert not any(row["status"] in {"supported", "partial"} for row in result["assessments"])
    assert result["budget_deferred_check_ids"]
    assert result["assessment_visibility"] == {}


def test_canonical_default_does_not_apply_advisory_recall_reservation(tmp_path):
    kwargs = _fixture(tmp_path, count=3)
    client, seen, _ = _client()
    result = engine.run_semantic_matching(**kwargs, client=client)
    assert seen == ["recall", "recall", "recall", "assess"]
    assert client.model_calls == 4
    assert len(result["card_reviews"]) == 3


def test_unassessed_parent_does_not_erase_independent_completed_requirement():
    client, _, _ = _client()
    raw = {
        "requirements": [{"id": "r1", "text": "Java"}, {"id": "r2", "text": "SQL"}],
        "requirement_checks": [{"id": "r1.c1", "parent_id": "r1"},
                               {"id": "r2.c1", "parent_id": "r2"}],
        "degraded_check_ids": [],
        "budget_deferred_check_ids": ["r2.c1"],
        "assessments": [
            {"requirement_id": "r1", "status": "supported", "reason": "Direct", "citations": []},
            {"requirement_id": "r2", "status": "insufficient", "reason": "Not run", "citations": []}],
    }
    inputs = {"direction": None, "evidence_files": [], "pool": {}}
    summary = _safe_summary("jp", inputs, client, raw, None)
    statuses = {r["requirement_id"]: r["status"] for r in summary["assessments"]}
    assert statuses == {"r1": "supported", "r2": "unassessed"}


def test_all_recall_invalid_without_reservation_is_failure_not_budget(tmp_path):
    kwargs = _fixture(tmp_path, count=1)
    client, seen, before = _client(invalid_recalls=100)
    result = engine.run_semantic_matching(**kwargs, client=client, advisory=True, before_model_call=before)
    assert seen == ["recall", "recall"]
    assert not result["budget_deferred_check_ids"]
    assert result["degraded_check_ids"]
    assert result["assessment_visibility"] == {}
    assert not client.budget_exhausted


def test_preassembled_assess_payload_is_not_completed_visibility(tmp_path):
    kwargs = _fixture(tmp_path, count=1)
    client, seen, _ = _client()

    def before(stage):
        if stage == "assess":
            client.budget_exhausted = True
            raise ValueError("semantic_stage_budget_deferred")

    result = engine.run_semantic_matching(**kwargs, client=client, advisory=True, before_model_call=before)
    assert seen == ["recall"]
    assert result["budget_deferred_check_ids"]
    assert result["assessment_visibility"] == {}


def test_unbound_reused_direction_rejected_before_any_network(tmp_path):
    import pytest
    kwargs = _fixture(tmp_path, count=1)
    client, seen, before = _client()
    with pytest.raises(ValueError, match="semantic_direction_preferences_missing"):
        engine.run_semantic_matching(
            **kwargs, client=client, advisory=True, before_model_call=before,
            reused_direction={"status": "aligned", "reason": "Invented",
                              "criterion_index": 0, "jd_quote": "not in JD"})
    assert seen == []
    assert client.model_calls == 0



def test_advisory_assess_terminal_safe_reasons_are_typed(tmp_path, monkeypatch):
    private = "PRIVATE_SHOULD_NEVER_REACH_ADVISORY_AUDIT"
    real_execute = engine.execute
    for name, expected, attempts in (
        ("timeout", "provider_timeout", 1),
        ("response", "response_invalid", 2),
        ("outer_json", "response_invalid", 1),
        ("outer_envelope", "response_invalid", 2),
        ("extract_error", "response_invalid", 1),
        ("retry_budget", "attempt_budget", 1),
        ("precall", "attempt_budget", 0),
        ("input_budget", "input_budget", 0),
        ("generic", "transport_other", 1),
    ):
        temp = tmp_path / name
        temp.mkdir()
        kwargs = _fixture(temp, count=1)
        client, seen, _ = _client()
        original = client._opener.open
        calls = []

        def open_fake(req, **options):
            data = json.loads(json.loads(req.data)["messages"][1]["content"])
            if data["stage"] == "recall":
                return original(req, **options)
            calls.append(data["stage"])
            if name == "timeout":
                raise TimeoutError(private)
            if name == "outer_json":
                return io.BytesIO(("{"+private).encode())
            if name == "outer_envelope":
                return io.BytesIO(json.dumps({"other": private}).encode())
            if name == "generic":
                # An unrelated exception resembling a known refusal must not select it.
                raise RuntimeError("semantic_stage_budget_deferred:" + private)
            response = {"choices": [{"message": {"content":json.dumps({"assessments":[]})},
                                     "finish_reason":"stop"}]}
            return io.BytesIO(json.dumps(response).encode())

        def invoke(contract, **options):
            if name == "input_budget" and json.loads(options["payload"]["messages"][1]["content"])["stage"] == "assess":
                options["payload"] = {**options["payload"], "size_pressure":"x"*30_000}
            return real_execute(contract, **options)

        def before(stage):
            if stage == "assess" and (name == "precall" or (name == "retry_budget" and calls)):
                raise ValueError("semantic_stage_budget_deferred")

        client._opener.open = open_fake
        extract = client.extract_content

        def extract_fake(response):
            if name == "extract_error" and calls:
                raise KeyError(private)
            return extract(response)

        client.extract_content = extract_fake
        monkeypatch.setattr(engine, "execute", invoke)
        result = engine.run_semantic_matching(**kwargs, client=client, advisory=True, before_model_call=before)
        assert len(calls) == attempts, name
        assert result["card_reviews"], name
        entry, = result["assessment_schedule"]["entries"]
        assert entry["reason_code"] == expected, name
        assert entry["outcome"] == ("budget_deferred" if expected == "attempt_budget" else "degraded"), name
        assert entry["completed"] is False, name
        assert entry.get("retry_budget_blocked", False) is (name == "retry_budget"), name
        assert private not in json.dumps(result), name
        assert len(list(kwargs["cache_dir"].glob("*.json"))) == 1, name
