"""证据字段推断与候选确认 handler（C4/C5）。

从 ``evidence.py`` 拆出；证据卡目录与卡片写入仍由原模块提供。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tools.infra import evidence_inference as inference
from tools.infra import evidence_provenance as provenance
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.policy.exclusions import load_evidence_inference_enabled
from tools.sidecar.handlers import evidence as _origin
from tools.sidecar.handlers._shared.llm_config import load_llm_config
from tools.sidecar.handlers.evidence import (
    _find_evidence_path,
    _preserved_blocks,
    _write_evidence_file,
)
from tools.sidecar.handlers._shared.evidence_triage import (
    card_sha as _card_sha,
    load_triage as _load_triage,
)


def _inference_llm_call(prompt: str) -> str:
    llm_config = load_llm_config()
    base_url = str(llm_config.get("base_url") or "").strip()
    if not base_url:
        raise RuntimeError("inference_llm_unavailable")
    payload: dict[str, Any] = {
        "model": str(llm_config["model"]),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_tokens": 1200,
    }
    client = _origin.LLMClient(
        base_url=base_url,
        api_key=str(llm_config["api_key_for_request"]),
        timeout=int(llm_config["timeout"]),
        provider=str(llm_config["provider"]),
        thinking_enabled=llm_config.get("thinking_enabled"),
        reasoning_effort=str(llm_config.get("thinking_effort", "high")),
    )
    response = client.post_json(client.chat_completions_url, payload)
    content = _origin.LLMClient.extract_content(response).strip()
    if not content:
        raise RuntimeError("inference_llm_empty")
    return content


def _inference_target_cards(card_ids: object) -> list[str]:
    if card_ids is not None:
        if not isinstance(card_ids, list) or any(not isinstance(item, str) for item in card_ids):
            raise ValueError("inference_card_ids_invalid")
        return [item.strip() for item in card_ids if item.strip()]
    triage = _load_triage()
    targets: list[str] = []
    if not _origin._EVIDENCE_DIR.exists():
        return targets
    for path in sorted(_origin._EVIDENCE_DIR.glob("*.yaml")):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        evidence_id = doc["scalars"].get("id", path.stem)
        record = triage.get(evidence_id) if isinstance(triage.get(evidence_id), dict) else {}
        if record.get("decision") != "needs_fill":
            continue
        if record.get("card_sha256") and record.get("card_sha256") != _card_sha(path):
            continue
        missing = [field for field in ("time_range", "role_scope") if not str(doc["scalars"].get(field, "")).strip()]
        if missing:
            targets.append(evidence_id)
    return targets


def handle_evidence_infer_fields(params: dict[str, Any]) -> dict[str, Any]:
    """C4：对缺时间/角色的卡运行规则聚合 + 一次 LLM，产出 L3 候选；不写卡。"""
    correlation_id = params["meta"]["correlation_id"]
    index = inference.load_index(Path("."))
    if index is None:
        return {"meta": {"correlation_id": correlation_id}, "status": "index_missing",
                "enabled": _origin.load_evidence_inference_enabled(), "cards": [],
                "summary": {"requested": 0, "candidates": 0}}
    enabled = _origin.load_evidence_inference_enabled()
    target_ids = _inference_target_cards(params.get("card_ids"))
    if not target_ids:
        return {"meta": {"correlation_id": correlation_id}, "status": "no_target_cards",
                "enabled": enabled, "cards": [],
                "summary": {"requested": 0, "candidates": 0}}
    llm_call = _origin._inference_llm_call if enabled else None
    results: list[dict[str, Any]] = []
    for evidence_id in target_ids:
        path = _find_evidence_path(evidence_id)
        if path is None:
            raise KeyError(f"NOT_FOUND: {evidence_id}")
        raw = path.read_bytes()
        doc = parse_simple_yaml(raw.decode("utf-8"))
        result = inference.infer_card(
            root=Path("."), index=index, card_id=evidence_id,
            card_sha256=hashlib.sha256(raw).hexdigest(),
            card_fields=doc["scalars"], card_lists=doc["lists"],
            enabled=enabled, llm_call=llm_call,
        )
        results.append(result)
    status = "ok"
    if any(result.get("status") == "llm_error" for result in results):
        status = "partial"
    candidates = [candidate for result in results for candidate in result.get("candidates") or []]
    summary = {
        "requested": len(results),
        "cards_with_candidates": sum(bool(result.get("candidates")) for result in results),
        "candidates": len(candidates),
        "time_candidates": sum(candidate.get("field") == "time_range" for candidate in candidates),
        "role_candidates": sum(candidate.get("field") == "role_scope" for candidate in candidates),
        "rules_only": sum(result.get("status") == "rules_only" for result in results),
        "cache_hits": sum(result.get("cache") == "hit" for result in results),
        "errors": sum(result.get("status") == "llm_error" for result in results),
    }
    return {"meta": {"correlation_id": correlation_id}, "status": status, "enabled": enabled,
            "cards": results, "summary": summary}


def handle_evidence_confirm_inference(params: dict[str, Any]) -> dict[str, Any]:
    """C5：接受/修改后接受/否决推断候选；接受写字段与 provenance，否决不再提名。"""
    correlation_id = params["meta"]["correlation_id"]
    evidence_id = str(params.get("evidence_id") or "").strip()
    card_sha256 = str(params.get("card_sha256") or "").strip()
    field = str(params.get("field") or "").strip()
    action = str(params.get("action") or "").strip()
    value_override = params.get("value")
    if field not in provenance.SOURCE_FIELDS:
        raise ValueError("evidence_inference_field_invalid")
    if action not in {"accept", "reject"}:
        raise ValueError("evidence_inference_action_invalid")
    path = _find_evidence_path(evidence_id)
    if path is None:
        raise KeyError(f"NOT_FOUND: {evidence_id}")
    current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if not card_sha256 or current_sha != card_sha256:
        raise ValueError("evidence_inference_stale")
    state = inference.load_state(Path("."))
    stored = state["cards"].get(evidence_id)
    candidates = [item for item in (stored or {}).get("candidates") or []
                  if isinstance(item, dict) and item.get("field") == field]
    if not candidates:
        raise ValueError("evidence_inference_candidate_missing")
    requested_value = str(value_override).strip() if isinstance(value_override, str) else ""
    candidate = next((item for item in candidates if requested_value and item.get("value") == requested_value),
                     candidates[0])
    if action == "reject":
        rejected = set(stored.get("rejected") or [])
        rejected.add(str(candidate.get("candidate_hash")))
        stored["rejected"] = sorted(rejected)
        stored["candidates"] = [item for item in stored.get("candidates") or []
                                if item.get("candidate_hash") not in rejected]
        inference.save_state(Path("."), state)
        return {"meta": {"correlation_id": correlation_id}, "status": "rejected",
                "evidence_id": evidence_id, "field": field,
                "candidate_hash": candidate.get("candidate_hash")}
    now = _origin._utcnow_iso()
    accepted_value = requested_value or str(candidate.get("value", ""))
    if requested_value and requested_value != str(candidate.get("value", "")):
        accepted_provenance: dict[str, Any] = {
            "level": "L4", "evidence": [], "confirmed_by_user": True, "confirmed_at": now,
        }
    else:
        accepted_provenance = {
            "level": str(candidate.get("level", "L3")),
            "evidence": candidate.get("evidence") or [],
            "confidence": candidate.get("confidence"),
            "confirmed_by_user": True,
            "confirmed_at": now,
        }
        if field == "time_range":
            accepted_provenance["precision"] = str(candidate.get("precision", "month"))
        if field == "role_scope" and isinstance(candidate.get("first_person_hits"), dict):
            accepted_provenance["first_person_hits"] = candidate["first_person_hits"]
    accepted_provenance = provenance.normalize_provenance(accepted_provenance, field=field)
    if accepted_provenance is None:
        raise ValueError("evidence_inference_provenance_invalid")
    doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
    s = doc["scalars"]
    l = doc["lists"]
    updated_at = _origin._utcnow_iso()
    fields = {
        "id": s.get("id", evidence_id),
        "title": s.get("title", ""),
        "time_range": accepted_value if field == "time_range" else s.get("time_range", ""),
        "context": s.get("context", ""),
        "role_scope": accepted_value if field == "role_scope" else s.get("role_scope", ""),
        "status": s.get("status", "draft"),
        "created_at": s.get("created_at", updated_at),
        "updated_at": updated_at,
        "actions": l.get("actions", []),
        "results": l.get("results", []),
        "stack": l.get("stack", []),
        "artifacts": l.get("artifacts", []),
        "tags": l.get("tags", []),
        "review_decision": "pending",
        "candidate_pool_eligible": False,
    }
    for key in ('raw_source', 'source_documents_json', 'field_sources_json', 'source_material_fingerprints_json',
                'reviewed_facts_json', 'source_whole_material_ids_json',
                'time_range_provenance_json', 'role_scope_provenance_json'):
        if key in s:
            fields[key] = s[key]
    for key in ('source_material_ids', 'missing_items'):
        if key in l:
            fields[key] = l[key]
    fields[provenance.PROVENANCE_SCALARS[field]] = provenance.provenance_json(accepted_provenance)
    _write_evidence_file(path, fields, preserved_blocks=_preserved_blocks(path.read_text(encoding="utf-8")))
    remaining = [item for item in stored.get("candidates") or []
                 if item.get("candidate_hash") != candidate.get("candidate_hash")]
    stored["candidates"] = remaining
    inference.save_state(Path("."), state)
    return {"meta": {"correlation_id": correlation_id}, "status": "accepted",
            "evidence_id": evidence_id, "field": field, "value": accepted_value,
            "card_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "provenance": accepted_provenance}
