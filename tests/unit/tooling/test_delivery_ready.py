"""投递就绪检查的只读契约：合规卡统计、已投岗位识别、可投岗位筛选。"""
import json
from pathlib import Path

from tools.tooling import delivery_ready


def _card(path: Path, *, status: str, eligible: str, results: list[str]) -> None:
    lines = [
        'id: "ec_test"',
        'title: "测试卡"',
        f'status: "{status}"',
        f'candidate_pool_eligible: "{eligible}"',
        "results:",
        *[f'  - "{value}"' for value in results],
        "artifacts:",
        '  - "mat_x"',
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_pool_cards_counts_eligible_and_flags_missing_results(tmp_path: Path):
    cards = tmp_path / "evidence_cards"
    cards.mkdir()
    _card(cards / "ec_good.yaml", status="saved_eligible", eligible="true", results=["降至 300ms"])
    _card(cards / "ec_bad.yaml", status="saved_eligible", eligible="true", results=[])
    _card(cards / "ec_draft.yaml", status="draft", eligible="false", results=["x"])

    pool, empty = delivery_ready._pool_cards(tmp_path)

    assert pool == 2 and empty == 1


def test_delivered_profiles_matches_company_and_role(tmp_path: Path):
    log_dir = tmp_path / "outputs/submissions/liepin/native-x"
    log_dir.mkdir(parents=True)
    (log_dir / "submission_log.json").write_text(
        json.dumps(
            {"input_artifacts": {"company": "某上海专业技术服务公司", "position": "高级全栈工程师"}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    delivered = delivery_ready._delivered_profiles(tmp_path)

    assert "某上海专业技术服务公司|高级全栈工程师" in delivered


def test_deliverable_profiles_excludes_delivered_and_unreviewed(tmp_path: Path):
    profiles = tmp_path / "job_profiles"
    profiles.mkdir()
    (profiles / "jp_a.yaml").write_text(
        'status: "active"\nreview_decision: "approved"\njob_lead_id: "jl1"\n'
        'company: "公司A"\ntarget_role: "Tech Lead"\n',
        encoding="utf-8",
    )
    (profiles / "jp_b.yaml").write_text(
        'status: "active"\nreview_decision: "approved"\njob_lead_id: "jl2"\n'
        'company: "公司B"\ntarget_role: "已投岗位"\n',
        encoding="utf-8",
    )
    (profiles / "jp_c.yaml").write_text(
        'status: "active"\nreview_decision: "pending"\njob_lead_id: "jl3"\n'
        'company: "公司C"\ntarget_role: "未审核"\n',
        encoding="utf-8",
    )
    log_dir = tmp_path / "outputs/submissions/liepin/native-y"
    log_dir.mkdir(parents=True)
    (log_dir / "submission_log.json").write_text(
        json.dumps({"input_artifacts": {"company": "公司B", "position": "已投岗位"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    rows = delivery_ready._deliverable_profiles(tmp_path)

    assert [row["id"] for row in rows] == ["jp_a"]


def test_deliverable_profiles_classifies_headhunter_vs_official(tmp_path: Path):
    profiles = tmp_path / "job_profiles"
    profiles.mkdir()
    (profiles / "jp_hh.yaml").write_text(
        'status: "active"\nreview_decision: "approved"\njob_lead_id: "jl1"\n'
        'company: "猎头岗公司"\ntarget_role: "CTO"\n'
        'source_url: "https://www.liepin.com/a/79819443.shtml"\n',
        encoding="utf-8",
    )
    (profiles / "jp_off.yaml").write_text(
        'status: "active"\nreview_decision: "approved"\njob_lead_id: "jl2"\n'
        'company: "官方岗公司"\ntarget_role: "后端"\n'
        'source_url: "https://www.liepin.com/job/1986627771.shtml"\n',
        encoding="utf-8",
    )

    rows = {row["id"]: row for row in delivery_ready._deliverable_profiles(tmp_path)}

    # 猎聘 /a/ 是猎头岗（只有平台默认简历），/job/ 才可能绑定定制 PDF。
    assert rows["jp_hh"]["delivery_mode"] == "platform_default"
    assert rows["jp_off"]["delivery_mode"] == "generated_pdf"
