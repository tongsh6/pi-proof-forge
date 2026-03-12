from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.persistence.yaml_io import parse_simple_yaml

_PROFILE_PATH = Path("personal_profile.yaml")
_PROFILE_FIELDS = ("name", "phone", "email", "city", "current_position")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _load_profile() -> dict[str, str]:
    if not _PROFILE_PATH.exists():
        return {}
    doc = parse_simple_yaml(_PROFILE_PATH.read_text(encoding="utf-8"))
    return dict(doc["scalars"])


def _write_profile(fields: dict[str, str]) -> None:
    lines = [f"{field}: {_quote(fields.get(field, ''))}" for field in _PROFILE_FIELDS]
    lines.append(f"updated_at: {_quote(fields.get('updated_at', ''))}")
    _PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROFILE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _profile_payload(fields: dict[str, str]) -> dict[str, Any]:
    missing_fields = [
        field for field in _PROFILE_FIELDS if not fields.get(field, "").strip()
    ]
    completeness = int(
        ((len(_PROFILE_FIELDS) - len(missing_fields)) / len(_PROFILE_FIELDS)) * 100
    )
    return {
        "name": fields.get("name", ""),
        "phone": fields.get("phone", ""),
        "email": fields.get("email", ""),
        "city": fields.get("city", ""),
        "current_position": fields.get("current_position", ""),
        "completeness": completeness,
        "missing_fields": missing_fields,
        "updated_at": fields.get("updated_at", ""),
    }


def handle_profile_get(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    profile = _profile_payload(_load_profile())
    return {
        "meta": {"correlation_id": correlation_id},
        "profile": profile,
    }


def handle_profile_update(params: dict[str, Any]) -> dict[str, Any]:
    correlation_id = params["meta"]["correlation_id"]
    patch = params.get("patch", {})
    if not isinstance(patch, dict):
        raise ValueError("patch must be an object")

    unsupported_fields = set(patch) - set(_PROFILE_FIELDS)
    if unsupported_fields:
        unsupported = ", ".join(sorted(unsupported_fields))
        raise ValueError(f"unsupported profile fields: {unsupported}")

    if "email" in patch:
        email = str(patch["email"]).strip()
        if email and not _EMAIL_PATTERN.fullmatch(email):
            raise ValueError("email must be a valid email address")

    fields = _load_profile()
    for key in _PROFILE_FIELDS:
        if key in patch:
            fields[key] = str(patch[key])

    updated_at = _utcnow_iso()
    fields["updated_at"] = updated_at
    _write_profile(fields)
    return {
        "meta": {"correlation_id": correlation_id},
        "saved": True,
        "updated_at": updated_at,
    }
