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
from tools.infra.evidence_sources import (
    ValidatedSourcePaths, assert_source_snapshot, exact_document_groups, validated_source_inputs,
)
from tools.infra.persistence.atomic_io import atomic_write_text
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.prompts.context import context_fingerprint

INFERENCE_PROMPT_VERSION = 7
INFERENCE_STATE_SCHEMA_VERSION = 1
MAX_DOCUMENTS = 20
MAX_EXCERPTS = 5

_DATE = re.compile(r"((?:19|20)\d{2})(?:[-./年](\d{1,2}))?(?:[-./月](\d{1,2}))?")
_DESIGN_SOURCE_MARKERS = ("设计", "实施计划", "非完成证明", "方案")
_OWNER = re.compile(r"我(?:负责|主导|设计|决策|推动|牵头|完成|搭建|重构)")
_PARTICIPANT = re.compile(r"(?:我|本人)(?:参与|协同|配合|支持)")




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
    scored: list[tuple[bool, int, int, dict[str, Any]]] = []
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
            if score <= 0 and not is_bound:
                continue
            scored.append((is_bound, len(title_grams & doc_grams), score, {
                "material_id": material_id,
                "document_id": document_id,
                "label": str(document.get("label", "")),
                "title": str(document.get("title", "")),
                "sha256": str(document.get("sha256", "")),
                "material_label": label,
                "document_dates": document.get("dates") or {},
            }))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2],
                                  item[3]["material_id"], item[3]["document_id"]))
    return [item[3] for item in scored[:limit]]


def read_document_texts(
    root: Path, documents: list[dict[str, Any]], *, asset_inventory: dict[str, str],
    card_fields: dict, card_lists: dict,
) -> ValidatedSourcePaths:
    """从当前登记材料核对所选三元引用，保留实际读取的文本与版本。"""
    from tools.infra import referenced_materials as rm
    from tools.infra.material_documents import split_material_documents
    from tools.policy.exclusions import load_material_source_roots, resolve_policy_path

    materials_dir = (Path(root) / "materials").absolute()
    try:
        bindings = json.loads(card_fields.get("source_documents_json") or "[]")
        whole = json.loads(card_fields.get("source_whole_material_ids_json") or "[]")
        bound = exact_document_groups(card_lists.get("source_material_ids") or [], bindings, whole)
        fingerprints = json.loads(card_fields.get("source_material_fingerprints_json") or "{}")
        if not isinstance(fingerprints, dict):
            fingerprints = {}
    except (ValueError, TypeError):
        bound, fingerprints = {}, {}

    groups: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        mid = document["material_id"]
        if (not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", mid)
                or any(not re.fullmatch(r"[0-9a-f]{64}", str(document.get(key, "")))
                       for key in ("document_id", "sha256"))):
            raise ValueError("material_document_reference_invalid")
        groups.setdefault(mid, []).append(document)
    snapshots, texts = {}, {}
    try:
        for mid, selected in groups.items():
            meta_path = materials_dir / f"{mid}.meta.yaml"
            if materials_dir.is_symlink() or meta_path.is_symlink() or not meta_path.is_file():
                raise ValueError("material_source_changed")
            meta_raw = meta_path.read_bytes()
            meta_sha = hashlib.sha256(meta_raw).hexdigest()
            if meta_sha != asset_inventory.get(f"materials/{mid}.meta.yaml"):
                raise ValueError("material_source_changed")
            item = parse_simple_yaml(meta_raw.decode("utf-8"))["scalars"]
            filename = str(item.get("filename") or "")
            path = materials_dir / filename
            if (item.get("material_id") != mid or not filename or Path(filename).is_absolute()
                    or path.is_symlink() or not path.is_file()
                    or not path.resolve().is_relative_to(materials_dir.resolve())):
                raise ValueError("material_source_changed")
            refs = [{"material_id": mid, "document_id": document["document_id"], "sha256": document["sha256"]}
                    for document in selected]
            if item.get("source_mode") == "referenced":
                roots = load_material_source_roots(resolve_policy_path(Path(root)))
                existing = {(ref["document_id"], ref["sha256"]) for ref in bound.get(mid, [])}
                narrow = (isinstance(fingerprints.get(mid), dict) and bool(fingerprints[mid])
                          and bool(existing)
                          and all((ref["document_id"], ref["sha256"]) in existing for ref in refs))
                if not narrow:
                    manifest_path = materials_dir / ".referenced" / f"{mid}.manifest.json"
                    if manifest_path.is_symlink() or not manifest_path.is_file():
                        raise ValueError("material_source_changed")
                    manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
                    target = Path(str(item.get("source_root") or "")) / str(item.get("source_relpath") or "")
                    rm.resolve_under_roots(target, roots)
                    if rm.verify_manifest(target, manifest).get("status") != "ok":
                        raise ValueError("material_source_changed")
                _, verified, captured = rm.verify_bound_documents(
                    materials_dir, item, refs, roots,
                    fingerprint=fingerprints[mid] if narrow else None)
                if captured[f"evidence_meta:{mid}"][1] != meta_sha:
                    raise ValueError("material_source_changed")
                snapshots.update(captured)
                texts.update(((mid, document_id), text) for document_id, text in verified.items())
            else:
                raw = path.read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                current = {doc["document_id"]: doc
                           for doc in split_material_documents(raw.decode("utf-8"), path.name)}
                for ref in refs:
                    doc = current.get(ref["document_id"])
                    if doc is None or doc["sha256"] != ref["sha256"]:
                        raise ValueError("material_document_changed_or_missing")
                    texts[(mid, ref["document_id"])] = doc["text"]
                snapshots[f"evidence_material:{mid}"] = (path, digest)
                snapshots[f"evidence_meta:{mid}"] = (meta_path, meta_sha)
        assert_source_snapshot(snapshots)
    except (OSError, UnicodeError, KeyError, TypeError) as exc:
        raise ValueError("material_source_changed") from exc
    return ValidatedSourcePaths(snapshots, documents=texts)



def aggregate_documents(
    documents: list[dict[str, Any]],
    texts: dict[tuple[str, str], str],
    *,
    max_excerpts: int = MAX_EXCERPTS,
) -> list[dict[str, Any]]:
    aggregates: list[dict[str, Any]] = []
    for document in documents:
        document_id = document["document_id"]
        text = texts.get((document["material_id"], document_id), "")
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
        })
    return aggregates


def _confirmed_profile(root: Path, card_id: str) -> tuple[dict, ValidatedSourcePaths]:
    """未采用的草稿不提供约束；已采用的上下文保留同次解析与依赖版本。"""
    from tools.infra.career_profile import inspect_career

    path = (Path(root) / "personal_profile.yaml").absolute()
    if not path.is_file() or path.is_symlink():
        return {}, ValidatedSourcePaths()
    try:
        raw = path.read_bytes()
        fields = dict(parse_simple_yaml(raw.decode("utf-8"))["scalars"])
        captured = {}
        profile = inspect_career(fields, path.parent / "evidence_cards", captured_sources=captured)
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}, ValidatedSourcePaths()
    if (not profile["career_status"]["reviewed"]
            or not any(card_id in row.get("evidence_ids", []) for row in profile["career"]["work"])):
        return {}, ValidatedSourcePaths()
    sources = ValidatedSourcePaths({
        **captured, "personal_profile": (path, hashlib.sha256(raw).hexdigest()),
    })
    assert_source_snapshot(sources.snapshots)
    return profile, sources


def employment_windows(profile: dict, card_id: str) -> tuple[list[tuple[int, int]], list[str]]:
    """只使用同次已确认档案中与当前卡关联的任职区间。"""
    labels = [
        f"{row['start']} ~ {'至今' if row.get('current') or not row.get('end') else row['end']}"
        for row in (profile.get("career") or {}).get("work") or []
        if card_id in row.get("evidence_ids", []) and row.get("start")
    ]
    windows = []
    for label in labels:
        start, end = provenance.period_bounds(label)
        if start is not None:
            windows.append((start, end if end is not None else 999999))
    return windows, labels


def confirmed_work_context(profile: dict, card_id: str) -> list[dict[str, Any]]:
    """只投影同次确认档案中的关联职责，不重新读取档案。"""
    context = []
    for row in (profile.get("career") or {}).get("work") or []:
        if card_id not in row.get("evidence_ids", []):
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
    texts: dict[tuple[str, str], str],
) -> list[dict[str, str]]:
    by_doc = {(item["material_id"], item["document_id"]): item for item in aggregates}
    entries: list[dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        document_id = str(item.get("document_id", ""))
        source_key = (str(item.get("material_id", "")), document_id)
        aggregate = by_doc.get(source_key)
        if aggregate is None:
            continue
        excerpt = " ".join(str(item.get("excerpt", "")).split())[:300]
        if len(excerpt) < 8 or excerpt not in texts.get(source_key, ""):
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
    texts: dict[tuple[str, str], str],
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
    by_doc = {(item["material_id"], item["document_id"]): item for item in aggregates}
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
            cited = {(entry["material_id"], entry["document_id"]) for entry in evidence}
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


def attempt_fingerprint(input_basis: dict[str, Any]) -> str:
    """绑定完整原始依据；保留文档顺序，派生语境由来源版本和现协议确定。"""
    canonical = json.dumps(input_basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _merge_sources(target: ValidatedSourcePaths, incoming: ValidatedSourcePaths) -> None:
    for key, (path, digest) in incoming.snapshots.items():
        previous = target.snapshots.get(key)
        if previous is not None and (previous[0].resolve() != path.resolve() or previous[1] != digest):
            raise ValueError("material_source_changed")
        target.snapshots[key] = (path.absolute(), digest)
        target[key] = path.absolute()
    for key, text in incoming.documents.items():
        if key in target.documents and target.documents[key] != text:
            raise ValueError("material_source_changed")
        target.documents[key] = text


def _assert_state_version(path: Path, expected: str) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("evidence_inference_state_changed")
    current = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
    if current != expected:
        raise ValueError("evidence_inference_state_changed")


def _assert_selected_inputs(
    *, root: Path, documents: list[dict[str, Any]], asset_inventory: dict[str, str],
    card_fields: dict, card_lists: dict, captured_sources: ValidatedSourcePaths,
) -> None:
    """推断与确认共用原文、历史依赖和当前来源许可的复核。"""
    snapshots = {key: value for key, value in captured_sources.snapshots.items() if key != "inference_state"}
    assert_source_snapshot(snapshots)
    current = read_document_texts(
        root, documents, asset_inventory=asset_inventory,
        card_fields=card_fields, card_lists=card_lists)
    for key, (path, digest) in current.snapshots.items():
        original = snapshots.get(key)
        if original is None or original[0].resolve() != path.resolve() or original[1] != digest:
            raise ValueError("material_source_changed")
    if any(key in captured_sources.documents and captured_sources.documents[key] != text
           for key, text in current.documents.items()):
        raise ValueError("material_source_changed")
    # 职业档案可能采用没有进入本卡召回集合的材料，沿原卡依赖复核当前许可。
    for key, (path, expected) in snapshots.items():
        if not key.startswith("career_evidence:"):
            continue
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("material_source_changed")
        dependencies = validated_source_inputs(parse_simple_yaml(raw.decode("utf-8")), path.parent.parent / "materials")
        for source_key, (source_path, digest) in dependencies.snapshots.items():
            original = snapshots.get(source_key)
            if original is None or original[0].resolve() != source_path.resolve() or original[1] != digest:
                raise ValueError("material_source_changed")
    assert_source_snapshot(snapshots)
    state_snapshot = captured_sources.snapshots.get("inference_state")
    if state_snapshot is not None:
        _assert_state_version(*state_snapshot)


def assert_current_inputs(
    *, root: Path, index: dict, card_fields: dict, card_lists: dict,
    captured_sources: ValidatedSourcePaths,
) -> None:
    """当前推断使用同次已冻结的导航集合；不替换原输入版本。"""
    _assert_selected_inputs(
        root=root, documents=select_documents(index, card_fields, card_lists),
        asset_inventory=index.get("asset_inventory") or {},
        card_fields=card_fields, card_lists=card_lists, captured_sources=captured_sources,
    )


def _assert_basis_contract(basis: dict[str, Any]) -> None:
    if (type(basis.get("prompt_version")) is not int
            or basis["prompt_version"] != INFERENCE_PROMPT_VERSION
            or basis.get("task_context") != context_fingerprint()):
        raise ValueError("evidence_inference_stale")


def assert_confirmation_inputs(
    root: Path, *, card_id: str, card_path: Path, card_sha256: str,
    card_fields: dict, card_lists: dict, stored: dict,
) -> None:
    """确认只复核原推断集合；服务端游标只承认目标文件的受控接续。"""
    basis = stored.get("input_basis")
    if (not isinstance(basis, dict)
            or basis.keys() != {"prompt_version", "task_context", "documents", "snapshots"}
            or stored.get("card_sha256") != card_sha256):
        raise ValueError("evidence_inference_stale")
    _assert_basis_contract(basis)
    documents, saved = basis["documents"], basis["snapshots"]
    if (not isinstance(documents, list) or len(documents) > MAX_DOCUMENTS
            or not isinstance(saved, dict) or not saved or "inference_state" in saved):
        raise ValueError("evidence_inference_stale")
    identities = set()
    for document in documents:
        if (not isinstance(document, dict)
                or document.keys() != {"material_id", "document_id", "sha256"}
                or not isinstance(document["material_id"], str)
                or not re.fullmatch(r"[A-Za-z0-9_-]+", document["material_id"])
                or any(not isinstance(document[key], str)
                       or not re.fullmatch(r"[0-9a-f]{64}", document[key])
                       for key in ("document_id", "sha256"))):
            raise ValueError("evidence_inference_stale")
        identity = tuple(document[key] for key in ("material_id", "document_id", "sha256"))
        if identity in identities:
            raise ValueError("evidence_inference_stale")
        identities.add(identity)
    snapshots = {}
    for key, value in saved.items():
        if (not isinstance(key, str) or not isinstance(value, dict)
                or value.keys() != {"path", "sha256"}
                or not isinstance(value["path"], str) or not value["path"]
                or not Path(value["path"]).is_absolute()
                or not isinstance(value["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])):
            raise ValueError("evidence_inference_stale")
        snapshots[key] = (Path(value["path"]), value["sha256"])
    if stored.get("attempt_fingerprint") != attempt_fingerprint(basis):
        raise ValueError("evidence_inference_stale")
    target_key = f"evidence_card:{card_id}"
    original_target = snapshots.get(target_key)
    target = Path(card_path).absolute()
    if (original_target is None or original_target[0].resolve() != target.resolve()
            or not re.fullmatch(r"[0-9a-f]{64}", card_sha256)):
        raise ValueError("evidence_inference_stale")
    for key, (path, digest) in list(snapshots.items()):
        if path.resolve() != target.resolve():
            continue
        if (key != target_key and not key.startswith("career_evidence:")) or digest != original_target[1]:
            raise ValueError("evidence_inference_stale")
        snapshots[key] = (path, card_sha256)
    for candidate in stored.get("candidates") or []:
        if not isinstance(candidate, dict):
            raise ValueError("evidence_inference_stale")
        for ref in candidate.get("evidence") or []:
            if (not isinstance(ref, dict)
                    or tuple(ref.get(key) for key in ("material_id", "document_id", "sha256")) not in identities):
                raise ValueError("evidence_inference_stale")
    inventory = {}
    for document in documents:
        mid = document["material_id"]
        meta = snapshots.get(f"evidence_meta:{mid}")
        if meta is None or meta[0].resolve() != (Path(root) / "materials" / f"{mid}.meta.yaml").resolve():
            raise ValueError("evidence_inference_stale")
        inventory[f"materials/{mid}.meta.yaml"] = meta[1]
    _assert_selected_inputs(
        root=root, documents=documents, asset_inventory=inventory,
        card_fields=card_fields, card_lists=card_lists,
        captured_sources=ValidatedSourcePaths(snapshots),
    )
    _assert_basis_contract(basis)


def state_path(root: Path) -> Path:
    return Path(root) / "app-data" / "evidence_inference.json"


def load_state(root: Path, *, captured_sources: ValidatedSourcePaths | None = None) -> dict[str, Any]:
    path = state_path(root)
    if path.is_symlink():
        if captured_sources is not None:
            raise ValueError("evidence_inference_state_changed")
        return {"schema_version": INFERENCE_STATE_SCHEMA_VERSION, "cards": {}}
    raw = path.read_bytes() if path.is_file() else None
    if captured_sources is not None:
        _merge_sources(captured_sources, ValidatedSourcePaths({
            "inference_state": (path.absolute(), hashlib.sha256(raw).hexdigest() if raw is not None else ""),
        }))
    if raw is None:
        return {"schema_version": INFERENCE_STATE_SCHEMA_VERSION, "cards": {}}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        return {"schema_version": INFERENCE_STATE_SCHEMA_VERSION, "cards": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), dict):
        return {"schema_version": INFERENCE_STATE_SCHEMA_VERSION, "cards": {}}
    payload.setdefault("schema_version", INFERENCE_STATE_SCHEMA_VERSION)
    return payload


def save_state(root: Path, state: dict[str, Any], *, expected_sha256: str | None = None) -> Path:
    path = state_path(root)
    if expected_sha256 is not None:
        _assert_state_version(path, expected_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path, json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True)
    )
    return path



def infer_card(
    *, root: Path, index: dict, card_id: str, card_path: Path, card_sha256: str,
    card_fields: dict, card_lists: dict, enabled: bool,
    llm_call: Callable[[str], str] | None, state: dict,
    captured_sources: ValidatedSourcePaths,
) -> dict[str, Any]:
    card_sources = ValidatedSourcePaths({
        f"evidence_card:{card_id}": (Path(card_path).absolute(), card_sha256),
    })
    assert_source_snapshot(card_sources.snapshots)
    profile, profile_sources = _confirmed_profile(root, card_id)
    _merge_sources(card_sources, profile_sources)
    windows, window_labels = employment_windows(profile, card_id)
    work_context = confirmed_work_context(profile, card_id)
    documents = select_documents(index, card_fields, card_lists)
    sources = read_document_texts(root, documents, asset_inventory=index.get("asset_inventory") or {},
                                  card_fields=card_fields, card_lists=card_lists)
    _merge_sources(card_sources, sources)
    _merge_sources(captured_sources, card_sources)
    texts = sources.documents
    aggregates = aggregate_documents(documents, texts)
    input_basis = {
        "prompt_version": INFERENCE_PROMPT_VERSION,
        "task_context": context_fingerprint(),
        "documents": [{key: document[key] for key in ("material_id", "document_id", "sha256")}
                      for document in documents],
        "snapshots": {key: {"path": str(path.absolute()), "sha256": digest}
                      for key, (path, digest) in card_sources.snapshots.items()},
    }
    fingerprint = attempt_fingerprint(input_basis)
    assert_current_inputs(root=root, index=index, card_fields=card_fields, card_lists=card_lists,
                          captured_sources=captured_sources)
    _assert_basis_contract(input_basis)
    stored = state["cards"].get(card_id)
    rejected = set((stored or {}).get("rejected") or [])
    rules_only = not enabled or llm_call is None
    if (
        isinstance(stored, dict)
        and stored.get("card_sha256") == card_sha256
        and stored.get("attempt_fingerprint") == fingerprint
        and stored.get("input_basis") == input_basis
        and bool(stored.get("rules_only")) == rules_only
    ):
        candidates = [
            candidate for candidate in stored.get("candidates") or []
            if isinstance(candidate, dict) and candidate.get("candidate_hash") not in rejected
        ]
        return {"card_id": card_id, "card_sha256": card_sha256, "cache": "hit",
                "status": "rules_only" if rules_only else "ok",
                "candidates": candidates, "documents": len(aggregates), "windows": window_labels}
    if rules_only:
        candidates = rules_only_candidates(aggregates, windows)
        status = "rules_only"
        error = ""
    else:
        try:
            content = llm_call(build_inference_prompt(card_fields, card_lists, aggregates, windows, window_labels, work_context))
            candidates = parse_inference_candidates(content, aggregates=aggregates, texts=texts, windows=windows)
            status = "ok"
            error = ""
        except Exception as exc:  # 模型失败不编造候选；来源复核在此边界之外。
            candidates = []
            status = "llm_error"
            error = str(exc)[:300]
    assert_current_inputs(root=root, index=index, card_fields=card_fields, card_lists=card_lists,
                          captured_sources=captured_sources)
    _assert_basis_contract(input_basis)
    candidates = [candidate for candidate in candidates if candidate.get("candidate_hash") not in rejected]
    if status != "llm_error":
        state["cards"][card_id] = {
            "card_sha256": card_sha256,
            "attempt_fingerprint": fingerprint,
            "input_basis": input_basis,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rules_only": rules_only,
            "candidates": candidates,
            "rejected": sorted(rejected),
        }
    return {"card_id": card_id, "card_sha256": card_sha256, "cache": "miss", "status": status,
            "candidates": candidates, "documents": len(aggregates), "windows": window_labels,
            **({"error": error} if error else {})}
