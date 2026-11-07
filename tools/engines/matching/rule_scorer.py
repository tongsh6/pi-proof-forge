"""匹配与评分引擎（规则实现）。

唯一规则公式在此维护：
- ``score_rule_payload``：对岗位画像与证据卡做 K/D/S/Q/E/R 可解释评分，返回结构化
  结果（分项/总分/top 卡/缺口）。Quick Run 的规则报告、CLI 与 Agent 编排的
  ``RuleMatchingEngine`` 共用同一实现。
- ``build_rule_report``：把评分结果渲染为匹配报告 YAML 文本（历史产物格式）；
- ``rank_cards_by_rule`` / ``select_llm_candidate_files``：语义评审前的规则预筛；
- ``RuleMatchingEngine``：domain 模型适配，供 Agent 编排的策略注册表使用。
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping, Sequence
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


class RulePayload(TypedDict):
    score_total: int
    score_breakdown: dict[str, ScoreItem]
    evidence_card_ids: list[str]
    top_cards: list[dict[str, object]]
    gaps: list[str]
    gap_tasks: list[str]
    metrics: dict[str, float]
    generated_at: str


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


def score_rule_payload(
    *,
    job_scalars: Mapping[str, str],
    job_lists: Mapping[str, Sequence[str]],
    cards: Sequence[Mapping[str, object]],
    now: datetime.datetime | None = None,
) -> RulePayload:
    """对岗位画像与证据卡做可解释规则评分。

    ``cards`` 每项结构：``{"id": str, "scalars": Mapping[str,str], "lists": Mapping[str, Sequence[str]]}``。
    返回分项得分、总分（0-100 整数）、top 卡与缺口；不写文件、不调用模型。
    """
    now_dt = now or datetime.datetime.now().astimezone()
    keywords = [str(item) for item in job_lists.get("keywords", [])]
    seniority_signals = [str(item) for item in job_lists.get("seniority_signal", [])]
    business_domain = str(job_scalars.get("business_domain", ""))

    evidence_ids: list[str] = []
    card_docs: list[ParsedDoc] = []
    card_texts: list[str] = []
    latest_months_ago: int | None = None

    for card in cards:
        card_id = str(card.get("id", ""))
        scalars = cast(Mapping[str, str], card.get("scalars", {}))
        lists = cast(Mapping[str, Sequence[str]], card.get("lists", {}))
        doc = ParsedDoc(
            scalars={key: str(value) for key, value in scalars.items()},
            lists={key: [str(item) for item in value] for key, value in lists.items()},
        )
        evidence_ids.append(card_id)
        card_docs.append(doc)
        card_texts.append(_join_card_text(doc))

        end_month = parse_end_month(doc["scalars"].get("time_range", ""))
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
    top_cards = [
        {"id": card_id, "score": score, "reason": reason}
        for card_id, score, reason in card_rank[:3]
    ]

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

    return RulePayload(
        score_total=total_score,
        score_breakdown=score_breakdown,
        evidence_card_ids=evidence_ids,
        top_cards=top_cards,
        gaps=gaps,
        gap_tasks=gap_tasks,
        metrics={
            "keyword_coverage": round(keyword_cov, 4),
            "domain_ratio": round(domain_ratio, 4),
            "seniority_ratio": round(seniority_ratio, 4),
        },
        generated_at=now_dt.isoformat(timespec="seconds"),
    )


def build_rule_report(
    job_profile_path: str | Path,
    evidence_files: Sequence[Path],
    *,
    version_id: str,
) -> str:
    """生成规则匹配报告 YAML 文本（与历史产物格式保持兼容）。"""
    job_doc = parse_simple_yaml(read_text(job_profile_path))
    cards: list[dict[str, object]] = []
    for card_file in evidence_files:
        card_doc = parse_simple_yaml(read_text(str(card_file)))
        cards.append(
            {"id": card_file.stem, "scalars": card_doc["scalars"], "lists": card_doc["lists"]}
        )

    payload = score_rule_payload(
        job_scalars=job_doc["scalars"],
        job_lists=job_doc["lists"],
        cards=cards,
    )
    lines = [
        f'job_profile_id: "{Path(job_profile_path).stem}"',
        "evidence_card_ids:",
    ]
    for evidence_id in payload["evidence_card_ids"]:
        lines.append(f'  - "{evidence_id}"')

    lines.append(f"score_total: {payload['score_total']}")
    lines.append("score_breakdown:")
    for key in ["K", "D", "S", "Q", "E", "R"]:
        item = payload["score_breakdown"][key]
        lines.append(
            f'  {key}: {{ score: {item["score"]}, reason: "{item["reason"]}" }}'
        )

    lines.append("top_cards:")
    for item in payload["top_cards"]:
        lines.append(f'  - id: "{item["id"]}"')
        lines.append(f'    reason: "{item["reason"]}"')

    lines.append("gaps:")
    for gap in payload["gaps"]:
        lines.append(f'  - "{gap}"')

    lines.append("gap_tasks:")
    for task in payload["gap_tasks"]:
        lines.append(f'  - "{task}"')

    lines.append(f'generated_at: "{payload["generated_at"]}"')
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
            if contains_any(
                doc["scalars"].get("role_scope", ""), ["Owner", "Tech Lead", "负责人"]
            )
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


# 分项满分：用于把真实规则分归一化为 0-1，供 Agent 门禁阈值比较。
_SCORE_MAX = {"K": 25, "D": 15, "S": 15, "Q": 20, "E": 15, "R": 10}


def _domain_card_payload(card: EvidenceCard) -> dict[str, object]:
    return {
        "id": card.id,
        "scalars": {
            "title": card.title,
            "raw_source": card.raw_source,
            "time_range": card.period,
            "context": card.context,
            "role_scope": card.role_scope,
        },
        "lists": {
            "actions": list(card.actions),
            "results": list(card.results),
            "stack": list(card.stack),
            "artifacts": list(card.artifacts),
            "tags": list(card.tags),
        },
    }


def _domain_job_payload(profile: JobProfile) -> tuple[dict[str, str], dict[str, list[str]]]:
    scalars = {
        "target_role": profile.title,
        "company": profile.company,
        "business_domain": profile.business_domain,
        "level": profile.level,
    }
    lists = {
        "keywords": list(profile.keywords),
        "seniority_signal": list(profile.seniority_signal),
        "must_have": list(profile.must_have),
        "nice_to_have": list(profile.nice_to_have),
    }
    return scalars, lists


class RuleMatchingEngine:
    """domain 模型适配：使用真实 K/D/S/Q/E/R 规则评分。"""

    def __init__(self) -> None:
        self._builder = ReportBuilder()

    def score(
        self,
        evidence_cards: Sequence[EvidenceCard],
        profile: JobProfile,
    ) -> MatchingReport:
        job_scalars, job_lists = _domain_job_payload(profile)
        payload = score_rule_payload(
            job_scalars=job_scalars,
            job_lists=job_lists,
            cards=[_domain_card_payload(card) for card in evidence_cards],
        )
        breakdown = payload["score_breakdown"]
        metrics = payload["metrics"]
        normalized = {
            key: round(breakdown[key]["score"] / _SCORE_MAX[key], 4)
            for key in _SCORE_MAX
        }
        # K 使用未四舍五入的覆盖率，避免 18.75/25 被整数分舍入成 0.76。
        normalized["K"] = metrics["keyword_coverage"]
        normalized["total"] = round(payload["score_total"] / 100, 4)

        covered_text = "\n".join(
            "\n".join(
                [
                    card.title,
                    card.context,
                    card.role_scope,
                    *card.tags,
                    *card.stack,
                    *card.results,
                ]
            )
            for card in evidence_cards
        ).casefold()
        gap_tasks: list[str] = list(payload["gap_tasks"])
        seen: set[str] = {task.casefold() for task in gap_tasks}
        for keyword in profile.keywords:
            if keyword.casefold() in covered_text:
                continue
            task = f"补充 {keyword} 相关技术栈或经验证据"
            if task.casefold() not in seen:
                gap_tasks.append(task)
                seen.add(task.casefold())
        for must_have in profile.must_have:
            if must_have.casefold() in covered_text:
                continue
            task = f"补充 {must_have} 相关证据"
            if task.casefold() not in seen:
                gap_tasks.append(task)
                seen.add(task.casefold())

        return self._builder.build(
            job_profile_id=profile.id,
            card_ids=tuple(payload["evidence_card_ids"]),
            score_breakdown=normalized,
            gap_tasks=tuple(gap_tasks),
        )
