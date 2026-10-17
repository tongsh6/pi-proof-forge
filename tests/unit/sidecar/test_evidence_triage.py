"""补全分流：把缺字段卡标为“值得补 / 不参与展示 / 重复”，只记在旁路文件，不改卡、不改审核。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from tools.sidecar.handlers import evidence, materials
from tools.sidecar.server import process_request


def _card(evidence_id, title, **extra):
    lines = [f'id: "{evidence_id}"', f'title: "{title}"', 'status: "saved_incomplete"', 'candidate_pool_eligible: "false"']
    lines += [f'{k}: "{v}"' for k, v in extra.items()]
    return "\n".join(lines) + "\nresults:\n  - \"r\"\nartifacts:\n  - \"a\"\n"


def _call(method, **params):
    return process_request({"jsonrpc": "2.0", "id": "t", "method": method,
                            "params": {"meta": {"correlation_id": "t"}, **params}})


@pytest.fixture
def env():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        edir = root / "evidence_cards"
        edir.mkdir()
        (edir / "ec_a.yaml").write_text(_card("ec_a", "统一运动中心平台"), encoding="utf-8")
        (edir / "ec_b.yaml").write_text(_card("ec_b", "接口梳理小任务"), encoding="utf-8")
        (edir / "ec_c.yaml").write_text(_card("ec_c", "统一运动中心平台（副本）"), encoding="utf-8")
        with patch.object(evidence, "_EVIDENCE_DIR", edir), patch.object(materials, "_MATERIALS_DIR", root / "materials"), \
                patch.object(evidence, "_APP_DATA_DIR", root / "app-data"):
            yield root, edir


def _items():
    result = _call("evidence.reconcile")["result"]
    return result, {item["evidence_id"]: item for item in result["items"]}


def test_triage_is_recorded_beside_cards_without_touching_card_files(env):
    root, edir = env
    before = {p.name: p.read_bytes() for p in edir.iterdir()}
    assert "result" in _call("evidence.triage.set", evidence_id="ec_b", decision="not_for_display", note="早期小任务")
    assert "result" in _call("evidence.triage.set", evidence_id="ec_c", decision="duplicate", duplicate_of="ec_a")
    assert "result" in _call("evidence.triage.set", evidence_id="ec_a", decision="needs_fill")
    assert {p.name: p.read_bytes() for p in edir.iterdir()} == before, "分流不得改写卡片（不影响档案修订与审核）"
    stored = json.loads((root / "app-data/evidence_triage.json").read_text(encoding="utf-8"))
    assert stored["ec_b"]["decision"] == "not_for_display" and stored["ec_b"]["note"] == "早期小任务"
    assert len(stored["ec_b"]["card_sha256"]) == 64

    result, items = _items()
    assert items["ec_b"]["triage"]["decision"] == "not_for_display" and items["ec_b"]["triage"]["stale"] is False
    assert items["ec_c"]["triage"]["duplicate_of"] == "ec_a"
    assert items["ec_a"]["triage"]["decision"] == "needs_fill"
    assert result["summary"]["triaged_out"] == 2
    assert result["summary"]["needs_fill"] == 1
    assert result["summary"]["untriaged"] == 0
    # 被分流掉的卡不再计入缺字段缺口
    assert result["summary"]["missing_time_range"] == 1 and result["summary"]["missing_role_scope"] == 1


def test_card_change_makes_triage_stale_and_counts_again(env):
    root, edir = env
    _call("evidence.triage.set", evidence_id="ec_b", decision="not_for_display")
    (edir / "ec_b.yaml").write_text(_card("ec_b", "接口梳理小任务", context="补了背景"), encoding="utf-8")
    result, items = _items()
    assert items["ec_b"]["triage"]["stale"] is True, "卡片内容变化后旧判断失效，需重新分流"
    assert result["summary"]["triaged_out"] == 0 and result["summary"]["untriaged"] == 3


def test_clear_and_invalid_inputs(env):
    root, _ = env
    _call("evidence.triage.set", evidence_id="ec_b", decision="not_for_display")
    assert "result" in _call("evidence.triage.set", evidence_id="ec_b", decision="")
    _, items = _items()
    assert items["ec_b"]["triage"] is None
    for params in ({"evidence_id": "ec_b", "decision": "bogus"},
                   {"evidence_id": "ec_missing", "decision": "needs_fill"},
                   {"evidence_id": "ec_c", "decision": "duplicate"},
                   {"evidence_id": "ec_c", "decision": "duplicate", "duplicate_of": "ec_c"},
                   {"evidence_id": "ec_c", "decision": "duplicate", "duplicate_of": "ec_missing"},
                   {"evidence_id": "../x", "decision": "needs_fill"},
                   {"evidence_id": "ec_b", "decision": "needs_fill", "note": "x" * 501}):
        assert "error" in _call("evidence.triage.set", **params), params


def test_corrupt_triage_file_is_reported_not_silently_dropped(env):
    root, _ = env
    (root / "app-data").mkdir()
    (root / "app-data/evidence_triage.json").write_text("{bad", encoding="utf-8")
    assert "error" in _call("evidence.reconcile")
    assert "error" in _call("evidence.triage.set", evidence_id="ec_b", decision="needs_fill")
