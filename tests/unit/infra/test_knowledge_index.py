"""知识索引构建器：材料/文档/卡片/档案/岗位的确定性导航索引（非 RAG）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.infra.material_documents import split_material_documents

BUNDLE = (
    "# Source: 02-CustomerA/调研.md\n"
    "---\n"
    "title: 改造调研\n"
    "created: '2017-02-13T05:37:09Z'\n"
    "updated: '2017-02-15T03:49:02Z'\n"
    "---\n"
    "\n"
    "# 改造调研\n"
    "\n"
    "正文提到 2017-02 与 2018-05 的一些事。\n"
    "# Source: 02-CustomerA/上线安排.md\n"
    "---\n"
    "title: 上线安排\n"
    "created: '2018-06-01T00:00:00Z'\n"
    "---\n"
    "上线安排正文。\n"
    "# Source: 02-CustomerA/05-全量验收.md\n"
    "---\n"
    "title: 验收记录\n"
    "created: '2018-06-10T00:00:00Z'\n"
    "---\n"
    "全量验收通过。\n"
)


def _meta(material_id: str, label: str, filename: str, kind: str = "raw_work_material") -> str:
    return (
        f'material_id: "{material_id}"\n'
        f'label: "{label}"\n'
        f'kind: "{kind}"\n'
        f'filename: "{filename}"\n'
        f'uploaded_at: "2026-10-01T00:00:00Z"\n'
    )


def make_root(tmp_path: Path) -> Path:
    materials = tmp_path / "materials"
    materials.mkdir()
    (materials / "mat_aaaa1111.txt").write_text(BUNDLE, encoding="utf-8")
    (materials / "mat_aaaa1111.meta.yaml").write_text(
        _meta("mat_aaaa1111", "客户A项目记录", "mat_aaaa1111.txt", "raw_work_material_directory"), encoding="utf-8")
    timeline = "# 个人职业与教育时间线\n\n远帆科技 2016.04–2019.07。\n"
    (materials / "mat_timeline.md").write_text(timeline, encoding="utf-8")
    (materials / "mat_timeline.meta.yaml").write_text(
        _meta("mat_timeline", "已确认职业与教育时间线", "mat_timeline.md"), encoding="utf-8")
    summary_bundle = (
        "# Source: 00-CB/00-overview/工作汇总/工作汇总-1.md\n"
        "角色：Tech Lead / 全栈负责人\n"
        "# Source: 00-CB/00-overview/工作汇总/项目目录/客户甲/会员中心小程序/5 分钟速读卡.md\n"
        "系统概览。\n"
    )
    (materials / "mat_summary.txt").write_text(summary_bundle, encoding="utf-8")
    (materials / "mat_summary.meta.yaml").write_text(
        _meta("mat_summary", "CB 工作汇总与模块架构切片", "mat_summary.txt", "raw_work_material_directory"), encoding="utf-8")
    (materials / "mat_career_notes.md").write_text("# CB工作经历详细底稿\n\n2022 年 2 月起任 Tech Lead。\n", encoding="utf-8")
    (materials / "mat_career_notes.meta.yaml").write_text(
        _meta("mat_career_notes", "CB工作经历详细底稿", "mat_career_notes.md"), encoding="utf-8")
    (materials / "mat_quick_run_verify.md").write_text(
        "# Quick Run verifier material\n时间：2025-06 ~ 2025-09\n", encoding="utf-8")
    (materials / "mat_quick_run_verify.meta.yaml").write_text(
        _meta("mat_quick_run_verify", "Quick Run verifier material", "mat_quick_run_verify.md"), encoding="utf-8")

    docs = split_material_documents(BUNDLE, "mat_aaaa1111.txt")
    research = next(d for d in docs if d["label"] == "02-CustomerA/调研.md")
    refs = [{"document_id": research["document_id"], "sha256": research["sha256"],
             "label": research["label"], "material_id": "mat_aaaa1111"}]

    cards = tmp_path / "evidence_cards"
    cards.mkdir()
    (cards / "ec_1111aaaa.yaml").write_text(
        'id: "ec_1111aaaa"\n'
        'title: "客户A资金改造"\n'
        'time_range: ""\n'
        'role_scope: ""\n'
        'context: "客户A的资金系统改造。"\n'
        'status: "saved_eligible"\n'
        'candidate_pool_eligible: "true"\n'
        f'source_documents_json: {json.dumps(json.dumps(refs, ensure_ascii=False))}\n'
        'source_material_ids:\n'
        '  - "mat_aaaa1111"\n',
        encoding="utf-8")
    (cards / "ec-2026-001.yaml").write_text(
        'id: "ec-2026-001"\n'
        'title: "示例卡"\n'
        'time_range: "2026-01 ~ 2026-02"\n'
        'role_scope: "示例职责"\n'
        'context: "仓库示例。"\n',
        encoding="utf-8")

    timeline_docs = split_material_documents(timeline, "mat_timeline.md")
    pref_source = {"material_id": "mat_timeline", "document_id": timeline_docs[0]["document_id"],
                   "label": timeline_docs[0]["label"], "sha256": timeline_docs[0]["sha256"]}
    career = {"schema_version": 1, "summary": "", "work": [
        {"id": "work_example", "company": "云桥（CB）", "title": "Tech Lead", "start": "2022-02", "end": "",
         "scope": "", "current": True, "evidence_ids": ["ec_1111aaaa"], "contributions": []}],
        "education": [], "skills": [], "extras": []}
    prefs = {"schema_version": 1, "source": pref_source, "items": [{"kind": "primary", "text": "产品型", "quote": "主方向"}],
             "confirmed_at": "2026-10-12T12:22:21Z"}
    (tmp_path / "personal_profile.yaml").write_text(
        'name: "测试"\n'
        'updated_at: "2026-10-12T00:00:00Z"\n'
        f'career_json: {json.dumps(json.dumps(career, ensure_ascii=False))}\n'
        'career_review_json: "{\\"revision\\": \\"rev1234567890\\", \\"reviewed_at\\": \\"2026-10-12T00:00:00Z\\"}"\n'
        f'job_preferences_json: {json.dumps(json.dumps(prefs, ensure_ascii=False))}\n',
        encoding="utf-8")

    jobs = tmp_path / "job_profiles"
    jobs.mkdir()
    (jobs / "jp_abc12345.yaml").write_text(
        'target_role: "AI 工程师"\n'
        'company: "某公司"\n'
        'source_jd: "做一个 AI 系统"\n'
        'status: "active"\n'
        'job_lead_id: "jl_liepin_aaa111"\n'
        'created_at: "2026-10-01T00:00:00Z"\n'
        'updated_at: "2026-10-01T00:00:00Z"\n'
        'source_jd_sha256: "deadbeef"\n',
        encoding="utf-8")
    (jobs / "jp-2026-001.yaml").write_text('target_role: "示例岗位"\ncompany: "示例公司"\n', encoding="utf-8")

    leads = tmp_path / "job_leads"
    leads.mkdir()
    (leads / "jl_liepin_aaa111.yaml").write_text(
        'id: "jl_liepin_aaa111"\n'
        'company: "米高蒲志"\n'
        'position: "Sr Full Stack"\n'
        'source: "liepin_official"\n'
        'status: "new"\n'
        'favorited: "false"\n'
        'job_profile_id: "jp_abc12345"\n'
        'salary: "45-83k·15薪"\n'
        'location: "广州"\n'
        'company_size: "5000-10000人"\n'
        'industry: "人力资源服务"\n'
        'created_at: "2026-10-14T00:00:00Z"\n',
        encoding="utf-8")
    (leads / "jl-2026-001.yaml").write_text('company: "示例公司"\nposition: "示例岗位"\n', encoding="utf-8")
    return tmp_path


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return make_root(tmp_path)


def _build(root: Path):
    from tools.infra import knowledge_index
    return knowledge_index.build_index(root, now="2026-10-17T00:00:00+00:00")


def test_materials_and_documents(root: Path):
    index = _build(root)
    mat = index["materials"]["mat_aaaa1111"]
    assert mat["document_count"] == 3
    assert mat["frontmatter_dated"] == 3
    assert mat["sha256"] == hashlib.sha256((root / "materials" / "mat_aaaa1111.txt").read_bytes()).hexdigest()
    docs = {d["label"]: d for d in mat["documents"]}
    research = docs["02-CustomerA/调研.md"]
    assert research["title"] == "改造调研"
    assert research["doc_type"] == "文档"
    assert research["dates"]["frontmatter"] == {"created": "2017-02-13", "updated": "2017-02-15"}
    assert research["dates"]["window"] == ["2017-02", "2018-05"]
    assert research["sha256"]
    assert docs["02-CustomerA/05-全量验收.md"]["doc_type"] == "验收"
    assert docs["02-CustomerA/上线安排.md"]["dates"]["frontmatter"]["created"] == "2018-06-01"
    bbbb = index["materials"]["mat_timeline"]["documents"][0]
    assert bbbb["title"] == "个人职业与教育时间线"
    assert bbbb["dates"]["window"] == ["2016-04", "2019-07"]


def test_cards_completion_fields(root: Path):
    index = _build(root)
    card = index["cards"]["ec_1111aaaa"]
    assert card["title"] == "客户A资金改造"
    assert card["demo"] is False
    assert card["missing"] == ["time_range", "role_scope"]
    assert card["employer"] == "CB"
    assert card["date_hints"] == ["2017-02", "2018-05"]
    assert card["sha256"] == hashlib.sha256((root / "evidence_cards" / "ec_1111aaaa.yaml").read_bytes()).hexdigest()
    assert card["source_documents"][0]["material_id"] == "mat_aaaa1111"
    assert card["source_documents"][0]["label"] == "02-CustomerA/调研.md"


def test_demo_card_flagged_without_status(root: Path):
    index = _build(root)
    demo = index["cards"]["ec-2026-001"]
    assert demo["demo"] is True
    assert demo["missing"] == []


def test_relations_cover_cites_evidence_and_preferences(root: Path):
    index = _build(root)
    rels = {(r["from"], r["type"]) for r in index["relations"]}
    assert ("card:ec_1111aaaa", "cites") in rels
    assert ("work:work_example", "evidence") in rels
    assert ("profile:job_preferences", "sourced_from") in rels
    cites = [r for r in index["relations"] if r["from"] == "card:ec_1111aaaa" and r["type"] == "cites"][0]
    assert cites["to"].startswith("doc:mat_aaaa1111:")
    evidence = [r for r in index["relations"] if r["type"] == "evidence"][0]
    assert evidence["to"] == "card:ec_1111aaaa"


def test_profile_and_jobs(root: Path):
    index = _build(root)
    profile = index["profile"]
    assert profile["work"][0]["short"] == "CB"
    assert profile["work"][0]["evidence_ids"] == ["ec_1111aaaa"]
    assert profile["job_preferences"]["source"]["material_id"] == "mat_timeline"
    assert index["jobs"]["jp_abc12345"]["demo"] is False
    assert index["jobs"]["jp-2026-001"]["demo"] is True
    assert index["jobs"]["jp_abc12345"]["jd_chars"] == len("做一个 AI 系统")


def test_index_does_not_assign_personal_authority_to_material_identifiers(root: Path):
    index = _build(root)
    assert "person_docs" not in index
    assert all("person_doc" not in doc for material in index["materials"].values()
               for doc in material["documents"])
    nonfact = {n["material_id"]: n["reason"] for n in index["nonfact_materials"]}
    assert "mat_quick_run_verify" in nonfact
    assert "事实" in nonfact["mat_quick_run_verify"]


@pytest.mark.parametrize("name, expected", [
    ("星河信息技术有限公司", "星河"),
    ("上海远帆金融信息服务有限公司", "远帆"),
    ("云桥科技（CB）", "CB"),
    ("", ""),
])
def test_company_short_name_uses_general_alias_rules(name: str, expected: str):
    from tools.infra.knowledge_index import short_company
    assert short_company(name) == expected


def test_render_index_md_sections(root: Path):
    from tools.infra import knowledge_index
    index = _build(root)
    md = knowledge_index.render_index_md(index)
    assert "知识索引" in md
    assert "2026-10-17T00:00:00+00:00" in md
    assert "mat_aaaa1111" in md
    assert "3 档" in md or "：3" in md
    assert "mat_quick_run_verify" in md
    assert "岗位线索" in md
    assert "索引缺口" in md
    assert "本地来源根" in md
    assert "缺" in md
    assert "kb read" in md


def test_verify_clean_then_stale(root: Path):
    from tools.infra import knowledge_index
    index = _build(root)
    assert knowledge_index.verify_index(root, index) == []
    (root / "materials" / "mat_aaaa1111.txt").write_text(BUNDLE + "# Source: 02-CustomerA/新档.md\n新内容。\n", encoding="utf-8")
    (root / "evidence_cards" / "ec_1111aaaa.yaml").write_text("id: \"ec_1111aaaa\"\n", encoding="utf-8")
    stale = knowledge_index.verify_index(root, index)
    refs = {(entry["kind"], entry["ref"]) for entry in stale}
    assert ("material", "mat_aaaa1111") in refs
    assert ("card", "ec_1111aaaa") in refs




@pytest.mark.parametrize(
    ("relative", "digest_path"),
    [
        ("materials/mat_aaaa1111.meta.yaml", ()),
        ("evidence_cards/ec_1111aaaa.yaml", ("cards", "ec_1111aaaa", "sha256")),
        ("personal_profile.yaml", ("profile", "file_sha256")),
        ("job_profiles/jp_abc12345.yaml", ("jobs", "jp_abc12345", "sha256")),
        ("job_leads/jl_liepin_aaa111.yaml", ("leads", "jl_liepin_aaa111", "sha256")),
    ],
)
def test_l4_inventory_and_entity_digest_bind_the_bytes_that_were_parsed(root, monkeypatch, relative, digest_path):
    from tools.infra import knowledge_index

    monkeypatch.setenv("PPF_POLICY_PATH", str(root / "policy.yaml"))
    target = root / relative
    original = target.read_bytes()
    actual_parse = knowledge_index.parse_simple_yaml
    changed = False

    def parse_then_change(text):
        nonlocal changed
        result = actual_parse(text)
        if not changed and text == original.decode("utf-8"):
            changed = True
            target.write_bytes(original + b"\nchanged_during_read: true\n")
        return result

    monkeypatch.setattr(knowledge_index, "parse_simple_yaml", parse_then_change)
    index = _build(root)
    assert changed
    expected = hashlib.sha256(original).hexdigest()
    assert index["asset_inventory"][relative] == expected
    if digest_path:
        actual = index
        for part in digest_path:
            actual = actual[part]
        assert actual == expected


def test_l4_material_documents_hash_and_size_use_the_same_read(root, monkeypatch):
    from tools.infra import knowledge_index

    monkeypatch.setenv("PPF_POLICY_PATH", str(root / "policy.yaml"))
    path = root / "materials" / "mat_aaaa1111.txt"
    original = path.read_bytes()
    actual_split = knowledge_index.split_material_documents
    changed = False

    def split_then_change(text, filename):
        nonlocal changed
        documents = actual_split(text, filename)
        if not changed and filename == path.name:
            changed = True
            path.write_bytes(original + b"\nA later source version.\n")
        return documents

    monkeypatch.setattr(knowledge_index, "split_material_documents", split_then_change)
    index = _build(root)
    material = index["materials"]["mat_aaaa1111"]
    assert changed
    assert material["sha256"] == hashlib.sha256(original).hexdigest()
    assert material["bytes"] == len(original)
    assert [doc["document_id"] for doc in material["documents"]] == [
        doc["document_id"] for doc in actual_split(original.decode("utf-8"), path.name)
    ]


@pytest.mark.parametrize("filename", ["index.json", "INDEX.md"])
def test_l4_failed_index_publication_preserves_each_previous_file(root, monkeypatch, filename):
    from tools.infra import knowledge_index
    from tools.infra.persistence import atomic_io

    monkeypatch.setenv("PPF_POLICY_PATH", str(root / "policy.yaml"))
    index = _build(root)
    out = root / "knowledge-index"
    knowledge_index.save_index(index, out)
    previous = (out / filename).read_bytes()
    actual_replace = atomic_io.os.replace

    def fail_selected_publication(source, destination, *args, **kwargs):
        if Path(destination) == out / filename:
            raise OSError("synthetic publication failure")
        return actual_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(atomic_io.os, "replace", fail_selected_publication)
    with pytest.raises(OSError, match="synthetic publication failure"):
        knowledge_index.save_index({**index, "built_at": "later snapshot"}, out)
    assert (out / filename).read_bytes() == previous


@pytest.mark.parametrize("link_kind", ["directory", "index_file"])
def test_l4_index_destination_does_not_write_through_escaping_symlinks(tmp_path, monkeypatch, link_kind):
    from tools.infra import knowledge_index

    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("PPF_POLICY_PATH", str(project / "policy.yaml"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "index.json").write_text("outside JSON must remain", encoding="utf-8")
    (outside / "INDEX.md").write_text("outside Markdown must remain", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in outside.iterdir()}
    out = project / "knowledge-index"
    if link_kind == "directory":
        out.symlink_to(outside, target_is_directory=True)
    else:
        out.mkdir()
        (out / "index.json").symlink_to(outside / "index.json")
    try:
        knowledge_index.save_index(_build(project), out)
    except (ValueError, OSError):
        pass
    assert {path.name: path.read_bytes() for path in outside.iterdir()} == before


@pytest.mark.parametrize("escape", ["relative_parent", "symlink"])
def test_l4_index_material_navigation_stays_inside_registered_library(tmp_path, monkeypatch, escape):
    from tools.infra import knowledge_index

    project = tmp_path / "project"
    materials = project / "materials"
    materials.mkdir(parents=True)
    monkeypatch.setenv("PPF_POLICY_PATH", str(project / "policy.yaml"))
    outside = project / "outside.txt"
    outside.write_text("This source was not imported into the material library.", encoding="utf-8")
    filename = "../outside.txt"
    if escape == "symlink":
        filename = "linked.txt"
        (materials / filename).symlink_to(outside)
    (materials / "mat_escape.meta.yaml").write_text(
        _meta("mat_escape", "unavailable registered source", filename), encoding="utf-8")
    index = knowledge_index.build_index(project)
    assert "mat_escape" not in index["materials"]
    assert any(item["kind"] == "material" and item["file"] == "mat_escape.meta.yaml"
               for item in index["skipped"])


def test_build_is_deterministic(root: Path):
    assert _build(root) == _build(root)


def test_leads_entity_and_demo(root: Path):
    index = _build(root)
    lead = index["leads"]["jl_liepin_aaa111"]
    assert lead["position"] == "Sr Full Stack"
    assert lead["company"] == "米高蒲志"
    assert lead["status"] == "new"
    assert lead["demo"] is False
    assert lead["job_profile_id"] == "jp_abc12345"
    assert lead["company_size"] == "5000-10000人"
    assert lead["salary"] == "45-83k·15薪"
    assert index["leads"]["jl-2026-001"]["demo"] is True
    assert index["assets"]["leads"] == {"real": 1, "samples": 1}


def test_lead_job_relation_single_edge(root: Path):
    index = _build(root)
    edges = [r for r in index["relations"] if r["type"] == "promoted_to"]
    assert edges == [{"from": "lead:jl_liepin_aaa111", "type": "promoted_to", "to": "job:jp_abc12345"}]


def test_skipped_records_missing_material_target(tmp_path: Path):
    root = make_root(tmp_path)
    (root / "materials" / "mat_deadbeef.meta.yaml").write_text(
        'material_id: "mat_deadbeef"\nfilename: "mat_missing.md"\n', encoding="utf-8")
    index = _build(root)
    assert any(s["kind"] == "material" and s["file"] == "mat_deadbeef.meta.yaml"
               and s["error"] == "filename_missing" for s in index["skipped"])
