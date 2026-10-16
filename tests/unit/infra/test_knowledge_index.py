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
    timeline = "# 个人职业与教育时间线\n\n九恒星 2015.06–2018.10。\n"
    (materials / "mat_331bc1bc.md").write_text(timeline, encoding="utf-8")
    (materials / "mat_331bc1bc.meta.yaml").write_text(
        _meta("mat_331bc1bc", "已确认职业与教育时间线", "mat_331bc1bc.md"), encoding="utf-8")
    summary_bundle = (
        "# Source: 00-EC+/00-overview/工作汇总/工作汇总-1.md\n"
        "角色：Tech Lead / 全栈负责人\n"
        "# Source: 00-EC+/00-overview/工作汇总/项目目录/始祖鸟/会员中心小程序/5 分钟速读卡.md\n"
        "系统概览。\n"
    )
    (materials / "mat_7dad703c.txt").write_text(summary_bundle, encoding="utf-8")
    (materials / "mat_7dad703c.meta.yaml").write_text(
        _meta("mat_7dad703c", "EC+ 工作汇总与模块架构切片", "mat_7dad703c.txt", "raw_work_material_directory"), encoding="utf-8")
    (materials / "mat_723e3040.md").write_text("# EC+工作经历详细底稿\n\n2021 年 3 月起任 Tech Lead。\n", encoding="utf-8")
    (materials / "mat_723e3040.meta.yaml").write_text(
        _meta("mat_723e3040", "EC+工作经历详细底稿", "mat_723e3040.md"), encoding="utf-8")
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

    timeline_docs = split_material_documents(timeline, "mat_331bc1bc.md")
    pref_source = {"material_id": "mat_331bc1bc", "document_id": timeline_docs[0]["document_id"],
                   "label": timeline_docs[0]["label"], "sha256": timeline_docs[0]["sha256"]}
    career = {"schema_version": 1, "summary": "", "work": [
        {"id": "work_ecplus", "company": "一里智辉（EC+）", "title": "Tech Lead", "start": "2021-03", "end": "",
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
        'created_at: "2026-10-01T00:00:00Z"\n'
        'updated_at: "2026-10-01T00:00:00Z"\n'
        'source_jd_sha256: "deadbeef"\n',
        encoding="utf-8")
    (jobs / "jp-2026-001.yaml").write_text('target_role: "示例岗位"\ncompany: "示例公司"\n', encoding="utf-8")
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
    bbbb = index["materials"]["mat_331bc1bc"]["documents"][0]
    assert bbbb["title"] == "个人职业与教育时间线"
    assert bbbb["dates"]["window"] == ["2015-06", "2018-10"]


def test_cards_completion_fields(root: Path):
    index = _build(root)
    card = index["cards"]["ec_1111aaaa"]
    assert card["title"] == "客户A资金改造"
    assert card["demo"] is False
    assert card["missing"] == ["time_range", "role_scope"]
    assert card["employer"] == "EC+"
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
    assert ("work:work_ecplus", "evidence") in rels
    assert ("profile:job_preferences", "sourced_from") in rels
    cites = [r for r in index["relations"] if r["from"] == "card:ec_1111aaaa" and r["type"] == "cites"][0]
    assert cites["to"].startswith("doc:mat_aaaa1111:")
    evidence = [r for r in index["relations"] if r["type"] == "evidence"][0]
    assert evidence["to"] == "card:ec_1111aaaa"


def test_profile_and_jobs(root: Path):
    index = _build(root)
    profile = index["profile"]
    assert profile["work"][0]["short"] == "EC+"
    assert profile["work"][0]["evidence_ids"] == ["ec_1111aaaa"]
    assert profile["job_preferences"]["source"]["material_id"] == "mat_331bc1bc"
    assert index["jobs"]["jp_abc12345"]["demo"] is False
    assert index["jobs"]["jp-2026-001"]["demo"] is True
    assert index["jobs"]["jp_abc12345"]["jd_chars"] == len("做一个 AI 系统")


def test_person_docs_and_nonfact_constants(root: Path):
    index = _build(root)
    person_ids = {p["material_id"] for p in index["person_docs"]}
    assert "mat_723e3040" in person_ids
    assert "mat_331bc1bc" in person_ids
    assert "mat_7dad703c" in person_ids
    assert "mat_aaaa1111" not in person_ids
    doc = index["materials"]["mat_723e3040"]["documents"][0]
    assert doc["person_doc"] is True
    assert index["materials"]["mat_aaaa1111"]["documents"][0]["person_doc"] is False
    summary_docs = {d["label"].split("/")[-1]: d for d in index["materials"]["mat_7dad703c"]["documents"]}
    assert summary_docs["工作汇总-1.md"]["person_doc"] is True
    assert summary_docs["5 分钟速读卡.md"]["person_doc"] is False
    nonfact = {n["material_id"]: n["reason"] for n in index["nonfact_materials"]}
    assert "mat_quick_run_verify" in nonfact
    assert "事实" in nonfact["mat_quick_run_verify"]


def test_render_index_md_sections(root: Path):
    from tools.infra import knowledge_index
    index = _build(root)
    md = knowledge_index.render_index_md(index)
    assert "知识索引" in md
    assert "2026-10-17T00:00:00+00:00" in md
    assert "mat_aaaa1111" in md
    assert "3 档" in md or "：3" in md
    assert "mat_quick_run_verify" in md
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


def test_build_is_deterministic(root: Path):
    assert _build(root) == _build(root)
