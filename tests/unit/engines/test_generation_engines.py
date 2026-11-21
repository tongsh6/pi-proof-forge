"""实际来源适配、唯一渲染和生成时版本绑定；所有资料均为合成夹具。"""
import json
from pathlib import Path
from dataclasses import replace

import pytest

from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.engines.generation.template_assembler import TemplateAssembler
from tools.engines.generation import resume_renderer
from tools.engines.generation.exporter import ResumeExporter
from tools.infra.persistence.review_snapshot import validate_generation_trace

RESULT = "在隔离测试环境中，1000 条合成请求的 P95 从 200ms 降至 120ms。"


@pytest.fixture
def generation(tmp_path):
    evidence = tmp_path / "evidence_cards"
    evidence.mkdir()
    card_path = evidence / "ec-engine.yaml"
    card_path.write_text(
        'id: "ec-engine"\ntitle: "队列处理服务"\nstatus: "saved_eligible"\n'
        'candidate_pool_eligible: "true"\ntime_range: "2024-01 ~ 2024-06"\n'
        'context: "合成队列处理验收"\nrole_scope: "负责接口联调"\n'
        'actions:\n  - "实现消费接口并完成测试联调"\n'
        'results:\n  - ' + json.dumps(RESULT, ensure_ascii=False) +
        '\nstack:\n  - "Java"\nartifacts:\n  - "合成测试报告"\n'
    )
    profile = tmp_path / "personal_profile.yaml"
    profile.write_text('name: "合成候选人"\ncurrent_position: "工程师"\n')
    job = tmp_path / "jp-engine.yaml"
    job.write_text('target_role: "工程师"\ncompany: "合成公司"\nsource_jd: "job.txt"\n')
    jd = tmp_path / "job.txt"
    jd.write_text("负责队列处理与测试联调")
    assembler = TemplateAssembler(evidence_dir=evidence, personal_profile_path=profile, job_profile_path=job)
    identity = EvidenceCard("ec-engine", "不可作为正文来源", "不可作为原料",
                            ("生产环境达到 999% 改善",), ("不可作为证明",))
    report = MatchingReport("jp-engine", ("ec-engine",), {}, ())
    return assembler, identity, report, {"card": card_path, "profile": profile, "job": job, "jd": jd}


def test_template_assembler_reads_current_source_not_domain_payload(generation):
    assembler, identity, report, paths = generation
    resume = assembler.generate(report, [identity], "v2")
    assert resume.version == "v2" and resume.job_profile_id == "jp-engine"
    assert RESULT in resume.content and "999%" not in resume.content
    assert validate_generation_trace(resume.content, resume.generation_trace)
    row, = [c for c in resume.generation_trace["claims"] if c.get("fact_id") == "ec-engine:results:0"]
    assert row["text"] == RESULT and RESULT in resume.content.splitlines()[row["render_line"] - 1]
    assert resume.generation_trace["evidence_card_ids"] == ["ec-engine"]
    assert Path(resume.generation_trace["inputs"]["ec-engine"]["path"]) == paths["card"]


@pytest.mark.parametrize("selected", [(), ("outside",), ("ec-engine", "ec-engine")])
def test_template_assembler_never_expands_empty_or_outside_selection(generation, selected):
    assembler, identity, report, _ = generation
    with pytest.raises(ValueError, match="selected_evidence_missing_or_invalid"):
        assembler.generate(replace(report, evidence_card_ids=selected), [identity], "v1")


def test_template_assembler_rejects_different_target(generation):
    assembler, identity, report, _ = generation
    with pytest.raises(ValueError, match="generation_target_changed"):
        assembler.generate(replace(report, job_profile_id="other"), [identity], "v1")


@pytest.mark.parametrize("changed", ["card", "profile", "job", "jd"])
def test_render_cannot_bind_old_content_to_new_input_hash(generation, monkeypatch, changed):
    assembler, identity, report, paths = generation
    render = resume_renderer.build_template_resume

    def mutate_after_render(*args, **kwargs):
        content = render(*args, **kwargs)
        path = paths[changed]
        path.write_text(path.read_text() + "\n# newer source revision\n")
        return content

    monkeypatch.setattr(resume_renderer, "build_template_resume", mutate_after_render)
    with pytest.raises(ValueError, match="generation_input_changed"):
        assembler.generate(report, [identity], "v1")


@pytest.mark.parametrize("replacement", ['status: "draft"', 'status: ""'])
def test_template_assembler_does_not_recover_revoked_approval_from_domain_card(generation, replacement):
    assembler, identity, report, paths = generation
    card = paths["card"]
    card.write_text(card.read_text().replace('status: "saved_eligible"', replacement))
    with pytest.raises(ValueError, match="selected_evidence_ineligible"):
        assembler.generate(report, [identity], "v1")


def test_markdown_exporter_writes_content(tmp_path):
    resume = ResumeOutput("v2", "jp-test", "# Resume\n", "markdown")
    path = ResumeExporter().export_markdown(resume, str(tmp_path))
    assert path.read_text() == resume.content

@pytest.mark.parametrize("level,precision,expected", [
    ("L2", "year", "2024"), ("L2", "month", "2024-01 ~ 2024-06"), ("L3", "month", "2024"),
])
def test_engine_lower_precision_keeps_original_source_and_standard_trace(generation, level, precision, expected):
    import hashlib
    assembler, identity, report, paths = generation
    time_source = {"level": level, "precision": precision, "confirmed_by_user": True,
                   "evidence": [{"material_id": "mat-period", "document_id": "doc-period",
                                 "excerpt": "2024-01 ~ 2024-06"}]}
    role_source = {"level": "L3", "confirmed_by_user": True,
                   "evidence": [{"material_id": "mat-role", "document_id": "doc-role",
                                 "excerpt": "负责接口联调"}]}
    card = paths["card"]
    card.write_text(card.read_text() +
        "time_range_provenance_json: " + json.dumps(json.dumps(time_source)) + "\n" +
        "role_scope_provenance_json: " + json.dumps(json.dumps(role_source)) + "\n")
    original = card.read_bytes()
    resume = assembler.generate(report, [identity], "v1")
    assert "### 队列处理服务（" + expected + "）" in resume.content
    if precision == "year" or level == "L3":
        assert "2024-01" not in resume.content and "2024-06" not in resume.content
    assert "角色：负责接口联调" in resume.content and RESULT in resume.content
    assert card.read_bytes() == original
    trace = resume.generation_trace
    assert validate_generation_trace(resume.content, trace)
    assert trace["inputs"]["ec-engine"]["sha256"] == hashlib.sha256(original).hexdigest()
    provenance = trace["field_provenance"]["ec-engine"]
    assert provenance["time_range"]["level"] == level
    assert provenance["time_range"]["precision"] == precision
    assert provenance["time_range"]["evidence"] == time_source["evidence"]
    assert provenance["role_scope"]["confirmed_by_user"] is True


@pytest.mark.parametrize("mode", ["empty", "explicit_l5", "unconfirmed_l3"])
def test_engine_omits_unproven_role_but_keeps_valid_source_facts(generation, mode):
    assembler, identity, report, paths = generation
    card = paths["card"]
    text = card.read_text()
    if mode == "empty":
        text = text.replace('role_scope: "负责接口联调"', 'role_scope: ""')
    else:
        role = {"level": "L5"} if mode == "explicit_l5" else {
            "level": "L3", "evidence": [{"material_id": "m", "document_id": "d", "excerpt": "候选归属"}]}
        text += "role_scope_provenance_json: " + json.dumps(json.dumps(role)) + "\n"
    card.write_text(text)
    resume = assembler.generate(report, [identity], "v1")
    assert "角色：" not in resume.content
    assert "实现消费接口并完成测试联调" in resume.content and RESULT in resume.content
    assert validate_generation_trace(resume.content, resume.generation_trace)
