"""R4 突出层：突出点提名与置信门槛。"""

from __future__ import annotations

import copy
import datetime as _datetime
import re
from dataclasses import dataclass
from pathlib import Path

from tools.domain.models import QualityFailure, TierResult
from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.engines.evaluation.llm_judge import resume_lines
from tools.infra.persistence.yaml_io import parse_simple_yaml

from .common import *


def _candidate_highlights(
    resume: str,
    candidates: list[dict] | None,
    decisions: dict | None,
) -> list[dict[str, object]]:
    bullets, _marker = _bullet_rows(resume)
    by_number = {f"bullet#{int(bullet['number'])}": bullet for bullet in bullets}
    rejected = {str(item) for item in ((decisions or {}).get("rejected") or [])}
    selected = {str(item) for item in ((decisions or {}).get("selected") or [])}
    items: list[dict[str, object]] = []
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        highlight_id = str(candidate.get("highlight_id") or "")
        bullet = candidate.get("bullet")
        if not highlight_id or not isinstance(bullet, int) or highlight_id in rejected:
            continue
        ref = f"bullet#{bullet}"
        row = by_number.get(ref)
        exceeds = [str(value) for value in (candidate.get("exceeds") or [])]
        items.append(
            {
                "highlight_id": highlight_id,
                "bullet_ref": ref,
                "jd_item_id": str(candidate.get("jd_item_id", "")),
                "exceeds": "、".join(exceeds),
                "level": str(candidate.get("level", "")),
                "reason": str(candidate.get("reason", "")),
                "citations": list(candidate.get("citations") or []),
                "first_screen": bool(row["first_screen"]) if row else False,
                "selected_by_user": highlight_id in selected,
            }
        )
    items.sort(
        key=lambda item: (
            0 if item["selected_by_user"] else 1,
            0 if item["first_screen"] else 1,
            -len(str(item["exceeds"]).split("、")) if item["exceeds"] else 0,
            item["bullet_ref"],
        )
    )
    return items


def evaluate_distinct(
    *,
    resume: str = "",
    highlights: list[dict] | None = None,
    candidates: list[dict] | None = None,
    decisions: dict | None = None,
    config: QualityConfig,
) -> TierResult:
    thresholds = config.thresholds["distinct"]
    if candidates is not None:
        items = _candidate_highlights(resume, candidates, decisions)
    else:
        items = [item for item in (highlights or []) if isinstance(item, dict)]
        if decisions:
            rejected = {str(value) for value in (decisions.get("rejected") or [])}
            items = [item for item in items if str(item.get("highlight_id") or "") not in rejected]
    failures: list[QualityFailure] = []
    minimum = int(thresholds["min_highlights"])
    maximum = int(thresholds["max_highlights"])
    if candidates is not None:
        # B4 设计要求突出点置于首屏；只有首屏候选可以被选入正文突出点。
        eligible = [
            item for item in items
            if item.get("first_screen") is not False or item.get("selected_by_user")
        ]
        if len(eligible) < minimum:
            failures.append(_failure("R4.2", "highlights", "无合格的首屏突出点"))
        chosen = eligible[:maximum]
    else:
        if len(items) < minimum:
            failures.append(_failure("R4.2", "highlights", "无合格突出点（LLM 提名尚未运行或全部被否决）"))
        chosen = items[:maximum] if len(items) > maximum else items
    if len(items) > maximum and candidates is None:
        failures.append(
            _failure("R4.2", "highlights", f"突出点 {len(items)} 条，超过 {maximum} 条上限")
        )
    for index, item in enumerate(chosen, start=1):
        level = str(item.get("level", "L1"))
        if level not in {"L1", "L2"}:
            failures.append(
                _failure("R4.3", f"突出点#{index}", f"证据等级 {level} 不能作为突出点")
            )
        if item.get("first_screen") is False:
            failures.append(_failure("R4.2", f"突出点#{index}", "突出点未置于首屏"))
    rejected_ids = {str(value) for value in ((decisions or {}).get("rejected") or [])}
    candidate_details = [
        {
            "highlight_id": item.get("highlight_id", ""),
            "bullet_ref": item.get("bullet_ref", ""),
            "jd_item_id": item.get("jd_item_id", ""),
            "exceeds": item.get("exceeds", ""),
            "level": item.get("level", ""),
            "reason": item.get("reason", ""),
            "first_screen": item.get("first_screen"),
            "rejected": str(item.get("highlight_id", "")) in rejected_ids,
        }
        for item in (items if candidates is not None else [])
    ]
    metrics = {
        "count": len(chosen),
        "candidate_count": len(candidates or []) if candidates is not None else len(items),
        "levels": sorted({str(item.get("level", "L1")) for item in chosen}),
        "rejected": len((decisions or {}).get("rejected") or []),
        "selected": len((decisions or {}).get("selected") or []),
        "candidates": candidate_details,
    }
    return TierResult(passed=not failures, failures=tuple(failures), metrics=metrics, highlights=tuple(chosen))


_GAP_KIND_LABELS = {"evidence_missing": "证据缺口", "not_expressed": "未表达"}
_FACT_RULES = frozenset({"R1.1", "R1.2", "R1.7"})
_RECOMMENDATION_LABELS = {
    "apply": "建议投递",
    "strengthen": "建议补强后投递",
    "reconsider": "建议先补证据或更换更匹配目标",
    "fix_facts": "先核对事实与硬性条件",
}
_RECOMMENDATION_SUMMARIES = {
    "apply": "建议投递：合格层与对位层通过，事实追溯与岗位支撑已覆盖。",
    "strengthen": "建议补强后投递：仍有可在生成或内容取舍阶段改进的缺口。",
    "reconsider": "建议先补证据或更换更匹配目标：核心职责证据支撑不足。",
    "fix_facts": "先核对事实与硬性条件：存在不能靠重新生成消除的缺口。",
}
