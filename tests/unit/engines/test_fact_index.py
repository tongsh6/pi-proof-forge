"""事实索引契约：证据卡与已确认职业档案展开为可追溯的最小事实单元。

生成阶段只选择、排序、分组事实，不改写、不新增；事实编号沿用语义评审的
`{source_id}:{field}:{index}` 口径，保证评估引用可直接映射回事实。
"""
from tools.engines.generation.fact_index import Fact, FactIndex, build_fact_index


def card(**over):
    base = {
        "id": "ec_a",
        "title": "门店预约与排队系统",
        "raw_source": "materials:mat_x",
        "context": "门店高峰预约排队场景",
        "role_scope": "主导方案设计与核心开发",
        "time_range": "2024-01 ~ 2024-06",
        "actions": ["引入 8 个分布式锁键控制并发", "设计 16+ 参数后台查询"],
        "results": ["核心查询从 2–3 秒降至 300–400 毫秒"],
        "stack": ["Java", "Redis"],
        "artifacts": ["mat_x"],
        "tags": ["预约"],
    }
    base.update(over)
    return base


def career(**over):
    base = {
        "summary": "后端与平台建设。",
        "work": [
            {
                "id": "w1",
                "company": "公司A",
                "title": "Tech Lead",
                "start": "2021-03",
                "end": "",
                "current": True,
                "scope": "门店数字化",
                "contributions": ["负责预约平台架构"],
                "evidence_ids": ["ec_a"],
            }
        ],
        "education_visibility": "show",
        "education": [
            {"id": "e1", "school": "某大学", "major": "软件工程", "degree": "本科", "start": "2018-09", "end": "2022-06"}
        ],
        "skills": [{"id": "s1", "category": "后端", "description": "Java 服务", "evidence_ids": ["ec_a"]}],
        "extras": [],
    }
    base.update(over)
    return base


def semantic(**over):
    report = {
        "facts": {},
        "requirements": [
            {"requirement_id": "r1", "text": "高并发系统经验"},
            {"requirement_id": "r2", "text": "平台化建设经验"},
        ],
        "assessments": [
            {
                "requirement_id": "r1",
                "status": "supported",
                "citations": [{"fact_id": "ec_a:actions:0", "quote": "8 个分布式锁键"}],
            }
        ],
        "selected_card_ids": ["ec_a"],
    }
    report.update(over)
    return report


def test_expands_card_fields_in_stable_order():
    index = build_fact_index([card()], career())

    assert isinstance(index, FactIndex)
    ids = [fact.fact_id for fact in index.facts]
    # 卡片顺序 × 字段顺序 × 条目序号稳定可复算
    assert ids[:5] == ["ec_a:title:0", "ec_a:context:0", "ec_a:role_scope:0", "ec_a:time_range:0", "ec_a:actions:0"]
    assert "ec_a:actions:1" in ids and "ec_a:results:0" in ids and "ec_a:stack:0" in ids
    assert index.get("ec_a:actions:0") == Fact(
        fact_id="ec_a:actions:0",
        source_id="ec_a",
        field="actions",
        text="引入 8 个分布式锁键控制并发",
        kind="evidence",
        work_id="w1",
        time_range="2024-01 ~ 2024-06",
        has_quant=True,  # "8 个" 属既有量化口径的规模单位
        role_strength="lead",
        requirement_ids=(),
        support_weight=0,
        card_title="门店预约与排队系统",
        order=4,
    )
    evidence_ids = [fact.fact_id for fact in index.facts if fact.kind == "evidence"]
    assert [fact.fact_id for fact in index.by_card("ec_a")] == evidence_ids


def test_skips_placeholder_values():
    broken = card(context="", role_scope="[]", actions=["", "null", "None", "{}"], results=["有效结果 3 条"])
    index = build_fact_index([broken], career())

    texts = [fact.text for fact in index.facts]
    assert "" not in texts and "[]" not in texts and "null" not in texts and "None" not in texts and "{}" not in texts
    assert "有效结果 3 条" in texts


def test_links_facts_to_work_by_evidence_ids():
    index = build_fact_index([card(), card(id="ec_b", title="无关项目")], career())

    assert index.by_work("w1")[0].source_id == "ec_a"
    assert all(fact.work_id == "" for fact in index.by_card("ec_b"))


def test_marks_quant_metrics_and_role_strength():
    index = build_fact_index([card()], career())

    assert index.get("ec_a:results:0").has_quant is True
    # "8 个" 命中既有规模单位口径；role_scope 无数字，不含量化
    assert index.get("ec_a:actions:0").has_quant is True
    assert index.get("ec_a:role_scope:0").has_quant is False
    assert index.get("ec_a:role_scope:0").role_strength == "lead"
    assert build_fact_index([card(role_scope="独立完成总体架构")], career()).get(
        "ec_a:role_scope:0"
    ).role_strength == "owner"
    assert build_fact_index([card(role_scope="参与联调")], career()).get(
        "ec_a:role_scope:0"
    ).role_strength == "participate"


def test_maps_semantic_requirements_and_support_weight():
    index = build_fact_index([card()], career(), semantic())

    action = index.get("ec_a:actions:0")
    assert action.requirement_ids == ("r1",)
    assert action.support_weight == 2
    assert index.get("ec_a:actions:1").requirement_ids == ()


def test_ignores_unknown_or_profile_fact_ids_without_breaking_order():
    report = semantic(
        assessments=[
            {"requirement_id": "r1", "status": "supported", "citations": [{"fact_id": "ec_missing:actions:0"}]},
            {
                "requirement_id": "r2",
                "status": "partial",
                "citations": [{"fact_id": "personal_profile:career.work.w1.contributions:0"}],
            },
        ]
    )
    index = build_fact_index([card()], career(), report)

    assert index.get("ec_a:actions:0").requirement_ids == ()
    profile_fact = index.get("personal_profile:career.work.w1.contributions:0")
    assert profile_fact is not None
    assert profile_fact.kind == "profile"
    assert profile_fact.work_id == "w1"
    assert profile_fact.requirement_ids == ("r2",)
    assert profile_fact.support_weight == 1


def test_requires_explicit_card_ids_and_rejects_duplicates():
    index = build_fact_index([card(), card()], career())
    ids = [fact.fact_id for fact in index.facts]
    assert len(ids) == len(set(ids))
