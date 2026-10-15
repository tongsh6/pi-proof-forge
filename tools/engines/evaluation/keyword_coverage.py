"""可复现的词面覆盖；不能据此判断硬性条件已满足。"""
from __future__ import annotations

import re
from collections.abc import Sequence


def unique_terms(terms: Sequence[str]) -> list[str]:
    result: dict[str, str] = {}
    for term in terms:
        value = " ".join(term.split())
        if value:
            result.setdefault(value.casefold(), value)
    return list(result.values())


def contains_term(text: str, term: str) -> bool:
    value = " ".join(term.split()).casefold()
    if not value:
        return False
    # ASCII 技术词的边界允许紧邻中文，但不能命中其他英文技术名的一部分。
    token_chars = r"[a-z0-9_]"
    left = rf"(?<!{token_chars})" if re.match(token_chars, value[0]) else ""
    # 单个加号是常见技术栈分隔符；C 仍不能命中 C++ 或 C#。
    right = r"(?![a-z0-9_#]|\+\+)" if re.match(token_chars, value[-1]) else ""
    if value[-1] in "+#":
        right = r"(?![a-z0-9_+#])"
    return re.search(left + re.escape(value) + right, " ".join(text.split()).casefold()) is not None


def keyword_coverage(content: str, keywords: Sequence[str]) -> dict:
    body_lines = []
    target_section_level = None
    target_label = r"(?:求职意向|目标岗位|Target role)"
    for line in content.splitlines():
        plain = line.replace("**", "").replace("__", "")
        heading = re.match(r"^\s*(#{1,6})\s+(.+)", plain)
        if heading:
            level = len(heading[1])
            if target_section_level is not None and level <= target_section_level:
                target_section_level = None
            if re.fullmatch(target_label + r"\s*[:：]?", heading[2].strip(), re.I):
                target_section_level = level if target_section_level is None else min(level, target_section_level)
        if target_section_level is not None:
            continue
        if re.match(r"^\s*(?:[-*]\s*|#{1,6}\s*)?" + target_label + r"\s*[:：]", plain, re.I):
            continue
        body_lines.append(line)
    body = "\n".join(body_lines)
    terms = unique_terms(keywords)
    matched = [term for term in terms if contains_term(body, term)]
    return {"matched": matched, "missing": [term for term in terms if term not in matched],
            "ratio": len(matched) / len(terms) if terms else None}
