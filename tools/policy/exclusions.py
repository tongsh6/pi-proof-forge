from __future__ import annotations

import os
from pathlib import Path

from tools.infra.persistence.yaml_io import dump_yaml, parse_simple_yaml

_DEFAULT_POLICY_PATH = "policy.yaml"


def load_exclusion_list(path: Path | None = None) -> list[str]:
    policy_path = _resolve_policy_path(path)
    if policy_path is None or not policy_path.exists():
        return []
    text = policy_path.read_text(encoding="utf-8")
    doc = parse_simple_yaml(text)
    lists = doc.get("lists", {})
    if "exclusion_list" in lists:
        return _normalize_entries(lists.get("exclusion_list", []))
    entries: list[str] = []
    entries.extend(lists.get("excluded_companies", []))
    entries.extend(lists.get("excluded_legal_entities", []))
    return _normalize_entries(entries)


def save_exclusion_list(entries: list[str], path: Path | None = None) -> Path | None:
    policy_path = _resolve_policy_path(path)
    if policy_path is None:
        return None
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    if policy_path.exists():
        doc = parse_simple_yaml(policy_path.read_text(encoding="utf-8"))
        scalars = doc.get("scalars", {})
        lists = doc.get("lists", {})
    lists["exclusion_list"] = _normalize_entries(entries)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    _ = policy_path.write_text(dump_yaml(scalars, lists), encoding="utf-8")
    return policy_path


def is_company_excluded(company: str, exclusions: list[str]) -> bool:
    normalized_company = _normalize_text(company)
    if not normalized_company:
        return False
    for entry in exclusions:
        match, value = _parse_rule(entry)
        if not value:
            continue
        if match == "contains":
            if value in normalized_company:
                return True
        else:
            if value == normalized_company:
                return True
    return False


def _resolve_policy_path(path: Path | None) -> Path | None:
    if path is not None:
        return path
    env_path = os.environ.get("PPF_POLICY_PATH")
    if env_path:
        return Path(env_path)
    return Path(_DEFAULT_POLICY_PATH)


def _normalize_entries(entries: list[str]) -> list[str]:
    cleaned: list[str] = []
    for entry in entries:
        value = entry.strip()
        if value:
            cleaned.append(value)
    return cleaned


def _parse_rule(entry: str) -> tuple[str, str]:
    raw = entry.strip()
    lowered = raw.lower()
    if lowered.startswith("contains:"):
        return "contains", _normalize_text(raw[len("contains:") :])
    if lowered.startswith("exact:"):
        return "exact", _normalize_text(raw[len("exact:") :])
    return "exact", _normalize_text(raw)


def _normalize_text(value: str) -> str:
    return "".join(value.casefold().split())
