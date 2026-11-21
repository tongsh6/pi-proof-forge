"""事实级选材契约：先满足 JD 需求覆盖，再按价值与配额分配，不再按"卡"硬截断。"""
from tools.engines.generation.fact_index import build_fact_index
from tools.engines.generation.fact_selector import (
    DELIVERY_OWNER,
    TECHNICAL_DEPTH,
    SelectionBudget,
    SelectedFacts,
    select_facts,
)


def card(cid, title, time_range="2024-01 ~ 2024-06", actions=(), results=(), role_scope="主导方案设计"):
    return {
        "id": cid,
        "title": title,
        "raw_source": "materials:mat_x",
        "context": f"{title}的业务背景",
        "role_scope": role_scope,
        "time_range": time_range,
        "actions": list(actions),
        "results": list(results),
        "stack": ["Java"],
        "artifacts": ["mat_x"],
        "tags": [],
    }


def career(cards_by_work):
    work = [
        {
            "id": work_id,
            "company": f"公司{work_id}",
            "title": "Tech Lead",
            "start": "2021-03",
            "end": "",
            "current": True,
            "scope": f"{work_id} 的业务范围",
            "contributions": [f"{work_id} 的概括职责"],
            "evidence_ids": list(card_ids),
        }
        for work_id, card_ids in cards_by_work.items()
    ]
    return {
        "summary": "后端与平台建设。",
        "work": work,
        "education_visibility": "omit",
        "education": [],
        "skills": [],
        "extras": [],
    }


def semantic(citations):
    """citations: [(requirement_id, status, fact_id), ...]"""
    return {
        "facts": {},
        "requirements": [{"requirement_id": rid} for rid, _status, _fid in citations],
        "assessments": [
            {"requirement_id": rid, "status": status, "citations": [{"fact_id": fid}]}
            for rid, status, fid in citations
        ],
    }


def test_prefers_requirement_cited_facts_over_mere_keyword_density():
    rich = card(
        "ec_rich",
        "关键词很多的普通项目",
        actions=["使用 Java MySQL Redis Spring Boot 开发系统"],
        results=["系统上线"],
    )
    cited = card(
        "ec_cited",
        "MongoDB 存储改造与容量治理",
        actions=["将核心存储从 MySQL/Redis 迁移至 MongoDB"],
        results=["五类查询 P95 不超过 32ms"],
    )
    index = build_fact_index(
        [rich, cited],
        career({"w1": ["ec_rich", "ec_cited"]}),
        semantic([("r1", "supported", "ec_cited:results:0")]),
    )
    chosen = select_facts(index, budget=SelectionBudget(max_total_facts=12, min_project_facts=1))

    assert "ec_cited:results:0" in chosen.projects["ec_cited"]
    assert len(chosen.projects["ec_cited"]) >= 1


def test_each_work_block_keeps_minimum_facts():
    index = build_fact_index(
        [
            card("ec_a", "项目 A", actions=["动作 A1", "动作 A2"], results=["结果 A1"]),
            card("ec_b", "项目 B", actions=["动作 B1"], results=["结果 B1"]),
        ],
        career({"w1": ["ec_a"], "w2": ["ec_b"]}),
    )
    chosen = select_facts(index, budget=SelectionBudget(min_work_facts=2, max_total_facts=40))

    assert len(chosen.work["w1"]) >= 2
    assert len(chosen.work["w2"]) >= 2  # 不足时用 archive/profile 事实补齐
    assert all(fid.startswith(("ec_a", "ec_b", "personal_profile")) for ids in chosen.work.values() for fid in ids)


def test_project_fact_quota_and_project_cap():
    cards = [
        card(f"ec_{i}", f"项目{i}", actions=[f"动作{i}-1", f"动作{i}-2", f"动作{i}-3"], results=[f"结果{i}-1"])
        for i in range(6)
    ]
    index = build_fact_index(cards, career({"w1": [c["id"] for c in cards]}))
    chosen = select_facts(
        index,
        budget=SelectionBudget(min_project_facts=2, max_project_facts=3, max_total_facts=100),
        max_projects=4,
    )

    assert 1 <= len(chosen.projects) <= 4
    for fact_ids in chosen.projects.values():
        assert 2 <= len(fact_ids) <= 3


def test_total_budget_is_respected():
    cards = [
        card(f"ec_{i}", f"项目{i}", actions=[f"动作{i}-{j}" for j in range(5)], results=[f"结果{i}-{j}" for j in range(3)])
        for i in range(5)
    ]
    index = build_fact_index(cards, career({"w1": [c["id"] for c in cards]}))
    chosen = select_facts(index, budget=SelectionBudget(max_total_facts=10))

    assert 0 < chosen.total <= 10


def test_variants_select_different_fact_sets():
    cards = [
        card(
            "ec_tech",
            "架构与性能治理",
            actions=["设计微服务分层与领域事件机制", "重构查询链路并建立索引边界"],
            results=["核心查询从 2–3 秒降至 300–400 毫秒"],
        ),
        card(
            "ec_delivery",
            "交付治理与团队协作",
            actions=["带领 5–8 人团队按品牌线拆解交付", "建立 Feature 化交付机制覆盖 57 个 Feature"],
            results=["5–8 人团队服务 6+ 品牌持续迭代"],
        ),
    ]
    index = build_fact_index(cards, career({"w1": ["ec_tech", "ec_delivery"]}))

    technical = select_facts(index, weights=TECHNICAL_DEPTH, budget=SelectionBudget(max_total_facts=6))
    delivery = select_facts(index, weights=DELIVERY_OWNER, budget=SelectionBudget(max_total_facts=6))

    assert set(technical.projects) != set(delivery.projects) or technical.work != delivery.work


def test_records_excluded_facts_with_reason():
    index = build_fact_index(
        [card("ec_a", "项目 A", actions=["动作 1", "动作 2"], results=["结果 1"])],
        career({"w1": ["ec_a"]}),
    )
    chosen = select_facts(index, budget=SelectionBudget(max_total_facts=3))

    assert isinstance(chosen, SelectedFacts)
    assert chosen.excluded
    assert all(reason for reason in chosen.excluded.values())


def test_empty_index_returns_empty_selection():
    chosen = select_facts(build_fact_index([], {}))
    assert chosen.total == 0 and chosen.projects == {} and chosen.work == {}


def test_task_list_fragments_are_penalized_below_real_duties():
    from tools.engines.generation.fact_selector import task_like_penalty

    assert task_like_penalty("封装GetInfoTypesAction查询参数") >= 2.0
    assert task_like_penalty("检查SaveInfoTypeAction事务和异常处理") >= 2.0
    assert task_like_penalty("因原有添加逻辑一致，前端统一使用接口") > 0
    assert task_like_penalty("逐步形成了一套模板代码") > 0
    assert task_like_penalty("带领 5–8 人跨职能团队，参与或负责 15+ 个系统从 0 到 1") == 0
    assert task_like_penalty("实施稳定性工程，包括幂等去重与分布式锁") == 0


def test_task_like_facts_lose_to_high_value_facts_under_budget():
    good = card(
        "ec_good",
        "核心平台建设",
        actions=["设计跨品牌会员中台并统一领域模型", "主导性能治理与容量验证"],
        results=["核心查询从 2–3 秒降至 300–400 毫秒", "支撑 6 个品牌持续迭代"],
    )
    bad = card(
        "ec_bad",
        "零散任务记录",
        actions=["封装GetInfoTypesAction查询参数", "检查SaveInfoTypeAction事务和异常处理"],
        results=["逐步形成了一套模板代码"],
    )
    index = build_fact_index([good, bad], career({"w1": ["ec_good", "ec_bad"]}))
    chosen = select_facts(index, budget=SelectionBudget(max_total_facts=6, min_work_facts=2, min_project_facts=2))

    selected_ids = {fid for ids in chosen.projects.values() for fid in ids}
    assert any(fid.startswith("ec_good:") for fid in selected_ids)
