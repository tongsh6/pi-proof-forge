from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.infra.persistence.yaml_io import parse_simple_yaml

_EVIDENCE_DIR = Path("evidence_cards")


def _load_evidence_cards() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    if not _EVIDENCE_DIR.exists():
        return cards
    for path in sorted(_EVIDENCE_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        doc = parse_simple_yaml(text)
        s = doc["scalars"]
        cards.append({
            "evidence_id": s.get("id", path.stem),
            "title": s.get("title", ""),
            "time_range": s.get("time_range", ""),
            "role_scope": s.get("role_scope", ""),
            "score": 0,
            "status": "ready",
            "updated_at": "",
        })
    return cards


def _load_evidence_detail(evidence_id: str) -> dict[str, Any] | None:
    for path in _EVIDENCE_DIR.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        doc = parse_simple_yaml(text)
        s = doc["scalars"]
        l = doc["lists"]
        if s.get("id") == evidence_id:
            return {
                "evidence_id": s.get("id", ""),
                "title": s.get("title", ""),
                "time_range": s.get("time_range", ""),
                "context": s.get("context", ""),
                "role_scope": s.get("role_scope", ""),
                "actions": "\n".join(l.get("actions", [])),
                "results": "\n".join(l.get("results", [])),
                "stack": l.get("stack", []),
                "tags": l.get("tags", []),
                "artifacts": [],
            }
    return None


def handle_evidence_list(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    page_size = min(params.get("page_size", 20), 100)
    cards = _load_evidence_cards()

    paginated = cards[:page_size]
    next_cursor = str(page_size) if len(cards) > page_size else None

    return {
        "meta": {"correlation_id": correlation_id},
        "items": paginated,
        "next_cursor": next_cursor,
    }


def handle_evidence_get(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    evidence_id = params["evidence_id"]

    detail = _load_evidence_detail(evidence_id)
    if detail is None:
        raise KeyError(f"NOT_FOUND: {evidence_id}")

    return {
        "meta": {"correlation_id": correlation_id},
        "evidence": detail,
    }
