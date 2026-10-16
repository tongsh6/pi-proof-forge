"""kb CLI：知识索引的构建与查询命令（面向 AI 代理的确定性接口）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import kb
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


def make_root(tmp_path: Path) -> Path:
    materials = tmp_path / "materials"
    materials.mkdir()
    (materials / "mat_aaaa1111.txt").write_text(BUNDLE, encoding="utf-8")
    (materials / "mat_aaaa1111.meta.yaml").write_text(
        'material_id: "mat_aaaa1111"\nlabel: "客户A项目记录"\nkind: "raw_work_material_directory"\n'
        'filename: "mat_aaaa1111.txt"\n', encoding="utf-8")
    (materials / "mat_331bc1bc.md").write_text("# 个人职业与教育时间线\n\n九恒星 2015.06–2018.10。\n", encoding="utf-8")
    (materials / "mat_331bc1bc.meta.yaml").write_text(
        'material_id: "mat_331bc1bc"\nlabel: "已确认职业与教育时间线"\nkind: "raw_work_material"\n'
        'filename: "mat_331bc1bc.md"\n', encoding="utf-8")
    (materials / "mat_quick_run_verify.md").write_text(
        "# Quick Run verifier material\n时间：2025-06 ~ 2025-09\n", encoding="utf-8")
    (materials / "mat_quick_run_verify.meta.yaml").write_text(
        'material_id: "mat_quick_run_verify"\nlabel: "Quick Run verifier material"\nkind: "raw_work_material"\n'
        'filename: "mat_quick_run_verify.md"\n', encoding="utf-8")

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
        'status: "saved_eligible"\n'
        'candidate_pool_eligible: "true"\n'
        f'source_documents_json: {json.dumps(json.dumps(refs, ensure_ascii=False))}\n'
        'source_material_ids:\n'
        '  - "mat_aaaa1111"\n',
        encoding="utf-8")
    (cards / "ec-2026-001.yaml").write_text(
        'id: "ec-2026-001"\ntitle: "示例卡"\ntime_range: "2026-01 ~ 2026-02"\nrole_scope: "示例职责"\n',
        encoding="utf-8")

    career = {"work": [{"id": "work_ecplus", "company": "一里智辉（EC+）", "start": "2021-03", "end": "",
                        "current": True, "evidence_ids": ["ec_1111aaaa"]}], "education": [], "skills": [], "extras": []}
    (tmp_path / "personal_profile.yaml").write_text(
        'name: "测试"\n'
        f'career_json: {json.dumps(json.dumps(career, ensure_ascii=False))}\n'
        'career_review_json: "{\\"revision\\": \\"rev1234567890\\"}"\n',
        encoding="utf-8")
    jobs = tmp_path / "job_profiles"
    jobs.mkdir()
    (jobs / "jp_abc12345.yaml").write_text('target_role: "AI 工程师"\ncompany: "某公司"\nstatus: "active"\n', encoding="utf-8")
    return tmp_path


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = make_root(tmp_path)
    assert kb.main(["build", "--root", str(r)]) == 0
    return r


def test_build_writes_index_files(root: Path):
    assert (root / "knowledge-index" / "index.json").is_file()
    assert (root / "knowledge-index" / "INDEX.md").is_file()


def test_queries_require_build(tmp_path: Path, capsys):
    bare = make_root(tmp_path)
    assert kb.main(["tree", "mat_aaaa1111", "--root", str(bare)]) == 1
    assert "build" in capsys.readouterr().out


def test_tree_and_prefix(root: Path, capsys):
    assert kb.main(["tree", "mat_aaaa1111", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "调研.md" in out and "验收.md" in out and "类型:验收" in out
    assert kb.main(["tree", "mat_aaaa1111", "02-CustomerA", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 3


def test_find_by_type_and_date(root: Path, capsys):
    assert kb.main(["find", "--type", "验收", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "05-全量验收.md" in out and "调研.md" not in out
    assert kb.main(["find", "--date-from", "2018-01", "--date-to", "2018-12", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "上线安排.md" in out
    assert "quick_run_verify" not in out


def test_grep_scopes(root: Path, capsys):
    assert kb.main(["grep", "改造调研", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "mat_aaaa1111" in out and "调研.md" in out
    assert kb.main(["grep", "客户A", "--scope", "cards", "--root", str(root)]) == 0
    assert "card:ec_1111aaaa" in capsys.readouterr().out
    assert kb.main(["grep", "工程师", "--scope", "jobs", "--root", str(root)]) == 0
    assert "job:jp_abc12345" in capsys.readouterr().out


def test_read_verifies_document(root: Path, capsys):
    docs = split_material_documents(BUNDLE, "mat_aaaa1111.txt")
    research = next(d for d in docs if d["label"] == "02-CustomerA/调研.md")
    assert kb.main(["read", "mat_aaaa1111", research["document_id"], "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "改造调研" in out and research["sha256"][:12] in out
    assert kb.main(["read", "mat_aaaa1111", "0" * 64, "--root", str(root)]) == 2
    assert "stale" in capsys.readouterr().out


def test_refs_outputs_relations(root: Path, capsys):
    assert kb.main(["refs", "ec_1111aaaa", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "cites" in out and "mat_aaaa1111" in out
    assert "work_ecplus" in out
    assert "time_range" in out


def test_cards_filters_and_demo(root: Path, capsys):
    assert kb.main(["cards", "--missing", "any", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "ec_1111aaaa" in out and "ec-2026-001" not in out
    assert kb.main(["cards", "--include-demo", "--root", str(root)]) == 0
    assert "ec-2026-001" in capsys.readouterr().out
    assert kb.main(["cards", "--has-date-hints", "--root", str(root)]) == 0
    assert "2017-02" in capsys.readouterr().out


def test_person_docs_lists_whitelist(root: Path, capsys):
    assert kb.main(["person-docs", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "mat_331bc1bc" in out
    assert "mat_quick_run_verify" not in out


def test_json_flag_returns_valid_json(root: Path, capsys):
    assert kb.main(["cards", "--missing", "any", "--json", "--root", str(root)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "ec_1111aaaa" in data


def test_verify_cli(root: Path, capsys):
    assert kb.main(["verify", "--root", str(root)]) == 0
    (root / "materials" / "mat_aaaa1111.txt").write_text(BUNDLE + "# Source: 02-CustomerA/新档.md\n新增。\n", encoding="utf-8")
    assert kb.main(["verify", "--root", str(root)]) == 2
    assert "mat_aaaa1111" in capsys.readouterr().out
