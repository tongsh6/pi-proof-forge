"""profile.autoLinkEvidence：先建议，apply 才写入；写入后修订号变化、档案回到待确认。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers import materials, profile
from tools.sidecar.server import process_request


def _rpc(**params):
    response = process_request({"jsonrpc": "2.0", "id": "t", "method": "profile.autoLinkEvidence",
                                "params": {"meta": {"correlation_id": "t"}, **params}})
    return response


def _card(path: Path, evidence_id: str, title: str, material: str, time_range: str = "") -> None:
    path.write_text("\n".join([
        f'id: "{evidence_id}"', f'title: "{title}"', f'time_range: "{time_range}"', 'status: "saved_eligible"', 'candidate_pool_eligible: "true"',
        'results:', '  - "r"', 'artifacts:', f'  - "{material}"', 'source_material_ids:', f'  - "{material}"', ""]), encoding="utf-8")


def test_suggest_then_apply_links_and_invalidates_review():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "materials").mkdir(); (root / "evidence_cards").mkdir()
        (root / "materials" / "mat_ec.meta.yaml").write_text('material_id: "mat_ec"\nlabel: "EC+ 工作汇总"\nkind: "raw_work_material"\nfilename: "mat_ec.md"\nextension: ".md"\n', encoding="utf-8")
        (root / "materials" / "mat_ec.md").write_text("x", encoding="utf-8")
        _card(root / "evidence_cards" / "ec_new.yaml", "ec_new", "新卡", "mat_ec")
        _card(root / "evidence_cards" / "ec_far.yaml", "ec_far", "无关卡", "mat_other")
        career = {"schema_version": 1, "summary": "s", "education_visibility": "omit", "education": [], "skills": [{"id": "sk1", "category": "c", "description": "d", "evidence_ids": []}], "extras": [],
                  "work": [{"id": "w_ec", "company": "一里智辉（EC+）", "department": "", "title": "Tech Lead", "start": "2021-03", "end": "", "current": True, "scope": "s", "contributions": ["c"], "evidence_ids": []}]}
        profile_path = root / "personal_profile.yaml"
        profile_path.write_text("\n".join([
            'name: "N"', 'phone: "13800000000"', 'email: "a@b.co"', 'city: "上海"', 'current_position: "Tech Lead"',
            "career_json: " + json.dumps(json.dumps(career, ensure_ascii=False), ensure_ascii=False), ""]), encoding="utf-8")
        with patch.object(profile, "_PROFILE_PATH", profile_path), patch.object(materials, "_MATERIALS_DIR", root / "materials"):
            before = process_request({"jsonrpc": "2.0", "id": "g", "method": "profile.get", "params": {"meta": {"correlation_id": "g"}}})["result"]["profile"]
            preview = _rpc()["result"]
            assert preview["applied"] == 0 and [s["evidence_id"] for s in preview["suggestions"]] == ["ec_new"]
            assert preview["unresolved"][0]["evidence_id"] == "ec_far" and preview["revision"] == before["revision"]
            stale = _rpc(apply=True, expected_revision="old")
            assert "error" in stale and "profile_changed" in json.dumps(stale)
            applied = _rpc(apply=True, expected_revision=before["revision"])["result"]
            assert applied["applied"] == 1 and applied["revision"] != before["revision"]
            assert applied["career_status"]["reviewed"] is False
            after = process_request({"jsonrpc": "2.0", "id": "g", "method": "profile.get", "params": {"meta": {"correlation_id": "g"}}})["result"]["profile"]
            assert after["career"]["work"][0]["evidence_ids"] == ["ec_new"]
            again = _rpc()["result"]
            assert again["suggestions"] == [] and again["already_linked"] == 1
