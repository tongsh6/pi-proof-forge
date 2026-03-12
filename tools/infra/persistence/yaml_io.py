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


def _fold_block_scalar_lines(lines: list[str]) -> str:
    non_empty_lines = [line for line in lines if line.strip()]
    if non_empty_lines:
        min_indent = min(len(line) - len(line.lstrip(" ")) for line in non_empty_lines)
    else:
        min_indent = 0

    normalized: list[str] = []
    for line in lines:
        if not line.strip():
            normalized.append("")
            continue
        normalized.append(line[min_indent:].rstrip())

    paragraphs: list[str] = []
    current: list[str] = []
    for line in normalized:
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))

    return "\n".join(paragraphs)


def parse_simple_yaml(text: str) -> ParsedDoc:
    scalars: dict[str, str] = {}
    lists: dict[str, list[str]] = {}
    current_list_key: str | None = None
    lines = text.splitlines()
    index = 0

    while index < len(lines):
        raw = lines[index]
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            index += 1
            continue

        list_match = re.match(r"^\s*-\s*(.+)$", line)
        if list_match and current_list_key is not None:
            value = unquote(list_match.group(1).strip())
            lists[current_list_key].append(value)
            index += 1
            continue

        key_list_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*$", line)
        if key_list_match:
            key = key_list_match.group(1)
            current_list_key = key
            lists[key] = []
            index += 1
            continue

        key_scalar_match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.+)$", line)
        if key_scalar_match:
            key = key_scalar_match.group(1)
            raw_value = key_scalar_match.group(2).strip()
            if raw_value.startswith(">"):
                index += 1
                block_lines: list[str] = []
                while index < len(lines):
                    block_line = lines[index].rstrip()
                    if not block_line:
                        block_lines.append("")
                        index += 1
                        continue
                    if block_line[:1].isspace():
                        block_lines.append(block_line)
                        index += 1
                        continue
                    break
                value = _fold_block_scalar_lines(block_lines)
            else:
                value = unquote(raw_value)
                index += 1
            scalars[key] = value
            current_list_key = None
            continue

        index += 1

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
