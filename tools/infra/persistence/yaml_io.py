from __future__ import annotations

import re
from typing import TypedDict


class ParsedDoc(TypedDict):
    scalars: dict[str, str]
    lists: dict[str, list[str]]


def unquote(value: str) -> str:
    if len(value) >= 2 and (
        (value.startswith('"') and value.endswith('"'))
        or (value.startswith("'") and value.endswith("'"))
    ):
        return value[1:-1]
    return value


def parse_simple_yaml(text: str) -> ParsedDoc:
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    current_list_key: str | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        list_match = re.match(r"^\s*-\s*(.+)$", line)
        if list_match and current_list_key is not None:
            value = unquote(list_match.group(1).strip())
            lists[current_list_key].append(value)
            continue

        key_list_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*$", line)
        if key_list_match:
            key = key_list_match.group(1)
            current_list_key = key
            lists[key] = []
            continue

        key_scalar_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.+)$", line)
        if key_scalar_match:
            key = key_scalar_match.group(1)
            value = unquote(key_scalar_match.group(2).strip())
            scalars[key] = value
            current_list_key = None

    return {"scalars": scalars, "lists": lists}


def dump_yaml(
    scalars: dict[str, str],
    lists: dict[str, list[str]],
) -> str:
    lines: list[str] = []
    for key, value in scalars.items():
        lines.append(f'{key}: "{value}"')
    for key, items in lists.items():
        lines.append(f"{key}:")
        for item in items:
            lines.append(f'  - "{item}"')
    return "\n".join(lines) + "\n"
