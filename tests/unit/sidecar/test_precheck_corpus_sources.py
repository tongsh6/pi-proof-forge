import hashlib
import json
import pytest
from tools.sidecar.handlers import jobs
from tools.sidecar.handlers._shared import profile_state

def test_pool_approval_reason_enforces_evidence_first_gate():
    from tools.infra.evidence_pool import pool_approval_reason

    good = {"title": "项目", "results": ["查询降至 300ms"], "artifacts": ["mat_x"]}
    assert pool_approval_reason(good) == ""
    assert pool_approval_reason({**good, "title": ""}) == "title_missing"
    assert pool_approval_reason({**good, "results": []}) == "results_missing"
    assert pool_approval_reason({**good, "artifacts": []}) == "artifacts_missing"
    assert pool_approval_reason(good, source_verifiable=False) == "source_unverifiable"


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    cards=tmp_path/"evidence_cards";cards.mkdir()
    materials=tmp_path/"materials";materials.mkdir()
    source=materials/"m.md";source.write_text("Java result")
    monkeypatch.setattr(jobs,"_EVIDENCE_CARD_DIR",cards)
    monkeypatch.setattr(profile_state,"profile_path",lambda:tmp_path/"profile.yaml")
    monkeypatch.setattr(jobs,"_PRECHECK_CORPUS_CACHE",None)
    def write(name="ec_live",**changes):
        fields={"id":name,"title":"Java project","status":"saved_eligible","candidate_pool_eligible":"true",
            "results":["Java result"],"artifacts":["m.md"],"source_material_ids":["m"],
            "source_material_fingerprints_json":json.dumps({"m":{"filename":"m.md","sha256":hashlib.sha256(source.read_bytes()).hexdigest()}})}
        fields.update(changes)
        lines=[]
        for key,value in fields.items():
            if value is None:continue
            if isinstance(value,list):
                lines.append(key+":")
                lines.extend("  - "+json.dumps(x) for x in value)
            else:lines.append(key+": "+json.dumps(value))
        path=cards/(name+".yaml");path.write_text("\n".join(lines)+"\n")
        return path
    return write,source,cards

def test_valid_source_and_source_change_invalidates_without_card_change(fixture):
    write,source,_=fixture
    card=write();before=card.read_bytes()
    assert jobs._load_precheck_corpus()["card_count"]==1
    source.write_text("tampered source")
    result=jobs._load_precheck_corpus()
    assert result["card_count"]==0
    assert result["excluded_reasons"]["source_unverifiable"]==1
    assert card.read_bytes()==before

@pytest.mark.parametrize("changes,reason",[
    ({"results":[]},"results_missing"),({"artifacts":[]},"artifacts_missing"),
    ({"title":""},"title_missing"),({"sample":"true"},"pool_ineligible"),
    ({"candidate_pool_eligible":None},"not_explicitly_eligible"),
    ({"candidate_pool_eligible":"false"},"not_explicitly_eligible"),
    ({"status":"draft"},"not_explicitly_eligible"),
    ({"source_material_fingerprints_json":"broken"},"source_unverifiable"),
])
def test_invalid_card_is_local_exclusion(fixture,changes,reason):
    write,_,_=fixture
    write("ec_good");write("ec_bad",**changes)
    result=jobs._load_precheck_corpus()
    assert result["card_count"]==1
    assert result["excluded_count"]==1
    assert result["excluded_reasons"]=={reason:1}

def test_legacy_no_fingerprint_matches_formal_compatibility_but_not_verified(fixture):
    fixture[0](source_material_fingerprints_json=None)
    result=jobs._load_precheck_corpus()
    assert result["card_count"]==1
    assert result["source_freshness_unverified_count"]==1
    assert result["verified_source_count"]==0

def test_demo_id_is_excluded(fixture):
    fixture[0]("ec-demo_1")
    assert jobs._load_precheck_corpus()["card_count"]==0

def test_source_error_does_not_leak_path(fixture):
    write,source,_=fixture
    write();source.unlink()
    result=jobs._load_precheck_corpus()
    assert str(source) not in str(result)
    assert result["excluded_reasons"]=={"source_unverifiable":1}
