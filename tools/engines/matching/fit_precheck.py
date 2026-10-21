"""岗位适配预检：优先复用最近一次 Quick Run 的对位结论，否则用证据库做规则预检。

规则预检只做证据与 JD 的关键词/要求匹配，不调用模型、不产生投递或生成副作用；
它的结论是“是否值得跑一次 Quick Run”的粗筛参考，不能替代语义对位评审。
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

PROMISING_COVERAGE = 0.65
CAUTION_COVERAGE = 0.35
MATCHED_REQUIREMENT_RATIO = 0.5
MAX_TERMS = 8

RANK_BY_STATE: dict[str, int] = {
    "recommended": 0,
    "consider": 1,
    "promising": 2,
    "caution": 3,
    "hold": 4,
    "unknown": 5,
    "low": 6,
}
_ADVICE_STATE = {
    "apply": "recommended",
    "strengthen": "consider",
    "reconsider": "caution",
    "fix_facts": "hold",
}
_LATIN_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#./-]{1,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
_UNVERIFIABLE = (
    re.compile(r"\d+\s*年"),
    re.compile(r"本科|硕士|博士|研究生|学历|学位|统招|全日制"),
)
# 通用词命中不能证明岗位适配；亚洲语言按二字窗口匹配，英文按完整词边界匹配。
_STOP_TERMS = frozenset(
    {
        "经验", "能力", "熟悉", "熟练", "具备", "相关", "以上", "优先", "要求", "负责",
        "能够", "了解", "使用", "开发", "设计", "系统", "工作", "团队", "良好", "扎实",
        "理解", "掌握", "以及", "或者", "进行", "完成", "参与", "支持", "常用", "基本",
        "一定", "需要", "加分", "经历", "项目", "技术", "业务", "平台", "产品", "数据",
        "服务", "公司", "管理", "建设", "优化", "提升", "实现", "方案", "流程", "质量",
        "沟通", "学习", "背景", "知识", "独立", "长期", "问题", "方法", "文档", "语言",
        "excellent", "strong", "good", "experience", "ability", "skills", "skill",
        "knowledge", "familiar", "proficient", "with", "and", "the", "for",
        "of", "in", "to", "on", "at", "as", "or", "by", "is", "are", "be",
        "an", "a", "from", "that", "this", "will", "can", "you", "we",
    }
)


def _normalize(text: object) -> str:
    return " ".join(str(text or "").casefold().split())


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]


def _card_signals(card: Mapping[str, Any]) -> list[str]:
    signals: list[str] = []
    for key in ("title", "context", "role_scope"):
        value = card.get(key)
        if isinstance(value, str) and value.strip():
            signals.append(value)
    for key in ("tags", "stack", "actions", "results"):
        signals.extend(_text_list(card.get(key)))
    return signals


def build_evidence_corpus(cards: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """把已审核证据卡的文本信号合成规则预检语料。"""
    items: list[dict[str, str]] = []
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        signals = _card_signals(card)
        if not signals:
            continue
        items.append(
            {
                "id": str(card.get("id", "")),
                "text": _normalize(" ".join(signals)),
            }
        )
    return {
        "card_count": len(items),
        "cards": items,
        "text": " ".join(item["text"] for item in items),
    }


def _is_unverifiable(text: str) -> bool:
    return any(pattern.search(text) for pattern in _UNVERIFIABLE)


def _requirement_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in _LATIN_TOKEN.findall(text):
        normalized = token.casefold().rstrip(".-/")
        if len(normalized) >= 2 and normalized not in _STOP_TERMS:
            terms.append(normalized)
    for run in _CJK_RUN.findall(text):
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram not in _STOP_TERMS:
                terms.append(bigram)
    return list(dict.fromkeys(terms))


def _term_in_text(term: str, text: str) -> bool:
    if not text:
        return False
    if term.isascii():
        pattern = r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])"
        return re.search(pattern, text) is not None
    return term in text


def _requirement_match(
    text: str,
    corpus: Mapping[str, Any],
) -> tuple[float, set[str]]:
    terms = _requirement_terms(text)
    if not terms:
        needle = _normalize(text)
        matched = bool(needle) and needle in str(corpus.get("text", ""))
        return (1.0 if matched else 0.0), set()
    corpus_text = str(corpus.get("text", ""))
    matched_cards: set[str] = set()
    matched = 0
    for term in terms:
        if not _term_in_text(term, corpus_text):
            continue
        matched += 1
        for card in corpus.get("cards", []):
            if _term_in_text(term, str(card.get("text", ""))):
                matched_cards.add(str(card.get("id", "")))
    return matched / len(terms), matched_cards


def _verifiable_requirements(profile: Mapping[str, Any]) -> list[tuple[str, float]]:
    candidates: list[tuple[str, float]] = []
    candidates.extend((text, 1.0) for text in _text_list(profile.get("keywords")))
    candidates.extend((text, 1.0) for text in _text_list(profile.get("must_have")))
    candidates.extend((text, 0.5) for text in _text_list(profile.get("nice_to_have")))
    selected: dict[str, tuple[str, float]] = {}
    for text, weight in candidates:
        if len(text) < 2 or _is_unverifiable(text):
            continue
        key = text.casefold()
        existing = selected.get(key)
        if existing is None or weight > existing[1]:
            selected[key] = (text, weight)
    return list(selected.values())


def _snapshot_fit_score(snapshot: Mapping[str, Any]) -> int | None:
    """只接受语义评审 fit_score（0 也是合法显式分）；匹配总分不是对位适配分。"""
    value = snapshot.get("fit_score")
    if value is None:
        return None
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def _assessed_precheck(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    advice = _snapshot_advice(snapshot)
    recommendation = str(advice.get("recommendation", "") or "") if advice is not None else ""
    fit_state = str(snapshot.get("fit_state", "unassessed") or "unassessed")
    fit_failures = int(snapshot.get("fit_failures", 0) or 0)
    fit_score = _snapshot_fit_score(snapshot)
    if recommendation in _ADVICE_STATE:
        state = _ADVICE_STATE[recommendation]
    elif fit_state == "passed":
        state = "recommended"
    elif fit_state == "failed":
        if fit_score is None:
            state = "unknown"
        elif fit_score < 45:
            state = "low"
        elif fit_score >= 70 and fit_failures <= 2:
            state = "consider"
        elif fit_score >= 70:
            state = "caution"
        else:
            state = "caution"
    else:
        state = "unknown"
    return {
        "source": "assessed",
        "state": state,
        "rank": RANK_BY_STATE[state],
        "coverage": None,
        "matched_requirements": None,
        "total_requirements": None,
        "evidence_hits": None,
        "matched_terms": [],
        "missing_terms": [],
        "fit_state": fit_state,
        "fit_failures": fit_failures,
        "match_score": int(snapshot.get("match_score", snapshot.get("score", 0)) or 0),
        "fit_score": fit_score,
        "basis": "assessed_quick_run",
    }


def _insufficient_precheck(basis: str, corpus: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source": "insufficient",
        "state": "unknown",
        "rank": RANK_BY_STATE["unknown"],
        "coverage": None,
        "matched_requirements": 0,
        "total_requirements": 0,
        "evidence_hits": int(corpus.get("card_count", 0) or 0),
        "matched_terms": [],
        "missing_terms": [],
        "fit_state": "unassessed",
        "fit_failures": 0,
        "match_score": 0,
        "fit_score": None,
        "basis": basis,
    }


def _rule_precheck(profile: Mapping[str, Any], corpus: Mapping[str, Any]) -> dict[str, Any]:
    requirements = _verifiable_requirements(profile)
    if not requirements:
        return _insufficient_precheck("insufficient_requirements", corpus)
    if int(corpus.get("card_count", 0) or 0) <= 0:
        return _insufficient_precheck("insufficient_evidence", corpus)

    total_weight = sum(weight for _text, weight in requirements)
    weighted_ratio = 0.0
    matched_requirements = 0
    evidence_cards: set[str] = set()
    matched_terms: list[str] = []
    missing_terms: list[str] = []
    for text, weight in requirements:
        ratio, cards = _requirement_match(text, corpus)
        weighted_ratio += weight * ratio
        if ratio >= MATCHED_REQUIREMENT_RATIO:
            matched_requirements += 1
            evidence_cards.update(cards)
            matched_terms.append(text)
        else:
            missing_terms.append(text)
    coverage = weighted_ratio / total_weight if total_weight else 0.0
    if coverage >= PROMISING_COVERAGE and matched_requirements >= 1:
        state = "promising"
    elif coverage >= CAUTION_COVERAGE:
        state = "caution"
    else:
        state = "low"
    return {
        "source": "rule",
        "state": state,
        "rank": RANK_BY_STATE[state],
        "coverage": round(coverage, 4),
        "matched_requirements": matched_requirements,
        "total_requirements": len(requirements),
        "evidence_hits": len(evidence_cards),
        "matched_terms": matched_terms[:MAX_TERMS],
        "missing_terms": missing_terms[:MAX_TERMS],
        "fit_state": "unassessed",
        "fit_failures": 0,
        "match_score": 0,
        "fit_score": None,
        "basis": "rule_evidence_overlap",
    }


def _snapshot_advice(snapshot: Mapping[str, Any]) -> Mapping[str, Any] | None:
    advice = snapshot.get("advice")
    return advice if isinstance(advice, Mapping) else None


def _valid_advice(snapshot: Mapping[str, Any]) -> bool:
    advice = _snapshot_advice(snapshot)
    return advice is not None and str(advice.get("recommendation", "")) in _ADVICE_STATE


def assessment_usable(snapshot: Mapping[str, Any] | None) -> bool:
    """只有 passed、或 failed 且带语义 fit_score/投递建议的结果才可信；其余退回规则预检。

    四层报告只说明“做了对位层”，若缺语义评审（fit_score=None）且无 delivery_advice，
    无法判断适配程度，不能把匹配总分或失败条数当成 assessed 依据。
    """
    if not isinstance(snapshot, Mapping):
        return False
    fit_state = str(snapshot.get("fit_state", ""))
    if fit_state == "passed":
        return True
    if fit_state != "failed":
        return False
    return _valid_advice(snapshot) or _snapshot_fit_score(snapshot) is not None


def precheck_profile(
    profile: Mapping[str, Any],
    snapshot: Mapping[str, Any] | None,
    corpus: Mapping[str, Any],
) -> dict[str, Any]:
    """对一个岗位画像给出适配预检结论；可信的 assessed 结果优先于规则预检。"""
    if assessment_usable(snapshot):
        return _assessed_precheck(snapshot)  # type: ignore[arg-type]
    return _rule_precheck(profile, corpus)


def precheck_rank(precheck: Mapping[str, Any] | None) -> int:
    state = str((precheck or {}).get("state", "") or "unknown")
    return RANK_BY_STATE.get(state, RANK_BY_STATE["unknown"])
