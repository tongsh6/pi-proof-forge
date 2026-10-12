"""证据卡自动关联工作经历：公司别名、三类信号、冲突不决定。"""
from tools.infra.career_profile import company_aliases, suggest_evidence_links


def test_company_aliases_strip_city_prefix_suffix_and_keep_bracket_short_names():
    assert company_aliases("一里智辉（EC+）") == ["一里智辉（EC+）", "一里智辉", "EC+"]
    assert company_aliases("众安保险") == ["众安保险", "众安"]
    assert company_aliases("九恒星（上海）金融信息服务有限公司") == ["九恒星（上海）金融信息服务有限公司", "九恒星"]
    assert company_aliases("上海伊尔普信息技术有限公司") == ["上海伊尔普信息技术有限公司", "伊尔普"]
    assert company_aliases("") == []


CAREER = {"work": [
    {"id": "w_ec", "company": "一里智辉（EC+）", "start": "2021-03", "end": "", "current": True, "evidence_ids": ["ec_old"]},
    {"id": "w_za", "company": "众安保险", "start": "2018-10", "end": "2021-03", "current": False, "evidence_ids": []},
]}
LABELS = {"mat_ec": "EC+ 工作汇总与模块架构切片", "mat_za": "众安 2018-2021 业务系统", "mat_bird": "始祖鸟", "mat_misc": "消息平台改造"}


def test_links_by_label_linked_material_and_time_and_flags_conflicts():
    cards = [
        {"id": "ec_old", "title": "旧卡", "time_range": "", "source_material_ids": ["mat_bird"]},
        {"id": "ec_a", "title": "标签命中", "time_range": "", "source_material_ids": ["mat_ec"]},
        {"id": "ec_b", "title": "同材料继承", "time_range": "", "source_material_ids": ["mat_bird"]},
        {"id": "ec_c", "title": "只有时间", "time_range": "2019-04 ~ 2019-06", "source_material_ids": ["mat_misc"]},
        {"id": "ec_d", "title": "无信号", "time_range": "", "source_material_ids": ["mat_misc"]},
        {"id": "ec_e", "title": "标签与时间冲突", "time_range": "2019-04 ~ 2019-06", "source_material_ids": ["mat_ec"]},
        {"id": "ec_f", "title": "标签与时间一致", "time_range": "2024-01 ~ 2024-03", "source_material_ids": ["mat_ec"]},
    ]
    result = suggest_evidence_links(CAREER, cards, LABELS)
    by_id = {item["evidence_id"]: item for item in result["suggestions"]}
    assert result["already_linked"] == 1
    assert by_id["ec_a"]["work_id"] == "w_ec" and by_id["ec_a"]["basis"] == ["material_label"]
    assert by_id["ec_b"]["work_id"] == "w_ec" and by_id["ec_b"]["basis"] == ["linked_material"]
    assert by_id["ec_c"]["work_id"] == "w_za" and by_id["ec_c"]["basis"] == ["time_range"]
    assert by_id["ec_f"]["work_id"] == "w_ec" and by_id["ec_f"]["basis"] == ["material_label", "time_range"]
    unresolved = {item["evidence_id"]: item for item in result["unresolved"]}
    assert unresolved["ec_d"]["reason"] == "no_signal"
    assert unresolved["ec_e"]["reason"] == "ambiguous" and unresolved["ec_e"]["candidates"] == ["w_ec", "w_za"]
    assert "ec_old" not in by_id and "ec_old" not in unresolved
