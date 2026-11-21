"""材料对账与补全分流 handler（只读报告 + 旁路分流记录）。

从 ``evidence.py`` 拆出；应用数据目录与证据卡目录经原模块运行时读取，
保证测试对 ``evidence._APP_DATA_DIR``、``evidence._EVIDENCE_DIR`` 的 patch 生效。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.sidecar.handlers import evidence as _origin
from tools.infra.persistence.atomic_io import atomic_write_text
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.sidecar.handlers._shared.evidence_triage import (
    card_sha as _card_sha,
    load_triage as _load_triage,
    triage_path as _triage_path,
)
from tools.sidecar.handlers._shared.material_sources import (
    list_material_source_items,
    materials_dir,
)

# ---- 材料对账（只读）：结果可追溯性、缺项、重复、日期线索 -------------------------------------
_RECONCILE_YEAR_MONTH = re.compile(r"(20\d{2})\s*[-./年]\s*(0?[1-9]|1[0-2])(?![\d])")
_RECONCILE_MAX_HINTS = 8
_RECONCILE_MAX_SUGGESTIONS = 3

# ---- 补全分流：只记旁路文件，不改卡、不影响审核与档案修订；卡变化后旧判断失效 ----------------
_TRIAGE_DECISIONS = {"needs_fill", "not_for_display", "duplicate"}


def _reconcile_material_documents() -> list[dict[str, Any]]:
    """把材料库里的文本材料按文档切分并小写化，供全库逐字查找。"""
    from tools.infra.material_documents import split_material_documents

    documents: list[dict[str, Any]] = []
    for item in list_material_source_items():
        if item.get("extension") not in {".md", ".txt"}:
            continue
        path = materials_dir() / str(item.get("filename", ""))
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for doc in split_material_documents(text, path.name):
            documents.append({"material_id": str(item.get("material_id", "")), "document_id": doc["document_id"],
                              "label": doc["label"], "text": doc["text"], "text_cf": doc["text"].casefold()})
    return documents


def _reconcile_source_text(scalars: dict[str, str], lists: dict[str, list[str]], documents: list[dict[str, Any]]) -> tuple[str, bool]:
    """卡片声明的来源文本：优先精确到所选文档，其次整份材料；没有来源声明时返回空。"""
    material_ids = [str(item) for item in lists.get("source_material_ids", []) if str(item).strip()]
    if not material_ids:
        return "", False
    wanted_docs: set[str] = set()
    try:
        for ref in json.loads(scalars.get("source_documents_json") or "[]"):
            if isinstance(ref, dict) and ref.get("document_id"):
                wanted_docs.add(str(ref["document_id"]))
    except (ValueError, TypeError):
        wanted_docs = set()
    whole_ids=json.loads(scalars.get('source_whole_material_ids_json') or '[]')
    chosen = [doc for doc in documents if doc["material_id"] in material_ids and (not wanted_docs or doc["document_id"] in wanted_docs or doc['material_id'] in whole_ids)]
    if wanted_docs and not chosen:
        chosen = [doc for doc in documents if doc["material_id"] in material_ids]
    return "\n".join(doc["text_cf"] for doc in chosen), bool(chosen)


def _reconcile_bigrams(title: str) -> set[str]:
    compact = re.sub(r"[\s（）()：:、，,。.\-_/]", "", title.casefold())
    return {compact[i:i + 2] for i in range(len(compact) - 1)} if len(compact) > 1 else {compact}


def _reconcile_verbatim_candidates(untraceable: list[str], source_text: str) -> list[dict[str, Any]]:
    """为不可逐字追溯的结果，在来源文本里找最接近的原句（相似度 ≥ 0.55），供用户或修复流程替换；不自动改卡。"""
    import difflib

    if not untraceable or not source_text:
        return []
    sentences = [seg.strip(" -*|>#\t") for seg in re.split(r"[。\n；;！!？?]", source_text)]
    sentences = list(dict.fromkeys(seg for seg in sentences if 6 <= len(seg) <= 400))
    candidates: list[dict[str, Any]] = []
    for item in untraceable:
        needle = item.casefold()
        best = max(((difflib.SequenceMatcher(None, needle, seg).ratio(), seg) for seg in sentences), default=(0.0, ""))
        if best[0] >= 0.55:
            candidates.append({"result": item, "verbatim": best[1], "similarity": round(best[0], 2)})
    return candidates


def _reconcile_pool_status(scalars: dict[str, str], lists: dict[str, list[str]]) -> str:
    status = scalars.get("status", "")
    if status == "saved_eligible" and scalars.get("candidate_pool_eligible") == "true" and lists.get("results") and lists.get("artifacts"):
        return "eligible"
    if status == "saved_incomplete":
        return "incomplete"
    return "legacy" if not status else status


def handle_evidence_triage_set(params: dict[str, Any]) -> dict[str, Any]:
    """记录或清除一张卡的补全分流；decision 为空即清除。"""
    correlation_id = params["meta"]["correlation_id"]
    evidence_id = str(params.get("evidence_id") or "").strip()
    decision = str(params.get("decision") or "").strip()
    note = str(params.get("note") or "").strip()
    duplicate_of = str(params.get("duplicate_of") or "").strip()
    if decision and decision not in _TRIAGE_DECISIONS:
        raise ValueError("evidence_triage_decision_invalid")
    if len(note) > 500:
        raise ValueError("evidence_triage_note_too_long")
    path = _origin._find_evidence_path(evidence_id) if evidence_id else None
    if path is None:
        raise KeyError(f"NOT_FOUND: {evidence_id}")
    if decision == "duplicate":
        if not duplicate_of or duplicate_of == evidence_id or _origin._find_evidence_path(duplicate_of) is None:
            raise ValueError("evidence_triage_duplicate_invalid")
    elif duplicate_of:
        raise ValueError("evidence_triage_duplicate_invalid")
    data = _load_triage()
    if decision:
        data[evidence_id] = {"decision": decision, "note": note, "duplicate_of": duplicate_of,
                             "card_sha256": _card_sha(path), "decided_at": _origin._utcnow_iso()}
    else:
        data.pop(evidence_id, None)
    target = _triage_path()
    atomic_write_text(
        target, json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
    )
    return {"meta": {"correlation_id": correlation_id}, "evidence_id": evidence_id, "triage": data.get(evidence_id)}


def handle_evidence_reconcile(params: dict[str, Any]) -> dict[str, Any]:
    """只读对账报告：不改任何卡，只报告哪些结果不可逐字追溯、缺哪些字段、哪些卡可能重复、材料里有哪些年月线索。"""
    correlation_id = params["meta"]["correlation_id"]
    requested = params.get("evidence_ids")
    wanted: set[str] | None = None
    if requested is not None:
        if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
            raise ValueError("evidence_ids must be a list of strings")
        wanted = {item.strip() for item in requested if item.strip()}
    documents = _reconcile_material_documents()
    triage = _load_triage()
    shas: dict[str, str] = {}
    parsed: list[tuple[str, dict[str, str], dict[str, list[str]]]] = []
    if _origin._EVIDENCE_DIR.exists():
        for path in sorted(_origin._EVIDENCE_DIR.glob("*.yaml")):
            try:
                doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError):
                continue
            evidence_id = doc["scalars"].get("id", path.stem)
            if wanted is not None and evidence_id not in wanted:
                continue
            parsed.append((evidence_id, doc["scalars"], doc["lists"]))
            shas[evidence_id] = _card_sha(path)
    bigrams = {evidence_id: _reconcile_bigrams(scalars.get("title", "")) for evidence_id, scalars, _ in parsed}
    items: list[dict[str, Any]] = []
    for evidence_id, scalars, lists in parsed:
        results = [str(item) for item in lists.get("results", []) if str(item).strip()]
        source_text, has_source = _reconcile_source_text(scalars, lists, documents)
        untraceable = [item for item in results if item.casefold() not in source_text] if has_source else list(results)
        suggestions: list[dict[str, str]] = []
        hint_pool = source_text
        for item in untraceable:
            needle = item.casefold()
            for doc in documents:
                if needle in doc["text_cf"]:
                    ref = {"material_id": doc["material_id"], "document": doc["label"], "result": item}
                    if ref not in suggestions:
                        suggestions.append(ref)
                    if not has_source:
                        hint_pool += "\n" + doc["text_cf"]
                    if len([s for s in suggestions if s["result"] == item]) >= _RECONCILE_MAX_SUGGESTIONS:
                        break
        found_results = {s["result"] for s in suggestions}
        still_untraceable = [item for item in untraceable if item not in found_results]
        verbatim_candidates = _reconcile_verbatim_candidates(still_untraceable, source_text) if has_source else []
        missing = [field for field in ("time_range", "role_scope") if not str(scalars.get(field, "")).strip()]
        missing += [field for field in ("results", "artifacts") if not lists.get(field)]
        date_hints: list[str] = []
        if "time_range" in missing and hint_pool:
            date_hints = sorted({f"{year}-{int(month):02d}" for year, month in _RECONCILE_YEAR_MONTH.findall(hint_pool)})[:_RECONCILE_MAX_HINTS]
        own = bigrams[evidence_id]
        duplicates = [other for other, grams in bigrams.items()
                      if other != evidence_id and own and grams and len(own & grams) / len(own | grams) >= 0.5][:3]
        items.append({
            "evidence_id": evidence_id, "title": scalars.get("title", ""), "pool_status": _reconcile_pool_status(scalars, lists),
            "has_source": has_source, "traceable_results": len(results) - len(untraceable),
            "untraceable_results": still_untraceable, "suggested_sources": suggestions, "verbatim_candidates": verbatim_candidates,
            "missing_fields": missing,
            "date_hints": date_hints, "possible_duplicates": duplicates,
            "triage": ({**triage[evidence_id], "stale": triage[evidence_id].get("card_sha256") != shas[evidence_id]}
                       if isinstance(triage.get(evidence_id), dict) else None),
        })
    active = lambda item: item["triage"] and not item["triage"]["stale"]
    counted = [item for item in items if not (active(item) and item["triage"]["decision"] != "needs_fill")]
    summary = {
        "total": len(items),
        "eligible": sum(item["pool_status"] == "eligible" for item in items),
        "incomplete": sum(item["pool_status"] == "incomplete" for item in items),
        "legacy": sum(item["pool_status"] == "legacy" for item in items),
        "untraceable_cards": sum(bool(item["untraceable_results"]) for item in items),
        "missing_time_range": sum("time_range" in item["missing_fields"] for item in counted),
        "missing_role_scope": sum("role_scope" in item["missing_fields"] for item in counted),
        "duplicate_cards": sum(bool(item["possible_duplicates"]) for item in items),
        "triaged_out": len(items) - len(counted),
        "needs_fill": sum(bool(active(item)) and item["triage"]["decision"] == "needs_fill" for item in items),
        "untriaged": sum(not active(item) for item in items),
    }
    return {"meta": {"correlation_id": correlation_id}, "summary": summary, "items": items}
