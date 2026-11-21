"""Pure, conservative binding of explicit numbered JD sections to grounded clauses."""
from __future__ import annotations

import hashlib
import re

_HEADING = re.compile(r"^\s*\d+[.、]\s*核心技术栈硬性要求\s*[:：]?\s*$")
_CHILD = re.compile(r"^\s*(?:（(?P<full>[1-9]\d*)）|\((?P<ascii>[1-9]\d*)\))\s*(?P<content>\S.*)$")
_PEER = re.compile(r"^\s*\d+[.、)]\s*\S")
_UPPER = re.compile(r"^\s*(?:#{1,6}\s+\S.*|(?:岗位职责|工作职责|任职要求|任职资格|职位要求|加分项|加分经历|Responsibilities|Requirements|Qualifications)\s*[:：]?)\s*$", re.I)


def bind_explicit_requirement_sections(body, sources):
    """Return annotations only. No inferred skill type, fit score or promotion of nice-to-have."""
    if not isinstance(body, str) or not isinstance(sources, (list, tuple)):
        return []
    lines = []
    offset = 0
    for raw in body.splitlines(keepends=True):
        text = raw.rstrip("\r\n")
        lines.append((text, offset, offset + len(text)))
        offset += len(raw)
    headings = [i for i, (line, _, _) in enumerate(lines) if _HEADING.fullmatch(line)]
    if len(headings) != 1:
        return []
    heading_index = headings[0]
    heading_line, heading_start, heading_end = lines[heading_index]
    children = []
    style = None
    terminated = False
    for line, start, end in lines[heading_index + 1:]:
        if _PEER.match(line) or _UPPER.fullmatch(line):
            terminated = True
            break
        child = _CHILD.fullmatch(line)
        if not child:
            return []  # Blank paragraphs, wrapping and unknown hierarchy are not guessed.
        current_style = "full" if child.group("full") is not None else "ascii"
        number = int(child.group(current_style))
        if number != len(children) + 1 or (style is not None and current_style != style):
            return []
        style = current_style
        children.append({"quote":line, "start":start, "end":end,
                         "content_start":start + child.start("content")})
    if not terminated or not children:
        return []
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    out = []
    for source in sources:
        if not isinstance(source, dict) or source.get("kind") != "must_have":
            continue
        index, quote, start, end = (source.get(key) for key in ("index", "quote", "start", "end"))
        if (type(index) is not int or index < 0 or not isinstance(quote, str) or not quote.strip()
                or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= len(body) or body[start:end] != quote
                or body.find(quote) != start or body.find(quote, start + 1) != -1
                or sum(isinstance(s, dict) and s.get("kind") == "must_have" and s.get("index") == index for s in sources) != 1):
            continue
        child = next((c for c in children if c["content_start"] <= start < end <= c["end"]), None)
        if child is None:
            continue
        out.append({"kind":"must_have", "index":index, "quote":quote, "start":start, "end":end,
                    "source_jd_sha256":digest, "binding_scope":"explicit_numbered_section_only",
                    "heading":{"quote":heading_line, "start":heading_start, "end":heading_end},
                    "child":{key:child[key] for key in ("quote", "start", "end")}})
    return out
