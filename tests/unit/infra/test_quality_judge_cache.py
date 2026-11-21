"""B1/B4：判项缓存键与突出点用户决策库。"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request

import pytest

from tools.infra import quality_judge_cache as cache


CARDS = {
    "ec_1": {"title": "统一平台", "time_range": "2022-03 ~ 2023-09", "role_scope": "负责人",
             "context": "上下文", "results": ["延迟降低 20%"], "stack": ["Java"]},
}


def _prepared(payload=None, *, url="http://localhost:1234/v1/chat/completions", headers=None):
    return Request(
        url, data=json.dumps(payload or {"model": "m1", "messages": []}).encode("utf-8"),
        headers=headers or {}, method="POST",
    )


def _key_inputs(prepared=None):
    return {
        "prepared_request": prepared if prepared is not None else _prepared(),
        "trace_inputs": {"ec_1": {"path": "/synthetic/ec_1.yaml", "exists": True, "sha256": "c" * 64}},
        "resume_sha256": "a" * 64, "job_profile_id": "jp-1", "cards": CARDS, "prompt_version": 1,
    }


def test_cards_fingerprint_is_deterministic_and_sensitive():
    first = cache.cards_fingerprint(CARDS)
    assert first == cache.cards_fingerprint(json.loads(json.dumps(CARDS)))
    changed = {"ec_1": {**CARDS["ec_1"], "results": ["延迟降低 30%"]}}
    assert cache.cards_fingerprint(changed) != first
    assert cache.cards_fingerprint({**CARDS, "ec_2": {"title": "另一个"}}) != first
    limited={"ec_1":{**CARDS["ec_1"],"actions":["参与联调，由平台组负责总体设计"]}}
    owner={"ec_1":{**CARDS["ec_1"],"actions":["独立负责总体架构设计"]}}
    assert cache.cards_fingerprint(limited)!=cache.cards_fingerprint(owner)
    pending={"ec_1":{**CARDS["ec_1"],"role_scope_provenance":{"level":"L3","confirmed_by_user":False}}}
    confirmed={"ec_1":{**CARDS["ec_1"],"role_scope_provenance":{"level":"L3","confirmed_by_user":True}}}
    assert cache.cards_fingerprint(pending)!=cache.cards_fingerprint(confirmed)


def test_cache_key_changes_with_current_request_resume_target_sources_and_protocol():
    args = _key_inputs()
    base = cache.judge_cache_key(**args)
    assert len(base) == 64
    variations = [
        {"resume_sha256": "b" * 64},
        {"job_profile_id": "jp-2"},
        {"prompt_version": 2},
        {"prepared_request": _prepared({"model": "m2", "messages": []})},
        {"prepared_request": _prepared(url="http://localhost:9000/v1/chat/completions")},
        {"prepared_request": _prepared({"model": "m1", "messages": [], "thinking": {"type": "disabled"}})},
        {"trace_inputs": {"ec_1": {**args["trace_inputs"]["ec_1"], "sha256": "d" * 64}}},
        {"cards": {"ec_1": {**CARDS["ec_1"], "results": ["延迟降低 30%"]}}},
    ]
    for change in variations:
        assert cache.judge_cache_key(**{**args, **change}) != base, change
    assert cache.judge_cache_key(**_key_inputs(_prepared(headers={"Authorization": "Bearer synthetic-one"}))) == base
    assert cache.judge_cache_key(**_key_inputs(_prepared(headers={"Authorization": "Bearer synthetic-two"}))) == base


def test_shared_context_is_bound_from_prepared_request_without_later_reread(monkeypatch):
    from tools.prompts import context
    from tools.infra.llm.client import LLMClient

    client = LLMClient(base_url="http://localhost:1234/v1", api_key="",
                       provider="openai_compatible", thinking_enabled=None)
    payload = {"model": "m1", "messages": [{"role": "user", "content": "合成质量判项"}]}
    prepared = client.prepare_request(client.chat_completions_url, payload)
    before = cache.judge_cache_key(**_key_inputs(prepared))
    monkeypatch.setattr(context, "JOB_SEARCH_CONTEXT", context.JOB_SEARCH_CONTEXT + "\n更新产品语境")
    assert cache.judge_cache_key(**_key_inputs(prepared)) == before
    changed = client.prepare_request(client.chat_completions_url, payload)
    assert changed.data != prepared.data
    assert cache.judge_cache_key(**_key_inputs(changed)) != before


def test_judgment_cache_roundtrip_and_corruption(tmp_path):
    key = "k" * 64
    assert cache.load_judgment(tmp_path, key) is None
    judgments = {"schema_version": 1, "judged_sections": ["r1_4"], "r1_4": []}
    path = cache.save_judgment(tmp_path, key, judgments)
    assert path.is_file()
    assert cache.load_judgment(tmp_path, key) == judgments
    path.write_text("{broken", encoding="utf-8")
    assert cache.load_judgment(tmp_path, key) is None


@pytest.mark.parametrize("judgments", [
    '{"judged_sections":[],"judged_sections":["r1_4"]}',
    '{"r1_4":[{"supported":false,"supported":true}]}',
], ids=["top-level", "nested-item"])
def test_current_cache_rejects_duplicate_json_keys_without_rewriting(tmp_path, judgments):
    path = cache.cache_path(tmp_path, "duplicate")
    path.write_text('{"cache_schema_version":' + str(cache.JUDGE_CACHE_SCHEMA_VERSION) +
                    ',"judgments":' + judgments + '}', encoding="utf-8")
    before = path.read_bytes()
    assert cache.load_judgment(tmp_path, "duplicate") is None
    assert path.read_bytes() == before


def test_old_cache_schema_is_a_miss_without_deleting_history(tmp_path):
    path = cache.save_judgment(tmp_path, "old", {"judged_sections": ["r1_4"], "r1_4": []})
    payload = json.loads(path.read_text())
    payload["cache_schema_version"] = cache.JUDGE_CACHE_SCHEMA_VERSION - 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()
    assert cache.load_judgment(tmp_path, "old") is None
    assert path.read_bytes() == before


def test_highlight_decisions_reject_select_and_clear(tmp_path):
    root = Path(tmp_path)
    sha = "a" * 64
    assert cache.load_decisions(root, sha) == {"rejected": [], "selected": []}
    cache.save_highlight_decision(root, sha, "hl_b2_d1", "reject")
    cache.save_highlight_decision(root, sha, "hl_b3_d2", "select")
    decisions = cache.load_decisions(root, sha)
    assert decisions == {"rejected": ["hl_b2_d1"], "selected": ["hl_b3_d2"]}
    # 同一候选先否决后选中会互换，不会同时存在。
    cache.save_highlight_decision(root, sha, "hl_b2_d1", "select")
    decisions = cache.load_decisions(root, sha)
    assert decisions == {"rejected": [], "selected": ["hl_b2_d1", "hl_b3_d2"]}
    cache.save_highlight_decision(root, sha, "hl_b2_d1", "reject")
    assert cache.load_decisions(root, sha) == {"rejected": ["hl_b2_d1"], "selected": ["hl_b3_d2"]}
    with pytest.raises(ValueError):
        cache.save_highlight_decision(root, sha, "hl_b2_d1", "unknown")
    payload = json.loads(cache.decisions_path(root).read_text(encoding="utf-8"))
    assert payload["resumes"][sha]["rejected"] == ["hl_b2_d1"]
