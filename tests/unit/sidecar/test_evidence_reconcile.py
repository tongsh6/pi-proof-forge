"""材料对账：每张卡的结果能否逐字追溯到材料、缺哪些字段、有无重复、材料里有哪些日期线索。只读，不改卡。"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers import evidence, materials
from tools.sidecar.server import process_request


MATERIAL = (
    "# Source: 项目/会员中心/速读卡.md\n\n---\ncreated: '2024-06-03T10:00:00Z'\n---\n"
    "会员中心上线后日活从 1.2 万提升到 3.5 万。\n2024-09 完成 CRM 同步重试机制。\n\n"
    "# Source: 项目/租赁/方案.md\n\n租赁订单状态机覆盖登记、核销、归还与异常结束。\n"
)


def _write_material(root: Path) -> None:
    mdir = root / "materials"
    mdir.mkdir()
    (mdir / "mat_t1.txt").write_text(MATERIAL, encoding="utf-8")
    (mdir / "mat_t1.meta.yaml").write_text(
        'material_id: "mat_t1"\nlabel: "测试材料"\nkind: "raw_work_material_directory"\nfilename: "mat_t1.txt"\nextension: ".txt"\nuploaded_at: "2026-10-12T00:00:00Z"\n',
        encoding="utf-8",
    )


def _card(**fields: object) -> str:
    lines = []
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f'  - "{item}"' for item in value)
        else:
            lines.append(f'{key}: "{value}"')
    return "\n".join(lines) + "\n"


def _rpc(**params):
    response = process_request({"jsonrpc": "2.0", "id": "t", "method": "evidence.reconcile",
                                "params": {"meta": {"correlation_id": "t"}, **params}})
    assert "result" in response, response
    return response["result"]


def test_reconcile_reports_traceability_missing_fields_duplicates_and_date_hints():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_material(root)
        edir = root / "evidence_cards"
        edir.mkdir()
        (edir / "ec_ok.yaml").write_text(_card(
            id="ec_ok", title="会员中心核心能力建设", time_range="2024-06 ~ 2024-09", role_scope="Owner", status="saved_eligible",
            candidate_pool_eligible="true", results=["会员中心上线后日活从 1.2 万提升到 3.5 万。"], artifacts=["mat_t1"], source_material_ids=["mat_t1"]), encoding="utf-8")
        (edir / "ec_bad.yaml").write_text(_card(
            id="ec_bad", title="会员中心核心能力建设（改写）", status="saved_incomplete", candidate_pool_eligible="false",
            results=["日活提升近三倍。"], artifacts=["mat_t1"], source_material_ids=["mat_t1"]), encoding="utf-8")
        (edir / "ec-legacy.yaml").write_text(_card(
            id="ec-legacy", title="门店租赁订单状态机设计", time_range="2024-05 ~ 2024-07", role_scope="Owner",
            results=["租赁订单状态机覆盖登记、核销、归还与异常结束。"], artifacts=["方案.pdf"]), encoding="utf-8")
        with patch.object(evidence, "_EVIDENCE_DIR", edir), patch.object(materials, "_MATERIALS_DIR", root / "materials"):
            result = _rpc()
        by_id = {item["evidence_id"]: item for item in result["items"]}
        assert result["summary"]["total"] == 3
        assert result["summary"]["eligible"] == 1 and result["summary"]["incomplete"] == 1 and result["summary"]["legacy"] == 1

        ok = by_id["ec_ok"]
        assert ok["pool_status"] == "eligible" and ok["untraceable_results"] == [] and ok["missing_fields"] == []
        assert ok["traceable_results"] == 1

        bad = by_id["ec_bad"]
        assert bad["pool_status"] == "incomplete"
        assert bad["untraceable_results"] == ["日活提升近三倍。"]
        assert set(bad["missing_fields"]) == {"time_range", "role_scope"}
        assert "2024-06" in bad["date_hints"] and "2024-09" in bad["date_hints"], "缺时间时给出材料中的年月线索"
        assert bad["verbatim_candidates"] == [] or bad["verbatim_candidates"][0]["result"] == "日活提升近三倍。"
        assert bad["possible_duplicates"] == ["ec_ok"], "标题高度相似的卡要提示可能重复"

        legacy = by_id["ec-legacy"]
        assert legacy["pool_status"] == "legacy" and legacy["has_source"] is False
        assert legacy["suggested_sources"][0]["material_id"] == "mat_t1"
        assert "租赁/方案.md" in legacy["suggested_sources"][0]["document"]
        assert legacy["untraceable_results"] == [], "旧卡结果能在材料里逐字找到时不算不可追溯"
        assert result["summary"]["untraceable_cards"] == 1


def test_reconcile_accepts_subset_and_tolerates_missing_materials():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        edir = root / "evidence_cards"
        edir.mkdir()
        (edir / "ec_a.yaml").write_text(_card(id="ec_a", title="A", status="saved_eligible", candidate_pool_eligible="true",
                                              results=["r1"], artifacts=["x"], source_material_ids=["mat_missing"]), encoding="utf-8")
        (edir / "ec_b.yaml").write_text(_card(id="ec_b", title="B", status="draft"), encoding="utf-8")
        with patch.object(evidence, "_EVIDENCE_DIR", edir), patch.object(materials, "_MATERIALS_DIR", root / "materials"):
            result = _rpc(evidence_ids=["ec_a"])
        assert [item["evidence_id"] for item in result["items"]] == ["ec_a"]
        item = result["items"][0]
        assert item["has_source"] is False and item["untraceable_results"] == ["r1"]
        assert item["missing_fields"] == ["time_range", "role_scope"]
        assert result["summary"]["total"] == 1


def test_reconcile_offers_nearest_verbatim_sentence_for_paraphrased_results():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_material(root)
        edir = root / "evidence_cards"
        edir.mkdir()
        (edir / "ec_p.yaml").write_text(_card(
            id="ec_p", title="会员中心", status="saved_incomplete", candidate_pool_eligible="false",
            results=["会员中心上线后日活从1.2万提升到3.5万", "完全无关的一句话用于测试没有候选"], artifacts=["mat_t1"], source_material_ids=["mat_t1"]), encoding="utf-8")
        with patch.object(evidence, "_EVIDENCE_DIR", edir), patch.object(materials, "_MATERIALS_DIR", root / "materials"):
            item = _rpc(evidence_ids=["ec_p"])["items"][0]
        assert len(item["untraceable_results"]) == 2
        assert item["verbatim_candidates"][0]["result"] == "会员中心上线后日活从1.2万提升到3.5万"
        assert item["verbatim_candidates"][0]["verbatim"] == "会员中心上线后日活从 1.2 万提升到 3.5 万"
        assert item["verbatim_candidates"][0]["similarity"] >= 0.8
        assert [c["result"] for c in item["verbatim_candidates"]] == ["会员中心上线后日活从1.2万提升到3.5万"], "无相近原句的结果不给候选"


def test_draft_prompt_keeps_document_language_and_verbatim_results():
    prompt = evidence._llm_draft_prompt("# Material mat_x\n工作内容：负责会员中心。")
    assert "document's own language" in prompt and "Chinese when the document is Chinese" in prompt
    assert "Quote results verbatim" in prompt
    assert prompt.rstrip().endswith("工作内容：负责会员中心。")
