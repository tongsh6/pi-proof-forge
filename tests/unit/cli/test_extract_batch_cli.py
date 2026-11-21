"""批量提炼 CLI 的落盘契约：空列表必须是合法 YAML，且卡保持待审核状态。"""
import json
from pathlib import Path

import yaml

from tools.cli.commands.extract_batch import _card_id, dump_card


def full_card() -> dict:
    return {
        "id": "ec_batch_demo",
        "title": "示例项目（工程档案规模）",
        "time_range": "",
        "context": "示例项目档案，共 3 篇文档。",
        "role_scope": "",
        "status": "draft",
        "created_at": "2026-11-09T00:00:00Z",
        "updated_at": "2026-11-09T00:00:00Z",
        "actions": ["项目目录共 3 篇文档，其中 方案 2 篇、需求 1 篇"],
        "results": ["3 篇业务文档沉淀（方案/需求/验收/发布记录可追溯）"],
        "stack": [],
        "artifacts": [],
        "tags": ["批量规模卡", "待提炼"],
        "raw_source": "materials:mat_demo",
        "source_material_ids": ["mat_demo"],
        "source_documents_json": json.dumps(
            [{"document_id": "a" * 64, "sha256": "b" * 64, "label": "示例/00-需求.md", "material_id": "mat_demo"}],
            ensure_ascii=False,
        ),
        "review_decision": "pending",
        "candidate_pool_eligible": "false",
        "missing_items": "本人职责、任职时间与量化成果待确认",
        "batch_scale_card": "true",
    }


def test_dump_card_with_empty_lists_is_valid_yaml(tmp_path: Path):
    text = dump_card(full_card())
    parsed = yaml.safe_load(text)

    assert parsed["stack"] == [] and parsed["artifacts"] == []
    assert parsed["status"] == "draft"
    assert parsed["candidate_pool_eligible"] == "false"
    assert parsed["batch_scale_card"] == "true"
    references = json.loads(parsed["source_documents_json"])
    assert references[0]["document_id"] == "a" * 64


def test_dump_card_roundtrips_non_empty_lists():
    card = full_card()
    card["stack"] = ["Java", "Redis"]
    card["artifacts"] = ["mat_demo"]

    parsed = yaml.safe_load(dump_card(card))

    assert parsed["stack"] == ["Java", "Redis"]
    assert parsed["artifacts"] == ["mat_demo"]


def test_card_id_is_stable_and_namespaced():
    first = _card_id("小程序站内消息")
    second = _card_id("小程序站内消息")

    assert first == second
    assert first.startswith("ec_batch_")
    assert len(first) == len("ec_batch_") + 8
    assert first != _card_id("活动报名聚合")


def test_dump_card_defaults_missing_source_binding_to_empty():
    card = full_card()
    card.pop("source_documents_json")
    parsed = yaml.safe_load(dump_card(card))
    assert parsed["source_documents_json"] == ""
