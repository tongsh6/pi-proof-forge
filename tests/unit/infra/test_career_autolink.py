"""证据卡自动关联工作经历：公司别名、三类信号、冲突不决定。"""
from tools.infra.career_profile import company_aliases, suggest_evidence_links


def test_company_aliases_strip_city_prefix_suffix_and_keep_bracket_short_names():
    assert company_aliases("云桥（CB）") == ["云桥（CB）", "云桥", "CB"]
    assert company_aliases("银杉保险") == ["银杉保险", "银杉"]
    assert company_aliases("远帆（上海）金融信息服务有限公司") == ["远帆（上海）金融信息服务有限公司", "远帆"]
    assert company_aliases("上海星河信息技术有限公司") == ["上海星河信息技术有限公司", "星河"]
    assert company_aliases("") == []


CAREER = {"work": [
    {"id": "w_current", "company": "云桥（CB）", "start": "2022-02", "end": "", "current": True, "evidence_ids": ["ec_old"]},
    {"id": "w_previous", "company": "银杉保险", "start": "2019-07", "end": "2022-02", "current": False, "evidence_ids": []},
]}
LABELS = {"mat_current": "CB 工作汇总与模块架构切片", "mat_previous": "银杉 2019-2022 业务系统", "mat_customer": "客户甲", "mat_misc": "消息平台改造"}


def test_links_by_label_linked_material_and_time_and_flags_conflicts():
    cards = [
        {"id": "ec_old", "title": "旧卡", "time_range": "", "source_material_ids": ["mat_customer"]},
        {"id": "ec_a", "title": "标签命中", "time_range": "", "source_material_ids": ["mat_current"]},
        {"id": "ec_b", "title": "同材料继承", "time_range": "", "source_material_ids": ["mat_customer"]},
        {"id": "ec_c", "title": "只有时间", "time_range": "2020-04 ~ 2020-06", "source_material_ids": ["mat_misc"]},
        {"id": "ec_d", "title": "无信号", "time_range": "", "source_material_ids": ["mat_misc"]},
        {"id": "ec_e", "title": "标签与时间冲突", "time_range": "2020-04 ~ 2020-06", "source_material_ids": ["mat_current"]},
        {"id": "ec_f", "title": "标签与时间一致", "time_range": "2024-01 ~ 2024-03", "source_material_ids": ["mat_current"]},
    ]
    result = suggest_evidence_links(CAREER, cards, LABELS)
    by_id = {item["evidence_id"]: item for item in result["suggestions"]}
    assert result["already_linked"] == 1
    assert by_id["ec_a"]["work_id"] == "w_current" and by_id["ec_a"]["basis"] == ["material_label"]
    assert by_id["ec_b"]["work_id"] == "w_current" and by_id["ec_b"]["basis"] == ["linked_material"]
    assert by_id["ec_c"]["work_id"] == "w_previous" and by_id["ec_c"]["basis"] == ["time_range"]
    assert by_id["ec_f"]["work_id"] == "w_current" and by_id["ec_f"]["basis"] == ["material_label", "time_range"]
    unresolved = {item["evidence_id"]: item for item in result["unresolved"]}
    assert unresolved["ec_d"]["reason"] == "no_signal"
    assert unresolved["ec_e"]["reason"] == "ambiguous" and unresolved["ec_e"]["candidates"] == ["w_current", "w_previous"]
    assert "ec_old" not in by_id and "ec_old" not in unresolved
