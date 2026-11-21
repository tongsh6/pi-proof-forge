"""R3 优质层：量化覆盖、空话检测与首屏成果密度。"""

from __future__ import annotations

import copy
import datetime as _datetime
import re
from dataclasses import dataclass
from pathlib import Path

from tools.domain.models import QualityFailure, TierResult
from tools.domain.quality_text import matches_fact_occurrence, render_fact_text
from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.engines.evaluation.llm_judge import resume_lines
from tools.infra.persistence.yaml_io import parse_simple_yaml

from .common import *


def _has_verifiable_quant(body: str, results: list[dict]) -> bool:
    # 完整结果与实测命题来自同一已核原行，不按数字词形重新判定测量发生性。
    from tools.domain.quality_text import compact

    normalized = compact(body)
    return any(
        row.get("result_review", {}).get("outcome") == "established"
        and isinstance(quote := row["result_review"].get("measurement_quote"), str) and quote
        and compact(str(row["value"])) in normalized
        and quote in row["value"] and quote in row["source"]["quote"]
        for row in results
    )


def evaluate_strong(
    *,
    resume: str,
    cards: dict[str, dict],
    trace: dict,
    config: QualityConfig,
    judgments: dict | None = None,
) -> TierResult:
    thresholds = config.thresholds["strong"]
    bullets, _marker = _bullet_rows(resume)
    trace_result = inspect_bullet_trace(resume, trace)
    verified_rows = {int(row["number"]): row for row in trace_result["bullets"]}
    experience = [bullet for bullet in bullets if bullet["section"] in _ENTRY_SECTIONS]
    failures: list[QualityFailure] = []
    if not experience:
        failures.append(_failure("R3.2", "bullets", "正文没有任何经历 bullet，无法判断表达质量"))
        quant_total = quant_first = 0.0
    else:
        quant_flags: list[bool] = []
        verified_results_by_bullet: dict[int, list[dict]] = {}
        for bullet in experience:
            number = int(bullet["number"])
            row = verified_rows.get(number, {})
            # 只有此行实际采用的 results Fact 能证明成果，不能借同卡其他结果取分。
            pool: list[dict] = []
            if trace.get("occurrence_lineage_version") == 1 and row.get("verified"):
                for source in row.get("sources", []):
                    if source.get("source_kind") != "evidence" or source.get("field") != "results":
                        continue
                    evidence_id = source.get("evidence_id", "")
                    card = cards.get(evidence_id, {})
                    stored_results = card.get("results", []) or []
                    reviewed = (card.get("result_reviews") or {}).get(source.get("fact_id"), {})
                    if (matches_fact_occurrence(evidence_id, "results", stored_results, source)
                            and reviewed.get("field") == "results"
                            and source.get("fact_id") == f"{evidence_id}:results:{reviewed.get('index')}"
                            and render_fact_text(reviewed.get("value", "")) == source["text"]
                            and reviewed.get("result_review", {}).get("outcome") == "established"):
                        pool.append(reviewed)
            verified_results_by_bullet[number] = pool
            quant_flags.append(_has_verifiable_quant(str(bullet["body"]), pool))
        quant_total = sum(quant_flags) / len(quant_flags)
        first_flags = [
            flag for bullet, flag in zip(experience, quant_flags) if bullet["first_screen"]
        ]
        quant_first = sum(first_flags) / len(first_flags) if first_flags else 0.0
        if quant_first < float(thresholds["quant_first_screen_min_ratio"]):
            failures.append(
                _failure(
                    "R3.2",
                    "首屏量化",
                    f"首屏可验证量化比例 {quant_first:.2f} 低于 {thresholds['quant_first_screen_min_ratio']}",
                )
            )
        if quant_total < float(thresholds["quant_total_min_ratio"]):
            failures.append(
                _failure(
                    "R3.2",
                    "全文量化",
                    f"全文可验证量化比例 {quant_total:.2f} 低于 {thresholds['quant_total_min_ratio']}",
                )
            )
    filler_hits: list[tuple[str, str]] = []
    for bullet in experience:
        for term in config.filler_terms:
            if term.casefold() in str(bullet["body"]).casefold():
                filler_hits.append((f"bullet#{bullet['number']}", term))
                break
    if len(filler_hits) > int(thresholds["filler_max_hits"]):
        for target, term in filler_hits[:5]:
            failures.append(_failure("R3.3", target, f"出现空话词：{term}"))
    normalized: dict[str, list[int]] = {}
    for bullet in experience:
        key = re.sub(r"[\s:：·、|*“”\"']", "", str(bullet["body"]))
        normalized.setdefault(key, []).append(int(bullet["number"]))
    for key, numbers in normalized.items():
        if key and len(numbers) > 1:
            failures.append(
                _failure("R3.4", "、".join(f"bullet#{number}" for number in numbers), "同一成果在正文重复出现")
            )
    casing: dict[str, set[str]] = {}
    for bullet in experience:
        # 只统计独立词：代码标识符内部（APPLY_RULE、repair-service-manager、
        # RepairOrderQuery）的片段不算术语大小写不一致。
        for match in re.finditer(
            r"(?<![A-Za-z0-9_\-./])([A-Za-z][A-Za-z0-9+#.]{2,})(?![A-Za-z0-9_\-/])",
            str(bullet["body"]),
        ):
            token = match.group(1)
            casing.setdefault(token.casefold(), set()).add(token)
    for variants in casing.values():
        if len(variants) > 1:
            failures.append(_failure("R3.6", "术语大小写", "同一术语大小写不一致：" + " / ".join(sorted(variants))))
    # R3.1 三段判定：每个经历 bullet 必须有带引用的场景/动作/结果判定，缺失按失败处理。
    if isinstance(judgments, dict) and "r3_1" in (judgments.get("judged_sections") or []):
        judged = {
            int(item["bullet"]): item
            for item in judgments.get("r3_1", []) or []
            if isinstance(item, dict) and isinstance(item.get("bullet"), int)
        }
        for bullet in experience:
            item = judged.get(int(bullet["number"]))
            if item is None:
                failures.append(_failure("R3.1", f"bullet#{bullet['number']}", "缺少带引用的三段判定"))
                continue
            # 与 R3.2 共用同一现行结果核定；独立 judge 的 True 不能洗白缺失证明。
            item = {**item, "result": bool(verified_results_by_bullet.get(int(bullet["number"])))}
            missing = [label for label, key in (("场景", "scene"), ("动作", "action"), ("结果", "result")) if not item.get(key)]
            if missing:
                failures.append(
                    _failure("R3.1", f"bullet#{bullet['number']}", "缺少" + "、".join(missing) + "段")
                )
    # R3.5 摘要判定：<=3 行、角色/规模匹配、无通用形容词。
    if isinstance(judgments, dict) and "r3_5" in (judgments.get("judged_sections") or []):
        summary_judgment = judgments.get("r3_5") or {}
        max_lines = int(thresholds.get("summary_max_lines", 3))
        lines = summary_judgment.get("summary_lines")
        if isinstance(lines, int) and lines > max_lines:
            failures.append(_failure("R3.5", "摘要", f"定位摘要 {lines} 行，超过 {max_lines} 行"))
        if summary_judgment.get("role_scale_match") is False:
            failures.append(_failure("R3.5", "摘要", "定位摘要未说明做什么、在什么规模/领域与岗位匹配点"))
        adjectives = summary_judgment.get("generic_adjectives") or []
        if adjectives:
            failures.append(_failure("R3.5", "摘要", "定位摘要含通用形容词：" + "、".join(str(item) for item in adjectives[:5])))
    metrics = {
        "quant_first_screen": round(quant_first, 4),
        "quant_total": round(quant_total, 4),
        "filler_hits": len(filler_hits),
        "duplicate_bullets": sum(len(numbers) - 1 for numbers in normalized.values() if len(numbers) > 1),
        "judged_r3_1": isinstance(judgments, dict) and "r3_1" in (judgments.get("judged_sections") or []),
        "judged_r3_5": isinstance(judgments, dict) and "r3_5" in (judgments.get("judged_sections") or []),
    }
    return TierResult(passed=not failures, failures=tuple(failures), metrics=metrics)
