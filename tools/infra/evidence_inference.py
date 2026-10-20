"""C4：证据卡时间/角色的跨文档推断（L3）与规则 L2 线索。

只做确定性检索、规则聚合、候选校验与本地状态；LLM 调用由调用方注入。
推断候选不写卡；用户在 App 中确认后才写字段与 provenance。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tools.infra import evidence_provenance as provenance
from tools.infra.career_profile import load_career_profile
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.prompts.context import context_fingerprint

INFERENCE_PROMPT_VERSION = 5
INFERENCE_STATE_SCHEMA_VERSION = 1
MAX_DOCUMENTS = 20
MAX_EXCERPTS = 5

_DATE = re.compile(r"((?:19|20)\d{2})(?:[-./年](\d{1,2}))?(?:[-./月](\d{1,2}))?")
_DESIGN_SOURCE_MARKERS = ("设计", "实施计划", "非完成证明", "方案")
_OWNER = re.compile(r"我(?:负责|主导|设计|决策|推动|牵头|完成|搭建|重构)")
_PARTICIPANT = re.compile(r"(?:我|本人)(?:参与|协同|配合|支持)")


def load_index(root: Path) -> dict | None:
    path = Path(root) / "knowledge-index" / "index.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def candidate_hash(field: str, value: str, evidence: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        [str(field), str(value), sorted(
            (str(item.get("material_id", "")), str(item.get("document_id", "")),
             str(item.get("excerpt", "")), str(item.get("key", "")))
            for item in evidence
        )],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"[\s（）()：:、，,。.\-_/·|]", "", str(text).casefold())
    return {compact[index:index + 2] for index in range(len(compact) - 1)} if len(compact) > 1 else {compact}


def _dates_in(text: str, limit: int = 8) -> list[str]:
    values: list[str] = []
    for year, month, day in _DATE.findall(str(text or "")):
        parts = [year]
        if month:
            parts.append(f"{int(month):02d}")
            if day:
                parts.append(f"{int(day):02d}")
        value = "-".join(parts)
        if value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def select_documents(index: dict, card_fields: dict, card_lists: dict, *, limit: int = MAX_DOCUMENTS) -> list[dict[str, Any]]:
    """直接来源和卡标题优先，背景/技术栈辅助；排除设计资料与合成夹具。"""
    materials = index.get("materials") if isinstance(index.get("materials"), dict) else {}
    nonfact = {
        str(item.get("material_id", ""))
        for item in (index.get("nonfact_materials") or [])
        if isinstance(item, dict)
    }
    query = " ".join(
        [str(card_fields.get("title", ""))]
        + [str(item) for item in (card_lists.get("tags") or [])]
        + [str(item) for item in (card_lists.get("stack") or [])]
        + [str(card_fields.get("context", ""))]
    )
    query_grams = _bigrams(query)
    if not query_grams:
        return []
    title_grams = _bigrams(str(card_fields.get("title", "")))
    try:
        references = json.loads(card_fields.get("source_documents_json") or "[]")
    except (ValueError, TypeError):
        references = []
    bound = {
        (ref["material_id"], ref["document_id"], ref["sha256"])
        for ref in (references if isinstance(references, list) else [])
        if isinstance(ref, dict)
        and all(isinstance(ref.get(key), str) and ref[key] for key in ("material_id", "document_id", "sha256"))
    }
    bound_materials = {ref[0] for ref in bound}
    scored: list[tuple[bool, bool, int, int, dict[str, Any]]] = []
    for material_id, material in materials.items():
        if not isinstance(material, dict) or material_id in nonfact:
            continue
        label = str(material.get("label", ""))
        if any(marker in label for marker in _DESIGN_SOURCE_MARKERS):
            continue
        material_grams = _bigrams(label)
        for document in material.get("documents") or []:
            if not isinstance(document, dict):
                continue
            document_id = str(document.get("document_id", ""))
            if not document_id:
                continue
            doc_text = " ".join(
                [str(document.get("title", "")), str(document.get("label", "")), str(document.get("source_name", ""))]
            )
            doc_grams = _bigrams(doc_text)
            overlap = len(query_grams & doc_grams)
            label_overlap = len(query_grams & material_grams)
            score = overlap * 2 + label_overlap
            is_bound = (material_id, document_id, str(document.get("sha256", ""))) in bound
            is_summary = material_id in bound_materials and document.get("person_doc") is True
            if score <= 0 and not (is_bound or is_summary):
                continue
            scored.append((is_bound, is_summary, len(title_grams & doc_grams), score, {
                "material_id": material_id,
                "document_id": document_id,
                "label": str(document.get("label", "")),
                "title": str(document.get("title", "")),
                "sha256": str(document.get("sha256", "")),
                "material_label": label,
                "material_filename": str(material.get("filename", "")),
                "document_dates": document.get("dates") or {},
                "source_kind": "career_summary" if document.get("person_doc") else "work_material",
            }))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3],
                                  item[4]["material_id"], item[4]["document_id"]))
    return [item[4] for item in scored[:limit]]


def read_document_texts(root: Path, documents: list[dict[str, Any]]) -> dict[str, str]:
    """只读取候选文档所属材料并按 document_id 取正文。"""
    from tools.infra.material_documents import split_material_documents

    materials_dir = Path(root) / "materials"
    texts: dict[str, str] = {}
    by_material: dict[str, set[str]] = {}
    for document in documents:
        by_material.setdefault(document["material_id"], set()).add(document["document_id"])
    for material_id, wanted in by_material.items():
        material = next((item for item in documents if item["material_id"] == material_id), None)
        filename = str((material or {}).get("material_filename", ""))
        path = materials_dir / filename
        if not filename or not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for doc in split_material_documents(text, path.name):
            document_id = str(doc.get("document_id", ""))
            if document_id in wanted:
                texts[document_id] = str(doc.get("text", ""))
    return texts


def aggregate_documents(
    documents: list[dict[str, Any]],
    texts: dict[str, str],
    *,
    max_excerpts: int = MAX_EXCERPTS,
) -> list[dict[str, Any]]:
    aggregates: list[dict[str, Any]] = []
    for document in documents:
        document_id = document["document_id"]
        text = texts.get(document_id, "")
        if not text:
            continue
        dates = _dates_in(" ".join([document.get("label", ""), document.get("title", "")]) + "\n" + text[:1200])
        for key in ("window", "frontmatter"):
            raw = document.get("document_dates", {}).get(key) if isinstance(document.get("document_dates"), dict) else None
            if isinstance(raw, str) and raw:
                dates.extend(item for item in re.findall(r"(?:19|20)\d{2}(?:-\d{2})?(?:-\d{2})?", raw) if item not in dates)
        sentences = [
            segment.strip(" -*|>#\t")
            for segment in re.split(r"[。\n；;！!？?]", text)
            if 8 <= len(segment.strip()) <= 400
        ]
        owner = [segment for segment in sentences if _OWNER.search(segment)]
        participant = [segment for segment in sentences if segment not in owner and _PARTICIPANT.search(segment)]
        aggregates.append({
            "material_id": document["material_id"],
            "document_id": document_id,
            "label": document.get("label", ""),
            "material_label": document.get("material_label", ""),
            "sha256": document.get("sha256", ""),
            "dates": list(dict.fromkeys(dates))[:8],
            "owner_hits": len(owner),
            "participant_hits": len(participant),
            "snippets": list(dict.fromkeys([*owner, *participant]))[:max_excerpts],
            "context_excerpt": text[:1000],
            "excerpt_truncated": len(text) > 1000,
            "source_kind": document.get("source_kind", "work_material"),
        })
    return aggregates


def employment_windows(root: Path, card_id: str) -> tuple[list[tuple[int, int]], list[str]]:
    """卡片所属工作的任职区间；找不到关联时退回全部已确认任职区间。"""
    try:
        profile = load_career_profile(Path(root) / "personal_profile.yaml")
    except (OSError, ValueError):
        return [], []
    work = (profile.get("career") or {}).get("work") or []
    rows: list[dict[str, str]] = []
    for item in work:
        if not isinstance(item, dict) or not item.get("start"):
            continue
        labels = f"{item['start']} ~ {'至今' if item.get('current') or not item.get('end') else item['end']}"
        rows.append({"company": str(item.get("company", "")), "label": labels,
                     "card": card_id if card_id in (item.get("evidence_ids") or []) else ""})
    matched = [row for row in rows if row["card"]] or rows
    labels = [row["label"] for row in matched]
    windows: list[tuple[int, int]] = []
    for label in labels:
        start, end = provenance.period_bounds(label)
        if start is not None:
            windows.append((start, end if end is not None else 999999))
    return windows, labels


def _document_pool(aggregates: list[dict[str, Any]], texts: dict[str, str]) -> dict[str, str]:
    return {item["document_id"]: texts.get(item["document_id"], "") for item in aggregates}


def confirmed_work_context(root: Path, card_id: str) -> list[dict[str, Any]]:
    """只传该卡关联且已确认的任职职责，不传联系方式及无关经历。"""
    try:
        profile = load_career_profile(Path(root) / "personal_profile.yaml")
    except (OSError, ValueError):
        return []
    if not (profile.get("career_status") or {}).get("reviewed"):
        return []
    context = []
    for row in (profile.get("career") or {}).get("work") or []:
        if card_id not in (row.get("evidence_ids") or []):
            continue
        context.append({
            **{key: str(row.get(key) or "")[:500] for key in ("id", "company", "title", "start", "end", "scope")},
            "current": bool(row.get("current")),
            "contributions": [str(value)[:500] for value in (row.get("contributions") or [])[:6]],
        })
    return context


def build_inference_prompt(
    card_fields: dict,
    card_lists: dict,
    aggregates: list[dict[str, Any]],
    windows: list[tuple[int, int]],
    window_labels: list[str],
    work_context: list[dict[str, Any]] | None = None,
) -> str:
    payload = {
        "card": {
            "title": card_fields.get("title", ""),
            "context": str(card_fields.get("context", ""))[:400],
            "existing_time_range": card_fields.get("time_range", ""),
            "existing_role_scope": card_fields.get("role_scope", ""),
            "tags": (card_lists.get("tags") or [])[:8],
            "stack": (card_lists.get("stack") or [])[:8],
        },
        "documents": aggregates,
        "employment_window": window_labels,
        "window_bounds_months": [list(item) for item in windows],
        "confirmed_work_context": work_context or [],
    }
    return (
        "任务：为一张求职证据卡补充缺失的项目时间和本人职责，输出待确认的 L3 候选。"
        "先结合原文语境、工作汇总和已确认任职职责判断人物与项目关联，再归纳具体贡献。"
        "context_excerpt 是原文有界片段，snippets 是辅助关键句；第一人称命中数为零不代表没有个人职责。"
        "允许从角色章节或省略主语的工作记录识别职责；跨文档归属需引用共同支撑的原文，"
        "对于已归属于用户任职的项目，未明示分工且没有反向信息时，优先提名主导/负责人职责，"
        "按 L3 默认归因候选保留依据和不确定性；明确参与、协助或他人负责时按原范围表达，"
        "不能扩成独立完成或全权负责所有成果。"
        "confirmed_work_context 用于理解角色与关联，不能代替具体项目的原文依据。"
        "value 只填写职责短语或时间，不附带 L3、默认归因候选、置信度或审核说明；这些信息由 App 单独展示。"
        "区分项目发生时间、资料整理时间和示例日期；任职区间只作上限约束，"
        "不得将接口样例、需求目标或文件更新时间直接填为项目期间。"
        "只能引用实际提供的原文片段；截断内容不可自行补全，仍无依据时返回空对象。"
        "Return ONLY JSON: {\"time_range\":{\"value\":\"YYYY-MM ~ YYYY-MM or YYYY\",\"precision\":\"year|month\","
        "\"confidence\":0.0-1.0,\"evidence\":[{\"material_id\":\"...\",\"document_id\":\"...\",\"excerpt\":\"<verbatim sentence>\"}]},"
        "\"role_scope\":{\"value\":\"<role>\",\"confidence\":0.0-1.0,"
        "\"evidence\":[{\"material_id\":\"...\",\"document_id\":\"...\",\"excerpt\":\"<verbatim sentence>\"}]}} "
        "Every evidence excerpt must be copied verbatim from the documents below; items without evidence must be empty. "
        f"Prompt version {INFERENCE_PROMPT_VERSION}.\nINPUT JSON:\n" + json.dumps(payload, ensure_ascii=False)
    )


def _evidence_entries(
    raw: Any,
    aggregates: list[dict[str, Any]],
    texts: dict[str, str],
) -> list[dict[str, str]]:
    by_doc = {item["document_id"]: item for item in aggregates}
    entries: list[dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        document_id = str(item.get("document_id", ""))
        aggregate = by_doc.get(document_id)
        if aggregate is None:
            continue
        excerpt = " ".join(str(item.get("excerpt", "")).split())[:300]
        if len(excerpt) < 8 or excerpt not in texts.get(document_id, ""):
            continue
        entries.append({
            "material_id": aggregate["material_id"],
            "document_id": document_id,
            "sha256": aggregate.get("sha256", ""),
            "excerpt": excerpt,
        })
    return entries[:4]


def parse_inference_candidates(
    content: str,
    *,
    aggregates: list[dict[str, Any]],
    texts: dict[str, str],
    windows: list[tuple[int, int]],
) -> list[dict[str, Any]]:
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        payload = json.loads(text[start:end + 1])
    except ValueError:
        return []
    if not isinstance(payload, dict):
        return []
    candidates: list[dict[str, Any]] = []
    by_doc = {item["document_id"]: item for item in aggregates}
    time_raw = payload.get("time_range")
    if isinstance(time_raw, dict) and str(time_raw.get("value", "")).strip():
        value = str(time_raw["value"]).strip()[:60]
        evidence = _evidence_entries(time_raw.get("evidence"), aggregates, texts)
        start_month, _ = provenance.period_bounds(value)
        if evidence and start_month is not None and provenance.within_windows(value, windows):
            precision = "year" if re.fullmatch(r"(?:19|20)\d{2}", value) else "month"
            confidence = _confidence(time_raw.get("confidence"))
            candidates.append({
                "field": "time_range", "value": value, "level": "L3", "precision": precision,
                "confidence": confidence, "evidence": evidence,
                "candidate_hash": candidate_hash("time_range", value, evidence),
            })
    role_raw = payload.get("role_scope")
    if isinstance(role_raw, dict) and str(role_raw.get("value", "")).strip():
        # 等级/候选身份是独立元数据，去掉模型误附的格式注记，不改职责与引用。
        value = re.sub(r"\s*[（(]L[1-5]\s*(?:默认归因|跨文档推断|推断)?候选[）)]\s*$",
                       "", str(role_raw["value"]).strip()).strip()[:80]
        evidence = _evidence_entries(role_raw.get("evidence"), aggregates, texts)
        if value and evidence:
            cited = {entry["document_id"] for entry in evidence}
            hits = {
                "owner": sum(by_doc[document_id]["owner_hits"] for document_id in cited if document_id in by_doc),
                "participant": sum(by_doc[document_id]["participant_hits"] for document_id in cited if document_id in by_doc),
            }
            candidates.append({
                "field": "role_scope", "value": value, "level": "L3",
                "confidence": _confidence(role_raw.get("confidence")), "evidence": evidence,
                "first_person_hits": hits,
                "candidate_hash": candidate_hash("role_scope", value, evidence),
            })
    return candidates


def _confidence(value: object) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 3)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.5


def rules_only_candidates(
    aggregates: list[dict[str, Any]],
    windows: list[tuple[int, int]],
    *,
    limit: int = 2,
) -> list[dict[str, Any]]:
    """C6：关闭 LLM 时只给出规则可得的 L2 时间线索。"""
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for aggregate in aggregates:
        for date in aggregate.get("dates") or []:
            if date in seen or not provenance.within_windows(date, windows):
                continue
            seen.add(date)
            evidence = [{
                "material_id": aggregate["material_id"],
                "document_id": aggregate["document_id"],
                "sha256": aggregate.get("sha256", ""),
                "key": f"document_date:{date}",
            }]
            precision = "year" if re.fullmatch(r"(?:19|20)\d{2}", date) else "month"
            candidates.append({
                "field": "time_range", "value": str(date), "level": "L2", "precision": precision,
                "confidence": 0.5, "evidence": evidence,
                "candidate_hash": candidate_hash("time_range", str(date), evidence),
            })
        if len(candidates) >= limit:
            break
    return candidates[:limit]


def attempt_fingerprint(card_sha256: str, aggregates: list[dict[str, Any]], windows: list[tuple[int, int]],
                        work_context: list[dict[str, Any]] | None = None) -> str:
    canonical = json.dumps(
        {
            "card": card_sha256,
            "documents": sorted((item["document_id"], item.get("sha256", "")) for item in aggregates),
            "windows": [list(item) for item in windows],
            "prompt": INFERENCE_PROMPT_VERSION,
            "task_context": context_fingerprint(),
            "confirmed_work_context": work_context or [],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def state_path(root: Path) -> Path:
    return Path(root) / "app-data" / "evidence_inference.json"


def load_state(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.is_file() or path.is_symlink():
        return {"schema_version": INFERENCE_STATE_SCHEMA_VERSION, "cards": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema_version": INFERENCE_STATE_SCHEMA_VERSION, "cards": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), dict):
        return {"schema_version": INFERENCE_STATE_SCHEMA_VERSION, "cards": {}}
    payload.setdefault("schema_version", INFERENCE_STATE_SCHEMA_VERSION)
    return payload


def save_state(root: Path, state: dict[str, Any]) -> Path:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return path


def infer_card(
    *,
    root: Path,
    index: dict,
    card_id: str,
    card_sha256: str,
    card_fields: dict,
    card_lists: dict,
    enabled: bool,
    llm_call: Callable[[str], str] | None,
) -> dict[str, Any]:
    windows, window_labels = employment_windows(root, card_id)
    work_context = confirmed_work_context(root, card_id)
    documents = select_documents(index, card_fields, card_lists)
    texts = read_document_texts(root, documents)
    aggregates = aggregate_documents(documents, texts)
    fingerprint = attempt_fingerprint(card_sha256, aggregates, windows, work_context)
    state = load_state(root)
    stored = state["cards"].get(card_id)
    rejected = set((stored or {}).get("rejected") or [])
    if (
        isinstance(stored, dict)
        and stored.get("card_sha256") == card_sha256
        and stored.get("attempt_fingerprint") == fingerprint
    ):
        candidates = [
            candidate for candidate in stored.get("candidates") or []
            if isinstance(candidate, dict) and candidate.get("candidate_hash") not in rejected
        ]
        return {"card_id": card_id, "card_sha256": card_sha256, "cache": "hit",
                "status": "rules_only" if stored.get("rules_only") else "ok",
                "candidates": candidates, "documents": len(aggregates), "windows": window_labels}
    if not enabled or llm_call is None:
        candidates = rules_only_candidates(aggregates, windows)
        status = "rules_only"
        error = ""
    else:
        try:
            content = llm_call(build_inference_prompt(card_fields, card_lists, aggregates, windows, window_labels, work_context))
            candidates = parse_inference_candidates(content, aggregates=aggregates, texts=texts, windows=windows)
            status = "ok"
            error = ""
        except Exception as exc:  # 推断失败不写卡、不编造候选
            candidates = []
            status = "llm_error"
            error = str(exc)[:300]
    candidates = [candidate for candidate in candidates if candidate.get("candidate_hash") not in rejected]
    if status != "llm_error":
        state["cards"][card_id] = {
            "card_sha256": card_sha256,
            "attempt_fingerprint": fingerprint,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rules_only": status == "rules_only",
            "candidates": candidates,
            "rejected": sorted(rejected),
        }
        save_state(root, state)
    return {"card_id": card_id, "card_sha256": card_sha256, "cache": "miss", "status": status,
            "error": error, "candidates": candidates, "documents": len(aggregates), "windows": window_labels}
