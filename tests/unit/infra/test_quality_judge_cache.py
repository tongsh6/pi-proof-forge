"""B1/B4：判项缓存键与突出点用户决策库。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.infra import quality_judge_cache as cache


CARDS = {
    "ec_1": {"title": "统一平台", "time_range": "2022-03 ~ 2023-09", "role_scope": "负责人",
             "context": "上下文", "results": ["延迟降低 20%"], "stack": ["Java"]},
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


def test_cache_key_changes_with_resume_job_model_and_prompt():
    base = cache.judge_cache_key(resume_sha256="a" * 64, job_profile_id="jp-1", cards=CARDS,
                                 model="m1", prompt_version=1)
    assert len(base) == 64
    assert base != cache.judge_cache_key(resume_sha256="b" * 64, job_profile_id="jp-1", cards=CARDS,
                                         model="m1", prompt_version=1)
    assert base != cache.judge_cache_key(resume_sha256="a" * 64, job_profile_id="jp-2", cards=CARDS,
                                         model="m1", prompt_version=1)
    assert base != cache.judge_cache_key(resume_sha256="a" * 64, job_profile_id="jp-1", cards=CARDS,
                                         model="m2", prompt_version=1)
    assert base != cache.judge_cache_key(resume_sha256="a" * 64, job_profile_id="jp-1", cards=CARDS,
                                         model="m1", prompt_version=2)


def test_shared_product_context_change_invalidates_quality_judgments(monkeypatch):
    from tools.prompts import context
    args=dict(resume_sha256="a"*64,job_profile_id="jp-1",cards=CARDS,model="m1",prompt_version=1)
    before=cache.judge_cache_key(**args)
    monkeypatch.setattr(context,"JOB_SEARCH_CONTEXT",context.JOB_SEARCH_CONTEXT+"\n更新产品语境")
    assert cache.judge_cache_key(**args)!=before


def test_judgment_cache_roundtrip_and_corruption(tmp_path):
    key = "k" * 64
    assert cache.load_judgment(tmp_path, key) is None
    judgments = {"schema_version": 1, "judged_sections": ["r1_4"], "r1_4": []}
    path = cache.save_judgment(tmp_path, key, judgments)
    assert path.is_file()
    assert cache.load_judgment(tmp_path, key) == judgments
    path.write_text("{broken", encoding="utf-8")
    assert cache.load_judgment(tmp_path, key) is None


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
