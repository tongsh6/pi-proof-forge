from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from tools.infra.persistence.yaml_io import dump_yaml, parse_simple_yaml, unquote

_DEFAULT_POLICY_PATH = "policy.yaml"


@dataclass(frozen=True)
class PolicyExclusions:
    company_rules: tuple[str, ...]
    legal_entities: tuple[str, ...]


def load_exclusion_policy(path: Path | None = None) -> PolicyExclusions:
    policy_path = _resolve_policy_path(path)
    if policy_path is None or not policy_path.exists():
        return PolicyExclusions(company_rules=(), legal_entities=())

    text = policy_path.read_text(encoding="utf-8")
    doc = parse_simple_yaml(text)
    lists = doc.get("lists", {})
    nested_companies, nested_legal_entities = _parse_nested_filters(text)

    company_rules = _merge_entries(
        lists.get("exclusion_list", []),
        lists.get("excluded_companies", []),
        nested_companies,
    )
    legal_entities = _merge_entries(
        lists.get("excluded_legal_entities", []),
        nested_legal_entities,
    )
    return PolicyExclusions(
        company_rules=tuple(company_rules),
        legal_entities=tuple(legal_entities),
    )


def load_exclusion_list(path: Path | None = None) -> list[str]:
    return list(load_exclusion_policy(path).company_rules)


def load_legal_entity_exclusion_list(path: Path | None = None) -> list[str]:
    return list(load_exclusion_policy(path).legal_entities)


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


def save_legal_entity_exclusion_list(
    entries: list[str], path: Path | None = None
) -> Path | None:
    policy_path = _resolve_policy_path(path)
    if policy_path is None:
        return None
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    if policy_path.exists():
        doc = parse_simple_yaml(policy_path.read_text(encoding="utf-8"))
        scalars = doc.get("scalars", {})
        lists = doc.get("lists", {})
    lists["excluded_legal_entities"] = _normalize_entries(entries)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    _ = policy_path.write_text(dump_yaml(scalars, lists), encoding="utf-8")
    return policy_path


def is_company_excluded(company: str, exclusions: list[str]) -> bool:
    return _matches_company_rules(company, exclusions)


def match_exclusion(
    company: str,
    legal_entity: str,
    policy: PolicyExclusions,
) -> str | None:
    normalized_legal_entity = _normalize_text(legal_entity)
    if normalized_legal_entity:
        for entry in policy.legal_entities:
            if _normalize_text(entry) == normalized_legal_entity:
                return "excluded_legal_entity"
    if _matches_company_rules(company, list(policy.company_rules)):
        return "excluded_company"
    return None


def load_delivery_settings(path: Path | None = None) -> tuple[str, bool]:
    """Return (delivery_mode, batch_review) from policy file; defaults ('auto', False)."""
    policy_path = _resolve_policy_path(path)
    if policy_path is None or not policy_path.exists():
        return ("auto", False)
    doc = parse_simple_yaml(policy_path.read_text(encoding="utf-8"))
    scalars = doc.get("scalars", {})
    mode = scalars.get("delivery_mode", "auto")
    if mode not in ("auto", "manual"):
        mode = "auto"
    batch = (scalars.get("batch_review", "false").lower() in ("true", "1"))
    return (mode, batch)


def save_delivery_settings(
    delivery_mode: str,
    batch_review: bool,
    path: Path | None = None,
) -> Path | None:
    """Persist delivery_mode and batch_review to policy file; merge with existing."""
    policy_path = _resolve_policy_path(path)
    if policy_path is None:
        return None
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    if policy_path.exists():
        doc = parse_simple_yaml(policy_path.read_text(encoding="utf-8"))
        scalars = doc.get("scalars", {})
        lists = doc.get("lists", {})
    scalars["delivery_mode"] = delivery_mode if delivery_mode in ("auto", "manual") else "auto"
    scalars["batch_review"] = "true" if batch_review else "false"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(dump_yaml(scalars, lists), encoding="utf-8")
    return policy_path


def _resolve_policy_path(path: Path | None) -> Path | None:
    if path is not None:
        return path
    env_path = os.environ.get("PPF_POLICY_PATH")
    if env_path:
        return Path(env_path)
    return Path(_DEFAULT_POLICY_PATH)


def _merge_entries(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for entry in _normalize_entries(group):
            if entry not in seen:
                merged.append(entry)
                seen.add(entry)
    return merged


def _normalize_entries(entries: list[str]) -> list[str]:
    cleaned: list[str] = []
    for entry in entries:
        value = entry.strip()
        if value:
            cleaned.append(value)
    return cleaned


def _matches_company_rules(company: str, exclusions: list[str]) -> bool:
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
        elif value == normalized_company:
            return True
    return False


def _parse_nested_filters(text: str) -> tuple[list[str], list[str]]:
    company_rules: list[str] = []
    legal_entities: list[str] = []
    in_filters = False
    current_section: str | None = None
    pending_match: str | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        if indent == 0:
            in_filters = stripped == "filters:"
            current_section = None
            pending_match = None
            continue

        if not in_filters:
            continue

        if indent == 2:
            current_section = _parse_filter_section_header(stripped)
            pending_match = None
            continue

        if current_section == "excluded_companies":
            if indent == 4:
                rule_match = re.match(r"^-\s*match:\s*(exact|contains)\s*$", stripped)
                if rule_match:
                    pending_match = rule_match.group(1)
                    continue
                value_match = re.match(r"^-\s*(.+)$", stripped)
                if value_match:
                    company_rules.append(value_match.group(1).strip())
                    pending_match = None
                    continue
            if indent == 6 and pending_match is not None:
                value_line = re.match(r"^value:\s*(.+)$", stripped)
                if value_line:
                    value = unquote(value_line.group(1).strip())
                    company_rules.append(f"{pending_match}:{value}")
                    pending_match = None
                    continue

        if current_section == "excluded_legal_entities" and indent == 4:
            value_match = re.match(r"^-\s*(.+)$", stripped)
            if value_match:
                legal_entities.append(unquote(value_match.group(1).strip()))

    return _normalize_entries(company_rules), _normalize_entries(legal_entities)


def _parse_filter_section_header(value: str) -> str | None:
    if value == "excluded_companies:":
        return "excluded_companies"
    if value == "excluded_legal_entities:":
        return "excluded_legal_entities"
    return None


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
