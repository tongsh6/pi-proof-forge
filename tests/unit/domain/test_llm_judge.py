"""B1：受控 JSON 判项通道的输入、校验与 fail-closed 行为。"""
from __future__ import annotations

import json

from tools.engines.evaluation import llm_judge


BULLETS = [
    {"number": 1, "section": "核心能力", "entry": "", "first_screen": True, "text": "架构：平台治理"},
    {"number": 2, "section": "项目经历", "entry": "统一平台建设", "first_screen": False, "text": "完成平台抽象"},
    {"number": 3, "section": "项目经历", "entry": "统一平台建设", "first_screen": False, "text": "负责查询性能治理"},
]
CARDS = {
    "ec_00000001": {
        "title": "统一平台建设",
        "time_range": "2022-03 ~ 2023-09",
        "role_scope": "平台负责人",
        "context": "多品牌微服务散落",
        "results": ["查询耗时从 2 秒降至 300 毫秒"],
        "stack": ["Java"],
    }
}
JD_ITEMS = [
    {"id": "d1", "kind": "responsibility", "text": "负责核心平台交付"},
    {"id": "r1", "kind": "must_have", "text": "熟悉 Java"},
]


def test_prompt_contains_bullets_cards_and_jd_items():
    prompt = llm_judge.build_judge_prompt(bullets=BULLETS, cards=CARDS, jd_items=JD_ITEMS)
    assert "r1_4" in prompt and "r4_1" in prompt
    assert "完成平台抽象" in prompt and "ec_00000001" in prompt and "负责核心平台交付" in prompt
    assert "citations" in prompt


def valid_payload():
    return {
        "r1_4": [{"bullet": 3, "supported": False, "citations": ["ec_00000001"], "reason": "卡中仅写负责查询治理"}],
        "r2_1": [
            {"jd_item_id": "d1", "status": "weak", "bullet_ref": "bullet#2", "citations": ["ec_00000001"], "reason": "仅部分支撑"},
            {"jd_item_id": "r1", "status": "supported", "bullet_ref": "bullet#1", "citations": ["bullet#1"], "reason": "技能区出现"},
        ],
        "r3_1": [
            {"bullet": 2, "scene": True, "action": True, "result": False, "citations": ["ec_00000001"], "reason": "缺结果"},
            {"bullet": 3, "scene": True, "action": True, "result": True, "citations": ["ec_00000001"], "reason": ""},
        ],
        "r3_5": {"summary_lines": 2, "role_scale_match": True, "generic_adjectives": [], "citations": ["bullet#1"], "reason": ""},
        "r4_1": [
            {"bullet": 2, "jd_item_id": "d1", "exceeds": ["scale", "difficulty"], "level": "L2",
             "citations": ["ec_00000001"], "reason": "规模超出 JD 字面"}
        ],
    }


def test_parse_valid_payload_marks_all_sections_covered():
    judgments = llm_judge.parse_judgments(
        "```json\n" + json.dumps(valid_payload(), ensure_ascii=False) + "\n```",
        bullets=BULLETS,
        jd_items=JD_ITEMS,
        cards=CARDS,
    )
    assert judgments is not None
    assert set(judgments["judged_sections"]) == {"r1_4", "r2_1", "r3_1", "r3_5", "r4_1"}
    assert judgments["r4_1"][0]["highlight_id"] if "highlight_id" in judgments["r4_1"][0] else True
    assert llm_judge.highlight_id(judgments["r4_1"][0]) == "hl_b2_d1"


def test_items_without_citations_are_discarded_and_incomplete_coverage_stays_pending():
    payload = valid_payload()
    payload["r2_1"] = [payload["r2_1"][0]]  # 缺少 r1 覆盖
    payload["r1_4"][0].pop("citations")
    payload["r3_1"][0]["citations"] = []
    payload["r4_1"][0]["citations"] = []
    judgments = llm_judge.parse_judgments(
        json.dumps(payload, ensure_ascii=False), bullets=BULLETS, jd_items=JD_ITEMS, cards=CARDS
    )
    assert judgments is not None
    assert "r2_1" not in judgments["judged_sections"]  # 未逐条覆盖 → 仍需 pending
    assert judgments["r1_4"] == [] and judgments["r3_1"] == [{"bullet": 3, "scene": True, "action": True, "result": True, "citations": ["ec_00000001"], "reason": ""}]
    assert judgments["r4_1"] == []
    assert judgments["rejected_items"] >= 3


def test_invalid_json_and_unknown_references_return_none_or_empty():
    assert llm_judge.parse_judgments("not json", bullets=BULLETS, jd_items=JD_ITEMS, cards=CARDS) is None
    payload = valid_payload()
    payload["r2_1"][0]["jd_item_id"] = "unknown"
    payload["r4_1"][0]["level"] = "L3"
    payload["r3_5"]["citations"] = []
    judgments = llm_judge.parse_judgments(
        json.dumps(payload, ensure_ascii=False), bullets=BULLETS, jd_items=JD_ITEMS, cards=CARDS
    )
    assert judgments is not None
    assert "r2_1" not in judgments["judged_sections"]
    assert judgments["r4_1"] == []
    assert "r3_5" not in judgments["judged_sections"]
