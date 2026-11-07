"""匹配与评分引擎（规则实现）。

包含两部分：
1. 主链路规则报告：从岗位画像与证据卡生成可解释的 K/D/S/Q/E/R 评分报告
   （确定性、零模型调用），供 Quick Run matching 阶段与 LLM 候选预筛使用。
2. ``RuleMatchingEngine``：domain 模型适配的引擎实现，供 Agent 编排的
   策略注册表使用。

规则公式只在第 1 部分维护一份；入口层不得复制同一套打分逻辑。
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict, cast

from tools.domain.models import EvidenceCard, JobProfile, MatchingReport
from tools.infra.persistence.yaml_io import parse_simple_yaml

from .report_builder import ReportBuilder

DEFAULT_LLM_MAX_CARDS = 8


class ParsedDoc(TypedDict):
    scalars: dict[str, str]
    lists: dict[str, list[str]]


class ScoreItem(TypedDict):
    score: int
    reason: str


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def parse_end_month(time_range: str) -> tuple[int, int] | None:
    matches = cast(
        list[tuple[str, str]], re.findall(r"(20\d{2})[-/.](0[1-9]|1[0-2])", time_range)
    )
    if not matches:
        return None
    year, month = matches[-1]
    return int(year), int(month)


def months_ago(year: int, month: int, now: datetime.datetime) -> int:
    return (now.year - year) * 12 + (now.month - month)


def contains_any(text: str, terms: Sequence[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def _join_card_text(doc: ParsedDoc) -> str:
    text_parts: list[str] = []
    text_parts.extend(doc["scalars"].values())
    for items in doc["lists"].values():
        text_parts.extend(items)
    return "\n".join(text_parts)


def build_rule_report(
    job_profile_path: str | Path,
    evidence_files: Sequence[Path],
    *,
    version_id: str,
) -> str:
    """生成规则匹配报告 YAML 文本（与历史产物格式保持兼容）。"""
    now_dt = datetime.datetime.now().astimezone()
    now_iso = now_dt.isoformat(timespec="seconds")
    job_doc = parse_simple_yaml(read_text(job_profile_path))

    keywords = job_doc["lists"].get("keywords", [])
    seniority_signals = job_doc["lists"].get("seniority_signal", [])
    business_domain = job_doc["scalars"].get("business_domain", "")

    evidence_ids: list[str] = []
    card_docs: list[ParsedDoc] = []
    card_texts: list[str] = []
    latest_months_ago: int | None = None

    for card_file in evidence_files:
        card_doc = parse_simple_yaml(read_text(str(card_file)))
        evidence_ids.append(card_file.stem)
        card_docs.append(card_doc)
        card_texts.append(_join_card_text(card_doc))

        time_range = card_doc["scalars"].get("time_range", "")
        end_month = parse_end_month(time_range)
        if end_month is not None:
            diff = months_ago(end_month[0], end_month[1], now_dt)
            latest_months_ago = (
                diff if latest_months_ago is None else min(latest_months_ago, diff)
            )

    all_text = "\n\n".join(card_texts)

    covered_keywords = [kw for kw in keywords if kw.lower() in all_text.lower()]
    missing_keywords = [kw for kw in keywords if kw.lower() not in all_text.lower()]
    keyword_cov = (len(covered_keywords) / len(keywords)) if keywords else 0.0
    k_score = int(round(keyword_cov * 25))

    domain_signals_map: dict[str, list[str]] = {
        "电商": ["订单", "库存", "大促", "支付", "促销", "店铺"],
        "零售": ["门店", "库存", "促销", "会员"],
        "金融": ["风控", "交易", "清算", "合规"],
    }
    domain_signals = domain_signals_map.get(
        business_domain, [business_domain] if business_domain else []
    )
    domain_hit_count = sum(1 for token in domain_signals if token and token in all_text)
    domain_ratio = (domain_hit_count / len(domain_signals)) if domain_signals else 0.0
    d_score = int(round(domain_ratio * 15)) if business_domain else 8

    seniority_hits = 0
    for signal in seniority_signals:
        if "owner" in signal.lower() and contains_any(all_text, ["owner", "负责人"]):
            seniority_hits += 1
        elif "跨团队" in signal and contains_any(all_text, ["跨团队", "协作", "推进"]):
            seniority_hits += 1
        elif "带人" in signal and contains_any(all_text, ["带人", "管理", "mentor"]):
            seniority_hits += 1
        elif "决策" in signal and contains_any(all_text, ["决策", "取舍", "方案"]):
            seniority_hits += 1
    seniority_ratio = (
        (seniority_hits / len(seniority_signals)) if seniority_signals else 0.0
    )
    s_score = int(round(seniority_ratio * 15)) if seniority_signals else 8

    numeric_results_count = 0
    artifact_count = 0
    for doc in card_docs:
        results = doc["lists"].get("results", [])
        artifacts = doc["lists"].get("artifacts", [])
        numeric_results_count += sum(1 for item in results if re.search(r"\d", item))
        artifact_count += len(artifacts)

    q_score = min(20, numeric_results_count * 5)
    e_score = min(15, artifact_count * 3)

    if latest_months_ago is None:
        r_score = 4
    elif latest_months_ago <= 6:
        r_score = 10
    elif latest_months_ago <= 12:
        r_score = 8
    elif latest_months_ago <= 18:
        r_score = 6
    elif latest_months_ago <= 24:
        r_score = 4
    else:
        r_score = 2

    score_breakdown: dict[str, ScoreItem] = {
        "K": {
            "score": k_score,
            "reason": f"关键词覆盖 {len(covered_keywords)}/{len(keywords) if keywords else 0}",
        },
        "D": {
            "score": d_score,
            "reason": f"业务域信号命中 {domain_hit_count}/{len(domain_signals) if domain_signals else 0}",
        },
        "S": {
            "score": s_score,
            "reason": f"级别信号命中 {seniority_hits}/{len(seniority_signals) if seniority_signals else 0}",
        },
        "Q": {"score": q_score, "reason": f"量化结果条数 {numeric_results_count}"},
        "E": {"score": e_score, "reason": f"证据附件条数 {artifact_count}"},
        "R": {
            "score": r_score,
            "reason": f"最近经历距今 {latest_months_ago if latest_months_ago is not None else 'unknown'} 月",
        },
    }
    total_score = sum(item["score"] for item in score_breakdown.values())

    card_rank: list[tuple[str, int, str]] = []
    for idx, doc in enumerate(card_docs):
        card_id = evidence_ids[idx]
        card_text = card_texts[idx]
        card_keyword_hits = sum(1 for kw in keywords if kw.lower() in card_text.lower())
        card_numeric = sum(
            1 for item in doc["lists"].get("results", []) if re.search(r"\d", item)
        )
        card_artifacts = len(doc["lists"].get("artifacts", []))
        role_scope = doc["scalars"].get("role_scope", "")
        role_bonus = (
            2 if contains_any(role_scope, ["Owner", "Tech Lead", "负责人"]) else 0
        )
        card_score = (
            card_keyword_hits * 3
            + card_numeric * 2
            + min(3, card_artifacts)
            + role_bonus
        )
        card_reason = (
            f"关键词命中 {card_keyword_hits}，量化 {card_numeric}，证据 {card_artifacts}"
        )
        card_rank.append((card_id, card_score, card_reason))

    card_rank.sort(key=lambda x: x[1], reverse=True)
    top_cards = card_rank[:3]

    gaps: list[str] = []
    gap_tasks: list[str] = []
    if missing_keywords:
        gaps.append("缺少关键词覆盖: " + ", ".join(missing_keywords[:5]))
        gap_tasks.append("补充包含缺失关键词的经历卡或证据")
    if q_score < 10:
        gaps.append("量化结果不足")
        gap_tasks.append("为关键经历补充可量化结果（时延/成功率/成本）")
    if e_score < 9:
        gaps.append("证据附件不足")
        gap_tasks.append("补充 PR、监控截图、复盘文档等 artifacts")
    if s_score < 8:
        gaps.append("级别信号不足")
        gap_tasks.append("补充 Owner、跨团队推进或决策类证据")
    if d_score < 7:
        gaps.append("业务域信号偏弱")
        gap_tasks.append("补充与目标业务域直接相关的经历表述")

    if not gaps:
        gaps.append("暂无明显缺口")
        gap_tasks.append("保持当前证据完整度，按新 JD 微调关键词")

    lines = [
        f'job_profile_id: "{Path(job_profile_path).stem}"',
        "evidence_card_ids:",
    ]
    for evidence_id in evidence_ids:
        lines.append(f'  - "{evidence_id}"')

    lines.append(f"score_total: {total_score}")
    lines.append("score_breakdown:")
    for key in ["K", "D", "S", "Q", "E", "R"]:
        item = score_breakdown[key]
        lines.append(
            f'  {key}: {{ score: {item["score"]}, reason: "{item["reason"]}" }}'
        )

    lines.append("top_cards:")
    for card_id, _score, reason in top_cards:
        lines.append(f'  - id: "{card_id}"')
        lines.append(f'    reason: "{reason}"')

    lines.append("gaps:")
    for gap in gaps:
        lines.append(f'  - "{gap}"')

    lines.append("gap_tasks:")
    for task in gap_tasks:
        lines.append(f'  - "{task}"')

    lines.append(f'generated_at: "{now_iso}"')
    lines.append(f'version_id: "{version_id}"')
    return "\n".join(lines) + "\n"


def rank_cards_by_rule(
    job_profile_path: str | Path, evidence_files: Sequence[Path]
) -> list[tuple[Path, int]]:
    """按规则报告同一公式给每张卡打分（关键词命中×3 + 量化结果×2 + min(3, 附件) + 负责人加分），降序返回。"""
    job_doc = parse_simple_yaml(read_text(job_profile_path))
    keywords = [str(item) for item in job_doc["lists"].get("keywords", [])]
    ranked: list[tuple[Path, int]] = []
    for card_file in evidence_files:
        doc = parse_simple_yaml(read_text(str(card_file)))
        card_text = _join_card_text(doc).lower()
        keyword_hits = sum(1 for kw in keywords if kw.lower() in card_text)
        numeric = sum(
            1 for item in doc["lists"].get("results", []) if re.search(r"\d", item)
        )
        artifacts = len(doc["lists"].get("artifacts", []))
        role_bonus = (
            2
            if contains_any(doc["scalars"].get("role_scope", ""), ["Owner", "Tech Lead", "负责人"])
            else 0
        )
        ranked.append(
            (card_file, keyword_hits * 3 + numeric * 2 + min(3, artifacts) + role_bonus)
        )
    ranked.sort(key=lambda item: (-item[1], item[0].stem))
    return ranked


def select_llm_candidate_files(
    job_profile_path: str | Path, evidence_files: Sequence[Path], limit: int
) -> list[Path]:
    """证据池大于上限时，只把规则分最高的前 N 张交给模型；本地模型吃不下整池提示词（51 张卡 600 秒超时）。"""
    if limit <= 0 or len(evidence_files) <= limit:
        return list(evidence_files)
    return [
        card_file
        for card_file, _ in rank_cards_by_rule(job_profile_path, evidence_files)[:limit]
    ]


class RuleMatchingEngine:
    """domain 模型适配的规则引擎（供 Agent 编排策略注册表使用）。"""

    def __init__(self) -> None:
        self._builder = ReportBuilder()

    def score(
        self,
        evidence_cards: Sequence[EvidenceCard],
        profile: JobProfile,
    ) -> MatchingReport:
        if not evidence_cards:
            return self._builder.build(
                job_profile_id=profile.id,
                card_ids=(),
                score_breakdown={"K": 0.0, "Q": 0.0, "E": 0.0, "total": 0.0},
                gap_tasks=_build_gap_tasks(profile, normalized_signals=""),
            )

        keyword_hits = 0
        all_signals: list[str] = []
        card_ids: list[str] = []
        quantified_cards = 0
        artifact_cards = 0

        for card in evidence_cards:
            card_ids.append(card.id)
            all_signals.extend(card.tags)
            all_signals.extend(card.stack)
            all_signals.append(card.title)
            all_signals.extend(card.results)
            if card.results:
                quantified_cards += 1
            if card.artifacts:
                artifact_cards += 1

        normalized_signals = " ".join(all_signals).casefold()
        for keyword in profile.keywords:
            if keyword.casefold() in normalized_signals:
                keyword_hits += 1

        k_score = keyword_hits / max(len(profile.keywords), 1)
        q_score = quantified_cards / len(evidence_cards)
        e_score = artifact_cards / len(evidence_cards)
        total = (k_score * 0.5) + (q_score * 0.25) + (e_score * 0.25)

        return self._builder.build(
            job_profile_id=profile.id,
            card_ids=tuple(card_ids),
            score_breakdown={
                "K": round(k_score, 4),
                "Q": round(q_score, 4),
                "E": round(e_score, 4),
                "total": round(total, 4),
            },
            gap_tasks=_build_gap_tasks(profile, normalized_signals=normalized_signals),
        )


def _build_gap_tasks(
    profile: JobProfile, *, normalized_signals: str
) -> tuple[str, ...]:
    gap_tasks: list[str] = []
    seen_terms: set[str] = set()

    for must_have in profile.must_have:
        normalized = must_have.casefold()
        if normalized and normalized not in normalized_signals:
            gap_tasks.append(f"补充 {must_have} 相关证据")
            seen_terms.add(normalized)

    for keyword in profile.keywords:
        normalized = keyword.casefold()
        if (
            normalized
            and normalized not in normalized_signals
            and normalized not in seen_terms
        ):
            gap_tasks.append(f"补充 {keyword} 相关技术栈或经验证据")

    return tuple(gap_tasks)
