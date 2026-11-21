"""实际来源适配、唯一渲染和生成时版本绑定；所有资料均为合成夹具。"""
import hashlib
import json
from pathlib import Path
from dataclasses import replace

import pytest

from tests.unit.engines.test_complete_resume import complete_profile
from tests.unit.sidecar.test_evidence_source_merge import sample as source_sample, result_review_model
from tools.sidecar.handlers import evidence, profile as profile_api

from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.engines.generation.template_assembler import TemplateAssembler
from tools.engines.generation import resume_renderer
from tools.engines.generation.exporter import ResumeExporter
from tools.infra.persistence.review_snapshot import validate_generation_trace

RESULT = "在隔离测试环境中，1000 条合成请求的 P95 从 200ms 降至 120ms。"


def write_reviewed_result_sources(card_path, measurement_quotes, *, material_dir):
    """Persist explicit synthetic reviewed inputs; this does not exercise or replace the reviewer."""
    from tests.unit.engines.test_fact_index import reviewed_result
    from tools.infra.material_documents import split_material_documents
    from tools.infra.persistence.yaml_io import parse_simple_yaml
    from tools.infra.evidence_sources import validated_source_inputs
    from tools.infra.evidence_fact_scope import current_result_reviews, result_review_basis, result_review_input

    doc = parse_simple_yaml(card_path.read_text())
    card_id = card_path.stem
    material_dir.mkdir(parents=True, exist_ok=True)
    material_id = "review-" + hashlib.sha256(str(card_path.absolute()).encode()).hexdigest()[:12]
    source_path = material_dir / (material_id + ".txt")
    values = doc["lists"].get("results", [])
    source_text = "# Source: synthetic-review.md\n" + "\n\n".join(values[index] for index in measurement_quotes)
    source_path.write_text(source_text)
    document, = split_material_documents(source_text, source_path.name)
    reference = {"material_id": material_id, "document_id": document["document_id"], "sha256": document["sha256"]}
    rows = []
    for index, quote in measurement_quotes.items():
        row = reviewed_result(card_id, index, values[index], measurement_quote=quote)
        rows.append({**row, "source": {**reference, "quote": values[index]}})
    doc["scalars"].update({
        "id": card_id, "status": "saved_eligible", "candidate_pool_eligible": "true", "review_decision": "approved",
        "source_documents_json": json.dumps([reference]),
        "source_whole_material_ids_json": "[]",
        "source_material_fingerprints_json": json.dumps({material_id: {
            "filename": source_path.name, "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()}}),
        "field_sources_json": json.dumps([
            {"field": "results", "value": row["value"], "material_id": material_id,
             "document_id": document["document_id"], "quote": row["source"]["quote"]} for row in rows]),
        "reviewed_facts_json": json.dumps({"fact_scope_v1": rows}),
    })
    doc["lists"]["source_material_ids"] = [material_id]
    sources = validated_source_inputs(doc, material_dir)
    bindings = json.loads(doc["scalars"]["field_sources_json"])
    for row in rows:
        review_input = result_review_input(card_id, row, rows, bindings, [reference], sources.documents)
        row["result_review"]["basis_sha256"] = result_review_basis(review_input)
    doc["scalars"]["reviewed_facts_json"] = json.dumps({"fact_scope_v1": rows})
    assert set(current_result_reviews(doc, material_dir, card_id=card_id, validated_sources=sources)) == {
        f"{card_id}:results:{index}" for index in measurement_quotes}
    lines = [key + ": " + json.dumps(value, ensure_ascii=False) for key, value in doc["scalars"].items()]
    for key, values in doc["lists"].items():
        lines.append(key + ":")
        lines.extend("  - " + json.dumps(value, ensure_ascii=False) for value in values)
    card_path.write_text("\n".join(lines) + "\n")
    return sources


@pytest.fixture
def generation(tmp_path):
    evidence = tmp_path / "evidence_cards"
    evidence.mkdir(exist_ok=True)
    card_path = evidence / "ec-engine.yaml"
    card_path.write_text(
        'id: "ec-engine"\ntitle: "队列处理服务"\nstatus: "saved_eligible"\n'
        'candidate_pool_eligible: "true"\ntime_range: "2024-01 ~ 2024-06"\n'
        'context: "合成队列处理验收"\nrole_scope: "负责接口联调"\n'
        'actions:\n  - "实现消费接口并完成测试联调"\n'
        'results:\n  - ' + json.dumps(RESULT, ensure_ascii=False) +
        '\nstack:\n  - "Java"\nartifacts:\n  - "合成测试报告"\n'
    )
    write_reviewed_result_sources(card_path, {0: RESULT}, material_dir=tmp_path / "materials")
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


@pytest.mark.parametrize("source_sample,outcome,measured", [
    ((["实现预约请求幂等校验与消息重试机制。"],
      ["隔离测试中，固定负载下接口响应时间减半。"]), "established", True),
    ((["实现预约请求幂等校验与消息重试机制。"],
      ["完成容量评估报告，报告列出的下期目标是承载 100 万请求，尚未上线。"]), "established", False),
    ((["实现预约请求幂等校验与消息重试机制。"],
      ["待核记录声称隔离测试接口耗时降低一半，缺少当次测量条件。"]), "unknown", False),
], indirect=["source_sample"])
def test_saved_result_review_reaches_generated_trace_and_actual_quality_flow(
        source_sample, result_review_model, outcome, measured):
    from tests.unit.sidecar.test_evidence_source_merge import _scoped_review
    from tools.infra.persistence.review_snapshot import read_generation_trace
    from tools.orchestration.evaluation_flow import EvaluationFlowConfig, run_evaluation_flow

    material_dir, card, params, scope = _scoped_review(source_sample, field="results")
    value = scope["value"]
    result_review_model["reply"] = {"outcome": outcome,
        "measurement_quote": value if measured else None,
        "rationale": "独立合成来源：报告交付与计划指标分开，实测保留固定负载和隔离范围。"}
    params["review"]["fact_scope"] = scope
    evidence.handle_evidence_save_draft(params)
    detail = evidence.handle_evidence_get({"meta": params["meta"], "evidence_id": card.stem})["evidence"]
    stored = detail["fact_scope_review"][0]["sources"][0]["result_review"]
    assert stored["outcome"] == outcome and stored["measurement_quote"] == (value if measured else None)

    profile = material_dir.parent / "personal_profile.yaml"
    profile.write_text('name: "合成结果候选人"\ncurrent_position: "工程师"\n')
    job = material_dir.parent / "jp-result.yaml"
    job.write_text('target_role: "工程师"\ncompany: "合成公司"\nsource_jd: "负责接口开发与回归验证"\n')
    assembler = TemplateAssembler(evidence_dir=card.parent, personal_profile_path=profile, job_profile_path=job)
    identity = EvidenceCard(card.stem, "仅作选择边界", "", ("禁止采用领域DTO正文",), ("证据",))
    resume = assembler.generate(MatchingReport(job.stem, (card.stem,), {}, ()), [identity], "reviewed")
    action = params["draft"]["actions"][0]
    assert action in resume.content
    assert (value in resume.content) is (outcome == "established")
    assert "禁止采用领域DTO正文" not in resume.content
    claims = [claim for claim in resume.generation_trace["claims"] if claim.get("fact_id") == card.stem + ":results:0"]
    assert len(claims) == int(outcome == "established")
    if claims:
        assert claims[0]["text"] == value

    resume_path = material_dir.parent / "synthetic-resume.md"
    resume_path.write_text(resume.content)
    resume_path.with_suffix(".trace.json").write_text(json.dumps(resume.generation_trace))
    assert read_generation_trace(resume_path)[1]
    output = material_dir.parent / "synthetic-quality.md"
    assert run_evaluation_flow(EvaluationFlowConfig(
        input_path=resume_path, output_path=output, job_profile_path=job)) == 0
    result = json.loads(output.with_suffix(".json").read_text())
    assert result["traceability"]["status"] == "verified"
    assert result["quality_report"]["tiers"]["strong"]["metrics"]["quant_total"] == (0.5 if measured else 0.0)
    assert result["quality_report"]["auto_pass"] is False
    assert len(result_review_model["calls"]) == 1


@pytest.fixture
def career_generation(generation, source_sample, monkeypatch):
    materials_dir, indirect_card, review = source_sample
    evidence.handle_evidence_save_draft(review)
    _, identity, _, paths = generation
    basic = complete_profile()
    career = basic.pop("career")
    career["work"][0]["evidence_ids"] = [identity.id]
    contribution = review["draft"]["actions"][0]
    career["work"].append({
        **career["work"][0], "id": "indirect", "company": "合成平台公司",
        "current": True, "end": "", "scope": "统一预约平台",
        "contributions": [contribution], "evidence_ids": [indirect_card.stem],
    })
    career["skills"][0]["evidence_ids"] = [identity.id, indirect_card.stem]
    monkeypatch.setattr(profile_api, "_PROFILE_PATH", paths["profile"])
    meta = {"correlation_id": "career-source-generation"}
    current = profile_api.handle_profile_get({"meta": meta})["profile"]
    profile_api.handle_profile_update({
        "meta": meta, "expected_revision": current["revision"],
        "patch": {**basic, "career": career},
    })
    current = profile_api.handle_profile_get({"meta": meta})["profile"]
    profile_api.handle_profile_review({
        "meta": meta, "expected_revision": current["revision"], "confirmed": True,
    })
    assert profile_api.handle_profile_get({"meta": meta})["profile"]["career_status"]["reviewed"]
    return generation, materials_dir, indirect_card, contribution, meta


def test_career_sources_remain_bound_without_selecting_the_indirect_card(career_generation):
    generation, materials_dir, indirect_card, contribution, meta = career_generation
    assembler, identity, report, paths = generation
    original_profile = paths["profile"].read_bytes()
    resume = assembler.generate(report, [identity], "v1")
    trace = resume.generation_trace
    assert validate_generation_trace(resume.content, trace)
    row, = [claim for claim in trace["claims"]
            if claim.get("fact_id") == "personal_profile:career.work.indirect.contributions:0"]
    assert row["source_kind"] == "personal_profile" and row["text"] == contribution
    assert contribution in resume.content
    assert trace["evidence_card_ids"] == [identity.id]
    assert not any(claim.get("evidence_id") == indirect_card.stem for claim in trace["claims"])
    assert Path(trace["inputs"]["career_evidence:" + indirect_card.stem]["path"]) == indirect_card
    for material_id in ("m1", "m2"):
        source = materials_dir / f"{material_id}.txt"
        assert trace["inputs"][f"evidence_material:{material_id}"] == {
            "path": str(source.resolve()), "exists": True,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    public_profile = profile_api.handle_profile_get({"meta": meta})["profile"]
    json.dumps(public_profile)
    assert "material_inputs" not in public_profile
    assert paths["profile"].read_bytes() == original_profile


@pytest.mark.parametrize("when", ["before", "during", "after", "missing_fingerprint"])
def test_indirect_career_material_change_invalidates_generation(career_generation, monkeypatch, when):
    generation, materials_dir, indirect_card, _, meta = career_generation
    assembler, identity, report, _ = generation
    source = materials_dir / "m1.txt"

    def change_source():
        source.write_text(source.read_text() + "\n已修订的来源。\n")

    if when in {"before", "missing_fingerprint"}:
        if when == "before":
            change_source()
        else:
            indirect_card.write_text("\n".join(
                line for line in indirect_card.read_text().splitlines()
                if not line.startswith("source_material_fingerprints_json:")
            ) + "\n")
        public = profile_api.handle_profile_get({"meta": meta})["profile"]
        assert public["career_status"]["reviewed"] is False
        assert any(item["field"] == "evidence." + indirect_card.stem
                   for item in public["career_status"]["missing"])
        json.dumps(public)
        with pytest.raises(ValueError, match="material_source|field_source|generation_input_changed"):
            assembler.generate(report, [identity], "v1")
    elif when == "during":
        render = resume_renderer.build_template_resume
        def render_then_change(*args, **kwargs):
            content = render(*args, **kwargs)
            change_source()
            return content
        monkeypatch.setattr(resume_renderer, "build_template_resume", render_then_change)
        with pytest.raises(ValueError, match="generation_input_changed|material_source"):
            assembler.generate(report, [identity], "v1")
    else:
        resume = assembler.generate(report, [identity], "v1")
        assert validate_generation_trace(resume.content, resume.generation_trace)
        change_source()
        assert not validate_generation_trace(resume.content, resume.generation_trace)


def test_career_trace_keeps_the_path_actually_read_before_directory_switch(career_generation, monkeypatch):
    generation, _, indirect_card, _, _ = career_generation
    _, identity, report, paths = generation
    external = paths["profile"].parent / "external"
    external.mkdir()
    profile_path = external / paths["profile"].name
    profile_path.write_bytes(paths["profile"].read_bytes())
    monkeypatch.chdir(paths["profile"].parent)
    assembler = TemplateAssembler(evidence_dir=paths["card"].parent,
                                  personal_profile_path=profile_path, job_profile_path=paths["job"])
    render = resume_renderer.build_template_resume
    def render_then_add_local_copies(*args, **kwargs):
        content = render(*args, **kwargs)
        copies = external / "evidence_cards"
        copies.mkdir()
        for source in (paths["card"], indirect_card):
            (copies / source.name).write_bytes(source.read_bytes())
        return content
    monkeypatch.setattr(resume_renderer, "build_template_resume", render_then_add_local_copies)
    resume = assembler.generate(report, [identity], "v1")
    assert Path(resume.generation_trace["inputs"]["career_evidence:" + indirect_card.stem]["path"]) == indirect_card
    indirect_card.write_text(indirect_card.read_text() + "\n# changed original card\n")
    assert not validate_generation_trace(resume.content, resume.generation_trace)


def test_unreferenced_source_change_does_not_block_an_incomplete_career(generation, source_sample):
    materials_dir, unused_card, review = source_sample
    evidence.handle_evidence_save_draft(review)
    (materials_dir / "m1.txt").write_text("不关联的来源已变更。")
    assembler, identity, report, _ = generation
    resume = assembler.generate(report, [identity], "v1")
    assert validate_generation_trace(resume.content, resume.generation_trace)
    assert resume.generation_trace["readiness"]["status"] == "NEEDS_EVIDENCE"
    assert unused_card.stem not in resume.generation_trace["evidence_card_ids"]
    assert not any("m1.txt" in item["path"] or unused_card.name in item["path"]
                   for item in resume.generation_trace["inputs"].values())


@pytest.mark.parametrize("case", ["same", "relative", "different_path", "different_hash"])
def test_career_capture_rejects_conflicts_without_overwriting_prior_snapshot(career_generation, monkeypatch, case):
    from tools.infra.career_profile import inspect_career
    from tools.infra.persistence.yaml_io import parse_simple_yaml

    generation, materials_dir, _, _, _ = career_generation
    _, _, _, paths = generation
    source = materials_dir / "m1.txt"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    captured_path = source
    if case == "relative":
        monkeypatch.chdir(materials_dir.parent)
        captured_path = Path("materials/m1.txt")
    elif case == "different_path":
        captured_path = materials_dir / "same-bytes.txt"
        captured_path.write_bytes(source.read_bytes())
    captures = {"evidence_material:m1": (captured_path, "0" * 64 if case == "different_hash" else digest)}
    before = dict(captures)
    fields = parse_simple_yaml(paths["profile"].read_text())["scalars"]
    if case.startswith("different_"):
        with pytest.raises(ValueError, match="material_source_changed"):
            inspect_career(fields, paths["card"].parent, captured_sources=captures)
        assert captures == before
    else:
        public = inspect_career(fields, paths["card"].parent)
        assert inspect_career(fields, paths["card"].parent, captured_sources=captures) == public
        assert captures["evidence_material:m1"] == before["evidence_material:m1"]
        json.dumps(public)


def test_missing_indirect_career_card_still_blocks_generation(career_generation):
    generation, _, indirect_card, _, meta = career_generation
    indirect_card.unlink()
    public = profile_api.handle_profile_get({"meta": meta})["profile"]
    assert any(item["field"] == "evidence." + indirect_card.stem
               for item in public["career_status"]["missing"])
    json.dumps(public)
    assembler, identity, report, _ = generation
    with pytest.raises(ValueError, match="generation_input_changed"):
        assembler.generate(report, [identity], "v1")


def test_unrelated_card_material_is_not_a_career_generation_dependency(career_generation):
    generation, materials_dir, _, _, _ = career_generation
    mid = "unused"
    source = materials_dir / f"{mid}.txt"
    source.write_text("# Source: 无关项目.md\n无关项目验收通过。\n")
    (materials_dir / f"{mid}.meta.yaml").write_text(
        f'material_id: "{mid}"\nfilename: "{mid}.txt"\nextension: ".txt"\nlabel: "无关项目"\n')
    document = evidence.handle_list_material_documents({"material_id": mid})["items"][0]
    unused_id = evidence.handle_evidence_save_draft({
        "meta": {"correlation_id": "unrelated-source"}, "review": {"decision": "approved"}, "save_mode": "eligible",
        "draft": {"source_material_ids": [mid],
                  "source_documents": [{"material_id": mid, **{key: document[key] for key in ("document_id", "sha256", "label")}}],
                  "title": "无关项目", "time_range": "", "context": "独立验收", "role_scope": "",
                  "actions": [], "results": ["无关项目验收通过。"], "stack": [], "tags": [],
                  "artifacts": [{"type": "text_document", "ref": mid, "label": "验收"}]},
    })["evidence_id"]
    assembler, identity, report, paths = generation
    resume = assembler.generate(report, [identity], "v1")
    assert f"career_evidence:{unused_id}" not in resume.generation_trace["inputs"]
    assert f"evidence_material:{mid}" not in resume.generation_trace["inputs"]
    assert unused_id not in resume.generation_trace["evidence_card_ids"]
    source.write_text("不相关材料已改变。")
    unused_card = paths["card"].parent / f"{unused_id}.yaml"
    unused_card.write_text(unused_card.read_text() + "\n# unused card changed\n")
    assert validate_generation_trace(resume.content, resume.generation_trace)
    current = assembler.generate(report, [identity], "v2")
    assert validate_generation_trace(current.content, current.generation_trace)


@pytest.mark.parametrize("change_during_render", [False, True])
def test_formal_generation_shares_indirect_career_source_capture(career_generation, monkeypatch, change_during_render):
    from tools.orchestration.generation_flow import GenerationFlowConfig, run_generation_flow
    from tools.infra.persistence.review_snapshot import read_generation_trace

    generation, materials_dir, indirect_card, contribution, _ = career_generation
    _, identity, _, paths = generation
    root = paths["profile"].parent
    staged = root / "selected"
    staged.mkdir()
    (staged / paths["card"].name).write_bytes(paths["card"].read_bytes())
    matching = root / "matching.yaml"
    matching.write_text(f'top_cards:\n  - id: "{identity.id}"\n')
    output = root / "formal"
    if change_during_render:
        render = resume_renderer.build_template_resume
        def render_then_change(*args, **kwargs):
            content = render(*args, **kwargs)
            source = materials_dir / "m1.txt"
            source.write_text(source.read_text() + "\n新的材料版本。\n")
            return content
        monkeypatch.setattr(resume_renderer, "build_template_resume", render_then_change)
    code = run_generation_flow(GenerationFlowConfig(
        matching_report_path=matching, output_dir=output, personal_profile_path=paths["profile"],
        evidence_dir=staged, job_profile_path=paths["job"],
    ))
    if change_during_render:
        assert code == 1 and not list(output.glob("*.md"))
    else:
        assert code == 0
        resume = output / "resume_matching_A.md"
        trace, valid = read_generation_trace(resume)
        assert valid and contribution in resume.read_text()
        assert trace["evidence_card_ids"] == [identity.id]
        assert "career_evidence:" + indirect_card.stem in trace["inputs"]
        assert "evidence_material:m1" in trace["inputs"]


@pytest.mark.parametrize("source_sample", [(["完成统一预约平台复用能力的接口设计与联调。"], ["模块验收通过。"])], indirect=True)
def test_direct_and_career_sources_share_relative_and_absolute_paths(career_generation, monkeypatch):
    generation, materials_dir, indirect_card, _, _ = career_generation
    _, identity, report, paths = generation
    external = paths["profile"].parent / "profile-copy"
    external.mkdir()
    profile_path = external / paths["profile"].name
    profile_path.write_bytes(paths["profile"].read_bytes())
    monkeypatch.chdir(paths["profile"].parent)
    assembler = TemplateAssembler(evidence_dir=paths["card"].parent,
                                  personal_profile_path=profile_path, job_profile_path=paths["job"])
    resume = assembler.generate(replace(report, evidence_card_ids=(indirect_card.stem,)),
                                [replace(identity, id=indirect_card.stem)], "v1")
    assert validate_generation_trace(resume.content, resume.generation_trace)
    assert resume.generation_trace["evidence_card_ids"] == [indirect_card.stem]
    assert resume.generation_trace["inputs"]["evidence_material:m1"]["path"] == str((materials_dir / "m1.txt").resolve())
