"""质量判项缓存：同版本输入不重复调用 LLM；只缓存已通过校验的判项。"""
from __future__ import annotations

import hashlib
import json

from tools.infra.persistence.atomic_io import atomic_write_text
import os
import tempfile
from pathlib import Path
from urllib.request import Request
from tools.infra.llm.task_runner import parse_json_response
from tools.infra.evidence_provenance import parse_provenance

JUDGE_CACHE_SCHEMA_VERSION = 2


def cards_fingerprint(cards: dict[str, dict]) -> str:
    canonical = [
        {
            "id": card_id,
            "title": str((cards.get(card_id) or {}).get("title", "")),
            "time_range": str((cards.get(card_id) or {}).get("time_range", "")),
            "role_scope": str((cards.get(card_id) or {}).get("role_scope", "")),
            "role_scope_provenance": parse_provenance((cards.get(card_id) or {}).get("role_scope_provenance")
                                                     or (cards.get(card_id) or {}).get("role_scope_provenance_json")),
            "context": str((cards.get(card_id) or {}).get("context", "")),
            "actions": [str(item) for item in ((cards.get(card_id) or {}).get("actions") or [])],
            "results": [str(item) for item in ((cards.get(card_id) or {}).get("results") or [])],
            "stack": [str(item) for item in ((cards.get(card_id) or {}).get("stack") or [])],
        }
        for card_id in sorted(cards)
    ]
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def judge_cache_key(
    *,
    prepared_request: Request,
    trace_inputs: dict,
    resume_sha256: str,
    job_profile_id: str,
    cards: dict[str, dict],
    prompt_version: int,
) -> str:
    if not isinstance(prepared_request, Request) or not isinstance(prepared_request.data, bytes):
        raise ValueError("invalid_prepared_request")
    material = {
        "request_url": prepared_request.full_url,
        "request_sha256": hashlib.sha256(prepared_request.data).hexdigest(),
        "inputs": trace_inputs,
        "resume_sha256": resume_sha256,
        "job_profile_id": job_profile_id,
        "cards_sha256": cards_fingerprint(cards),
        "prompt_version": prompt_version,
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

def cache_path(cache_dir: Path, key: str) -> Path:
    return Path(cache_dir) / f"{key}.json"


def load_judgment(cache_dir: Path, key: str) -> dict | None:
    path = cache_path(cache_dir, key)
    if not path.is_file() or path.is_symlink():
        return None
    try:
        payload = parse_json_response(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("cache_schema_version") != JUDGE_CACHE_SCHEMA_VERSION:
        return None
    judgments = payload.get("judgments")
    return judgments if isinstance(judgments, dict) else None


def save_judgment(cache_dir: Path, key: str, judgments: dict) -> Path:
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = cache_path(directory, key)
    payload = {"cache_schema_version": JUDGE_CACHE_SCHEMA_VERSION, "judgments": judgments}
    atomic_write_text(
        path, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    )
    return path


# --- 突出点用户决策（app-data/quality_decisions.json） ---


def decisions_path(root: Path) -> Path:
    return Path(root) / "app-data" / "quality_decisions.json"


def load_decisions(root: Path, resume_sha256: str) -> dict[str, list[str]]:
    path = decisions_path(root)
    empty = {"rejected": [], "selected": []}
    if not path.is_file() or path.is_symlink():
        return empty
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    resumes = payload.get("resumes") if isinstance(payload, dict) else None
    entry = resumes.get(resume_sha256) if isinstance(resumes, dict) else None
    if not isinstance(entry, dict):
        return empty
    return {
        "rejected": sorted({str(item) for item in entry.get("rejected", []) if isinstance(item, str)}),
        "selected": sorted({str(item) for item in entry.get("selected", []) if isinstance(item, str)}),
    }


def save_highlight_decision(root: Path, resume_sha256: str, highlight: str, action: str) -> dict[str, list[str]]:
    if action not in {"reject", "select"}:
        raise ValueError("quality_decision_invalid")
    path = decisions_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"schema_version": 1, "resumes": {}}
    if path.is_file() and not path.is_symlink():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("resumes"), dict):
                payload = loaded
                payload.setdefault("schema_version", 1)
        except (OSError, ValueError):
            payload = {"schema_version": 1, "resumes": {}}
    entry = payload["resumes"].setdefault(resume_sha256, {"rejected": [], "selected": []})
    rejected = {str(item) for item in entry.get("rejected", []) if isinstance(item, str)}
    selected = {str(item) for item in entry.get("selected", []) if isinstance(item, str)}
    if action == "reject":
        rejected.add(highlight)
        selected.discard(highlight)
    else:
        selected.add(highlight)
        rejected.discard(highlight)
    entry["rejected"] = sorted(rejected)
    entry["selected"] = sorted(selected)
    atomic_write_text(
        path, json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    )
    return {"rejected": entry["rejected"], "selected": entry["selected"]}
