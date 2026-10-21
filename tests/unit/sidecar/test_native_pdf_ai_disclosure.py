import json
from pathlib import Path

import pytest

from tools.infra.ai_disclosure import AI_DISCLOSURE_TEXT
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
from tools.sidecar.handlers import agent
from tools.sidecar.handlers import native_pdf as flow


def _observation(candidate, *, text, confirmed, evidence, action=None):
    network = []
    if evidence == "network":
        network = [{
            "method": "POST",
            "url": "https://api-c.liepin.com/api/com.liepin.im.c.chat.send",
            "http_status": 200,
            "request": json.dumps({"content": text}, ensure_ascii=False),
            "response": '{"flag":1,"data":{}}',
        }]
    detail = {
        "url": candidate["job_url"],
        "context": {"class_name": "im-ui-chat-container",
                    "text": f'{candidate["company"]} {candidate["position"]}'},
        "action": action or {"click_issued": True, "reason": "approved_ai_disclosure_send"},
        "ai_disclosure": {"text": text, "confirmed": confirmed, "evidence": evidence,
                          "dom_confirmed": evidence == "dom", "network": network},
    }
    return {"status": "unknown", "filename": "cv.pdf", "hints": [],
            "responses": [{"method": "OBSERVE", "url": candidate["job_url"],
                           "http_status": 0, "payload": json.dumps(detail, ensure_ascii=False)}]}


def _setup(tmp_path, monkeypatch, *, disclosure_enabled):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(agent, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(agent, "_AGENT_RUN_DIR", tmp_path / "outputs/agent_runs")
    monkeypatch.setattr(agent, "_REVIEW_QUEUE_DIR", tmp_path / "outputs/review_queue")
    policy = tmp_path / "policy.local.yaml"
    policy.write_text(
        'delivery_mode: "auto"\nbatch_review: "false"\n'
        f'ai_disclosure_enabled: "{"true" if disclosure_enabled else "false"}"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PPF_POLICY_PATH", str(policy))
    c = {"job_lead_id": "lead", "company": "公司", "position": "岗位", "platform": "liepin",
         "source": "liepin_official", "platform_job_id": "123", "platform_job_type": "2",
         "source_jd_sha256": "jd", "job_url": "https://www.liepin.com/job/123.shtml",
         "delivery_kind": "generated_pdf", "status": "approved"}
    store = ReviewSnapshotStore(agent._AGENT_RUN_DIR)
    c["snapshot"] = store.create("run", c, "# 合成候选人", dry_run=False,
                                 pdf_content=b"%PDF-1.7\nfixture\n%%EOF")
    sealed = store.load("run", c)
    q = {"run_id": "run", "candidates": [c],
         "attachment_binding": {"pdf_sha256": sealed["pdf_sha256"], "filename": "cv.pdf",
                                "attachment_id": "id", "file_id": "file-id"},
         "pdf_target_view": {"observation": {"responses": [{"method": "OBSERVE", "payload": json.dumps({
             "url_match": True, "company_present": True, "position_present": True,
             "challenge": False, "unavailable": False})}]}}}
    agent._save_queue(agent._get_queue_file("run"), q)
    monkeypatch.setattr("tools.infra.liepin_job_detail.fetch_liepin_job_detail",
                        lambda *a, **kw: {"source_jd_sha256": "jd"})
    attempts = DeliveryAttemptStore()
    attempts.authorize_batch("old", 1, [])
    old = attempts.reserve("old", "old", "x", delivery_kind="platform_default")
    attempts.finish(old, "success")
    attempts.authorize_supplementary_batch("pdf", "old", 1, "generated_pdf", "grant")
    params = {"meta": {"correlation_id": "t"}, "run_id": "run"}
    packet = flow.handle_begin_pdf_delivery(params)
    q = agent._load_queue(agent._get_queue_file("run"))
    q["pdf_delivery"]["state"] = "communication_started"
    agent._save_queue(agent._get_queue_file("run"), q)
    return params, packet, sealed, c


@pytest.fixture(autouse=True)
def _complete_content_precondition_for_disclosure_tests(monkeypatch):
    monkeypatch.setattr("tools.infra.resume_content.require_queue_content", lambda *a, **kw: {})


def test_prepare_requires_confirmed_ai_disclosure_before_resume_entry(tmp_path, monkeypatch):
    params, packet, sealed, c = _setup(tmp_path, monkeypatch, disclosure_enabled=True)

    required = flow.handle_pdf_interaction_packet({**params, "action": "prepare"})
    assert required["requires_ai_disclosure"] is True
    assert required["ai_disclosure"]["text"] == AI_DISCLOSURE_TEXT
    assert required["ai_disclosure"]["sha256"]
    q = agent._load_queue(agent._get_queue_file("run"))
    assert "resume_interaction_started" not in q["pdf_delivery"]
    assert flow.handle_pdf_interaction_packet({**params, "action": "inspect"}).get("requires_ai_disclosure") is not True

    bad = _observation(c, text=AI_DISCLOSURE_TEXT, confirmed=False, evidence="",
                       action={"click_issued": False, "reason": "composer_missing"})
    flow.handle_record_pdf_interaction({**params, "action": "ai_disclosure",
                                        "delivery_ref": packet["delivery_ref"], "observation": bad})
    q = agent._load_queue(agent._get_queue_file("run"))
    assert q["pdf_delivery"].get("ai_disclosure") is None
    assert flow.handle_pdf_interaction_packet({**params, "action": "prepare"})["requires_ai_disclosure"] is True

    good = _observation(c, text=AI_DISCLOSURE_TEXT, confirmed=True, evidence="network")
    recorded = flow.handle_record_pdf_interaction({**params, "action": "ai_disclosure",
                                                   "delivery_ref": packet["delivery_ref"], "observation": good})
    assert recorded["ai_disclosure_sent"] is True
    q = agent._load_queue(agent._get_queue_file("run"))
    assert q["pdf_delivery"]["ai_disclosure"]["text"] == AI_DISCLOSURE_TEXT

    prepared = flow.handle_pdf_interaction_packet({**params, "action": "prepare"})
    assert prepared.get("requires_ai_disclosure") is not True
    assert prepared["action"] == "prepare"
    q = agent._load_queue(agent._get_queue_file("run"))
    assert q["pdf_delivery"]["resume_interaction_started"] is True


def test_send_requires_ai_disclosure_even_when_dialog_is_confirmed(tmp_path, monkeypatch):
    params, packet, sealed, c = _setup(tmp_path, monkeypatch, disclosure_enabled=True)
    confirmation = {
        "context": {"class_name": "im-ui-chat-container", "text": "公司 岗位"},
        "confirmation": [{
            "text": "选择附件简历 默认在线简历和附件简历 cv",
            "inputs": [{"type": "radio", "checked": True, "value": "file-id", "disabled": False}],
            "buttons": [{"text": "立即投递", "disabled": False}],
        }],
    }
    q = agent._load_queue(agent._get_queue_file("run"))
    q["pdf_delivery"].update(state="resume_interaction_pending", resume_interaction_started=True,
                             interaction_history=[{"action": "prepare", "observation": {"responses": [
                                 {"method": "OBSERVE", "payload": json.dumps(confirmation, ensure_ascii=False)}]}}])
    agent._save_queue(agent._get_queue_file("run"), q)

    required = flow.handle_pdf_interaction_packet({**params, "action": "send"})
    assert required["requires_ai_disclosure"] is True
    q = agent._load_queue(agent._get_queue_file("run"))
    assert "final_send_started" not in q["pdf_delivery"]

    good = _observation(c, text=AI_DISCLOSURE_TEXT, confirmed=True, evidence="dom")
    flow.handle_record_pdf_interaction({**params, "action": "ai_disclosure",
                                        "delivery_ref": packet["delivery_ref"], "observation": good})
    allowed = flow.handle_pdf_interaction_packet({**params, "action": "send"})
    assert allowed.get("requires_ai_disclosure") is not True
    assert allowed["file_id"] == "file-id"
    q = agent._load_queue(agent._get_queue_file("run"))
    assert q["pdf_delivery"]["final_send_started"] is True


def test_disabled_ai_disclosure_keeps_previous_prepare_behavior(tmp_path, monkeypatch):
    params, packet, sealed, c = _setup(tmp_path, monkeypatch, disclosure_enabled=False)
    prepared = flow.handle_pdf_interaction_packet({**params, "action": "prepare"})
    assert prepared.get("requires_ai_disclosure") is not True
    q = agent._load_queue(agent._get_queue_file("run"))
    assert q["pdf_delivery"]["resume_interaction_started"] is True
    assert flow._public(q)["ai_disclosure_sent"] is False
