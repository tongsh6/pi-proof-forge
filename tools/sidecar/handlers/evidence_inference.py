"""证据字段推断与候选确认 handler（C4/C5）。

从 ``evidence.py`` 拆出；证据卡目录与卡片写入仍由原模块提供。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tools.infra import evidence_inference as inference
from tools.infra import evidence_provenance as provenance
from tools.infra import knowledge_index
from tools.infra.evidence_sources import ValidatedSourcePaths
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
    enabled = _origin.load_evidence_inference_enabled()
    target_ids = _inference_target_cards(params.get("card_ids"))
    if not target_ids:
        return {"meta": {"correlation_id": correlation_id}, "status": "no_target_cards",
                "enabled": enabled, "cards": [],
                "summary": {"requested": 0, "candidates": 0}}
    targets = []
    for evidence_id in target_ids:
        path = _find_evidence_path(evidence_id)
        if path is None:
            raise KeyError(f"NOT_FOUND: {evidence_id}")
        raw = path.read_bytes()
        targets.append((evidence_id, path, raw, parse_simple_yaml(raw.decode("utf-8"))))
    root = Path(".")
    index = knowledge_index.build_index(root)
    knowledge_index.save_index(index, root / "knowledge-index")
    captured_sources = ValidatedSourcePaths()
    state = inference.load_state(root, captured_sources=captured_sources)
    llm_call = _origin._inference_llm_call if enabled else None
    results: list[dict[str, Any]] = []
    for evidence_id, path, raw, doc in targets:
        result = inference.infer_card(
            root=root, index=index, card_id=evidence_id, card_path=path,
            card_sha256=hashlib.sha256(raw).hexdigest(),
            card_fields=doc["scalars"], card_lists=doc["lists"],
            state=state, captured_sources=captured_sources,
            enabled=enabled, llm_call=llm_call,
        )
        results.append(result)
    for _, _, _, doc in targets:
        inference.assert_current_inputs(
            root=root, index=index, card_fields=doc["scalars"],
            card_lists=doc["lists"], captured_sources=captured_sources,
        )
    if any(result.get("cache") == "miss" and result.get("status") != "llm_error" for result in results):
        inference.save_state(root, state, expected_sha256=captured_sources.snapshots["inference_state"][1])
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
    """Confirm one identified candidate against its original inputs and controlled card version."""
    correlation_id = params["meta"]["correlation_id"]
    evidence_id = str(params.get("evidence_id") or "").strip()
    card_sha256 = str(params.get("card_sha256") or "").strip()
    candidate_hash = params.get("candidate_hash")
    field = str(params.get("field") or "").strip()
    action = str(params.get("action") or "").strip()
    if field not in provenance.SOURCE_FIELDS:
        raise ValueError("evidence_inference_field_invalid")
    if action not in {"accept", "reject"}:
        raise ValueError("evidence_inference_action_invalid")
    if not isinstance(candidate_hash, str) or not candidate_hash:
        raise ValueError("evidence_inference_candidate_missing")
    path = _find_evidence_path(evidence_id)
    if path is None:
        raise KeyError(f"NOT_FOUND: {evidence_id}")
    if path.is_symlink() or not path.is_file():
        raise ValueError("evidence_inference_stale")
    raw = path.read_bytes()
    current_sha = hashlib.sha256(raw).hexdigest()
    if not card_sha256 or current_sha != card_sha256:
        raise ValueError("evidence_inference_stale")
    root = Path(".")
    captured_state = ValidatedSourcePaths()
    state = inference.load_state(root, captured_sources=captured_state)
    state_snapshot = captured_state.snapshots["inference_state"]
    stored = state["cards"].get(evidence_id)
    if not isinstance(stored, dict):
        raise ValueError("evidence_inference_candidate_missing")
    if stored.get("card_sha256") != current_sha:
        raise ValueError("evidence_inference_stale")
    candidates = [item for item in stored.get("candidates") or []
                  if isinstance(item, dict) and item.get("candidate_hash") == candidate_hash]
    if len(candidates) != 1 or candidates[0].get("field") != field:
        raise ValueError("evidence_inference_candidate_missing")
    candidate = candidates[0]

    def assert_versions() -> None:
        if (path.is_symlink() or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != current_sha):
            raise ValueError("evidence_inference_stale")
        inference._assert_state_version(*state_snapshot)

    if action == "reject":
        assert_versions()
        rejected = set(stored.get("rejected") or [])
        rejected.add(candidate_hash)
        stored["rejected"] = sorted(rejected)
        stored["candidates"] = [item for item in stored.get("candidates") or []
                                if item.get("candidate_hash") != candidate_hash]
        inference.save_state(root, state, expected_sha256=state_snapshot[1])
        return {"meta": {"correlation_id": correlation_id}, "status": "rejected",
                "evidence_id": evidence_id, "field": field, "card_sha256": current_sha,
                "candidate_hash": candidate_hash}

    text = raw.decode("utf-8")
    doc = parse_simple_yaml(text)
    s, l = doc["scalars"], doc["lists"]
    if s.get("id", evidence_id) != evidence_id:
        raise ValueError("evidence_inference_stale")
    if candidate.get("level") not in {"L2", "L3"}:
        raise ValueError("evidence_inference_provenance_invalid")
    candidate_value = candidate.get("value")
    if not isinstance(candidate_value, str) or not candidate_value.strip():
        raise ValueError("evidence_inference_provenance_invalid")
    if "value" in params:
        if not isinstance(params["value"], str) or not params["value"].strip():
            raise ValueError("evidence_inference_value_invalid")
        accepted_value = params["value"].strip()
    else:
        accepted_value = candidate_value
    modified = accepted_value != candidate_value

    def assert_acceptance() -> None:
        if candidate["level"] == "L3" and not _origin.load_evidence_inference_enabled():
            raise ValueError("evidence_inference_disabled")
        inference.assert_confirmation_inputs(
            root, card_id=evidence_id, card_path=path, card_sha256=current_sha,
            card_fields=s, card_lists=l, stored=stored,
        )
        assert_versions()

    assert_acceptance()
    now = _origin._utcnow_iso()
    if modified:
        accepted_provenance: dict[str, Any] = {
            "level": "L4", "evidence": [], "confirmed_by_user": True, "confirmed_at": now,
        }
    else:
        accepted_provenance = {
            "level": candidate["level"],
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
    preserved = _preserved_blocks(text)
    assert_acceptance()
    new_sha = _write_evidence_file(path, fields, preserved_blocks=preserved)
    stored["candidates"] = [] if modified else [
        item for item in stored.get("candidates") or [] if item.get("candidate_hash") != candidate_hash
    ]
    stored["card_sha256"] = new_sha
    inference.save_state(root, state, expected_sha256=state_snapshot[1])
    return {"meta": {"correlation_id": correlation_id}, "status": "accepted",
            "evidence_id": evidence_id, "field": field, "value": accepted_value,
            "candidate_hash": candidate_hash, "card_sha256": new_sha,
            "provenance": accepted_provenance}
