"""批量提炼契约：聚类、代表文档、规则规模卡与 LLM 结构校验。"""
import json
from pathlib import Path

import pytest

from tools.engines.evidence.batch_extract import (
    build_extraction_prompt,
    build_scale_card,
    cluster_by_project,
    collect_documents,
    parse_extraction_response,
    select_representative,
    verify_card_against_sources,
)

MATERIAL = """# Source: 门店预约/00-需求.md
门店预约需要支持导购邀约、会员主动预约与 Walk-in 排队三种方式。
# Source: 门店预约/02-技术方案.md
采用 3 个策略实现动态注册，覆盖预约全生命周期。
核心查询耗时从 2-3 秒降至 300-400 毫秒。
# Source: 门店预约/05-验收.md
验证成功、超限与失败分支。
# Source: 门店租赁/00-需求.md
门店租赁需要支持现场与邮寄两条归还路径。
# Source: 门店租赁/02-技术方案.md
使用 Redis 记录核销状态。
"""


def material_file(tmp_path: Path) -> Path:
    path = tmp_path / "mat_demo.md"
    path.write_text(MATERIAL, encoding="utf-8")
    return path


def test_collect_documents_keeps_document_identity(tmp_path):
    docs = collect_documents(material_file(tmp_path))

    assert [doc.label for doc in docs] == [
        "门店预约/00-需求.md",
        "门店预约/02-技术方案.md",
        "门店预约/05-验收.md",
        "门店租赁/00-需求.md",
        "门店租赁/02-技术方案.md",
    ]
    assert all(len(doc.document_id) == 64 and len(doc.sha256) == 64 for doc in docs)


def test_cluster_by_project_groups_first_path_segment(tmp_path):
    clusters = cluster_by_project(collect_documents(material_file(tmp_path)))

    assert [cluster.key for cluster in clusters] == ["门店预约", "门店租赁"]
    assert [cluster.document_count for cluster in clusters] == [3, 2]


def test_cluster_min_documents_filters_fragments(tmp_path):
    clusters = cluster_by_project(collect_documents(material_file(tmp_path)), min_documents=3)

    assert [cluster.key for cluster in clusters] == ["门店预约"]


def test_select_representative_prefers_requirement_and_solution_docs(tmp_path):
    clusters = {cluster.key: cluster for cluster in cluster_by_project(collect_documents(material_file(tmp_path)))}
    selected = select_representative(clusters["门店预约"], max_docs=2)

    labels = [doc.label for doc in selected]
    assert "门店预约/00-需求.md" in labels
    assert "门店预约/02-技术方案.md" in labels
    assert "门店预约/05-验收.md" not in labels


def test_build_scale_card_binds_sources_and_stays_out_of_pool(tmp_path):
    clusters = {cluster.key: cluster for cluster in cluster_by_project(collect_documents(material_file(tmp_path)))}
    cluster = clusters["门店预约"]
    selected = select_representative(cluster)
    card = build_scale_card(
        cluster,
        selected,
        material_id="mat_demo",
        card_id="ec_batch_demo",
        raw_source="materials:mat_demo",
        now="2026-11-09T00:00:00Z",
    )

    assert card["status"] == "draft"
    assert card["candidate_pool_eligible"] == "false"
    assert card["batch_scale_card"] == "true"
    assert "3 篇文档" in card["actions"][0]
    refs = json.loads(card["source_documents_json"])
    assert len(refs) == len(selected)
    assert all(ref["material_id"] == "mat_demo" and len(ref["document_id"]) == 64 for ref in refs)
    assert card["missing_items"]


def test_build_extraction_prompt_states_verbatim_requirement(tmp_path):
    clusters = {cluster.key: cluster for cluster in cluster_by_project(collect_documents(material_file(tmp_path)))}
    cluster = clusters["门店预约"]
    prompt = build_extraction_prompt(cluster, select_representative(cluster))

    assert "逐字引用原文" in prompt
    assert "门店预约" in prompt
    assert "只输出 JSON 数组" in prompt


def test_parse_extraction_response_accepts_valid_and_rejects_invalid():
    valid = json.dumps([{"title": "门店预约平台", "actions": ["采用 3 个策略"], "results": ["查询降至 300 毫秒"]}])
    cards = parse_extraction_response(valid)
    assert cards[0]["title"] == "门店预约平台"

    fenced = "```json\n" + valid + "\n```"
    assert parse_extraction_response(fenced)[0]["title"] == "门店预约平台"

    for bad in ("not json", "[]", json.dumps({"title": ""}), json.dumps([{"title": "x"}])):
        with pytest.raises(ValueError):
            parse_extraction_response(bad)


def test_verify_card_against_sources_flags_fabrication():
    card = {"actions": ["采用 3 个策略实现动态注册"], "results": ["降至 300-400 毫秒", "凭空捏造的 10 倍提升"]}
    sources = "采用 3 个策略实现动态注册，覆盖预约全生命周期。核心查询耗时从 2-3 秒降至 300-400 毫秒。"

    missing = verify_card_against_sources(card, sources)

    assert missing == ["凭空捏造的 10 倍提升"]


def test_infer_period_uses_real_document_dates(tmp_path):
    from tools.engines.evidence.batch_extract import infer_period

    path = tmp_path / "mat_dates.md"
    path.write_text(
        "# Source: 项目A/20260410-需求.md\n背景说明。\n"
        "# Source: 项目A/20260815-技术方案.md\n方案说明。\n",
        encoding="utf-8",
    )
    docs = collect_documents(path)

    assert infer_period(docs) == "2026-04 ~ 2026-08"


def test_infer_period_ignores_out_of_range_and_future_dates(tmp_path):
    from tools.engines.evidence.batch_extract import infer_period

    path = tmp_path / "mat_bad.md"
    path.write_text(
        "# Source: 项目B/19990101-旧文档.md\n历史资料。\n"
        "# Source: 项目B/29990101-未来计划.md\n计划。\n"
        "# Source: 项目B/无日期文档.md\n内容。\n",
        encoding="utf-8",
    )
    docs = collect_documents(path)

    assert infer_period(docs) == ""


def test_infer_period_returns_single_month_when_all_dates_match(tmp_path):
    from tools.engines.evidence.batch_extract import infer_period

    path = tmp_path / "mat_same.md"
    path.write_text(
        "# Source: 项目C/2025-07-01-需求.md\n需求。\n# Source: 项目C/2025-07-20-验收.md\n验收。\n",
        encoding="utf-8",
    )
    docs = collect_documents(path)

    assert infer_period(docs) == "2025-07"


def test_normalize_period_to_month_precision():
    from tools.engines.evidence.batch_extract import normalize_period

    assert normalize_period("2025-12-18") == "2025-12"
    assert normalize_period("2025-12-18 ~ 2026-01-05") == "2025-12 ~ 2026-01"
    assert normalize_period("2026-03 ~ 2026-11") == "2026-03 ~ 2026-11"
    assert normalize_period("2025年3月 至 2025年9月") == "2025-03 ~ 2025-09"
    assert normalize_period("") == ""
    assert normalize_period("某段时间") == ""


def test_split_planned_results_separates_unverified_claims():
    from tools.engines.evidence.batch_extract import split_planned_results

    verified, planned = split_planned_results(
        ["核心查询 P95 降至 32ms", "预计提升 50-80% 查询速度", "计划支持零代码发版"]
    )

    assert verified == ["核心查询 P95 降至 32ms"]
    assert planned == ["预计提升 50-80% 查询速度", "计划支持零代码发版"]


def test_project_outline_summarizes_directory_structure(tmp_path):
    from tools.engines.evidence.batch_extract import project_outline

    path = tmp_path / "mat_outline.md"
    path.write_text(
        "# Source: 项目A/features/F1/00-需求.md\n需求。\n"
        "# Source: 项目A/features/F1/02-技术方案.md\n方案。\n"
        "# Source: 项目A/features/F2/00-需求.md\n需求。\n"
        "# Source: 项目A/experiences/X.md\n经验。\n",
        encoding="utf-8",
    )
    docs = collect_documents(path)
    cluster = cluster_by_project(docs)[0]

    outline = project_outline(cluster)

    assert "features/F1（2 篇）" in outline
    assert "features/F2（1 篇）" in outline
    assert "experiences（1 篇）" in outline


def test_extraction_prompt_includes_project_outline_and_project_level_requirement(tmp_path):
    from tools.engines.evidence.batch_extract import project_outline

    path = tmp_path / "mat_prompt.md"
    path.write_text(
        "# Source: 项目B/features/F1/00-需求.md\n需求。\n# Source: 项目B/features/F2/00-需求.md\n需求。\n",
        encoding="utf-8",
    )
    docs = collect_documents(path)
    cluster = cluster_by_project(docs)[0]
    prompt = build_extraction_prompt(cluster, select_representative(cluster))

    assert "项目目录结构" in prompt
    assert "先概括该项目整体做了什么" in prompt
    assert project_outline(cluster).splitlines()[0] in prompt


def test_classify_card_category_separates_activity_from_project():
    from tools.engines.evidence.batch_extract import classify_card_category

    assert classify_card_category("Java高级开发工程师招聘面试题库整理") == "activity"
    assert classify_card_category("示例保险公司新人入职培训与合规学习") == "activity"
    assert classify_card_category("组内技术分享体系构建与知识沉淀") == "activity"
    assert classify_card_category("示例集团账务平台与结算服务接口集成") == "project"
    assert classify_card_category("业务记录与审核系统功能优化及上线") == "project"
    assert classify_card_category("示例支付系统运维支持与问题排查") == "operation"


def test_exclude_clusters_drops_noise_cluster(tmp_path):
    from tools.engines.evidence.batch_extract import exclude_clusters

    path = tmp_path / "mat_noise.md"
    path.write_text(
        "# Source: assets/a.txt\n附件。\n# Source: assets/b.txt\n附件。\n"
        "# Source: 接口平台规划/01-方案.md\n方案。\n",
        encoding="utf-8",
    )
    clusters = cluster_by_project(collect_documents(path))

    kept = exclude_clusters(clusters, ["assets"])

    assert [cluster.key for cluster in kept] == ["接口平台规划"]
    assert len(exclude_clusters(clusters, [])) == len(clusters)


def test_cluster_skips_generic_container_segment(tmp_path):
    from tools.engines.evidence.batch_extract import cluster_by_project

    path = tmp_path / "mat_container.md"
    path.write_text(
        "# Source: 项目目录/品牌A/活动管理/5分钟速读卡.md\n内容。\n"
        "# Source: 项目目录/品牌A/活动管理/业务地图.md\n内容。\n"
        "# Source: 项目目录/品牌A/会员管理/5分钟速读卡.md\n内容。\n"
        "# Source: 小程序站内消息/features/x/00-需求.md\n内容。\n",
        encoding="utf-8",
    )
    clusters = cluster_by_project(collect_documents(path))

    keys = [cluster.key for cluster in clusters]
    assert "品牌A/活动管理" in keys
    assert "品牌A/会员管理" in keys
    assert "小程序站内消息" in keys


def test_pool_approval_reason_enforces_evidence_first_gate():
    from tools.engines.evidence.batch_extract import pool_approval_reason

    good = {"title": "项目", "results": ["查询降至 300ms"], "artifacts": ["mat_x"]}
    assert pool_approval_reason(good) == ""
    assert pool_approval_reason({**good, "title": ""}) == "title_missing"
    assert pool_approval_reason({**good, "results": []}) == "results_missing"
    assert pool_approval_reason({**good, "artifacts": []}) == "artifacts_missing"
    assert pool_approval_reason(good, source_verifiable=False) == "source_unverifiable"
