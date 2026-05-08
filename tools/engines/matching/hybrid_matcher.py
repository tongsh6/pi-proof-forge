"""Hybrid Matching: Rule pre-filters Top N, LLM re-ranks semantically.

Combines the speed of rule matching (<0.01s) with the semantic precision
of LLM matching (~8s). Ideal balance for production use.
"""

from __future__ import annotations

from collections.abc import Sequence

from tools.domain.models import EvidenceCard, JobProfile, MatchingReport
from tools.infra.llm.client import LLMClient

from .llm_matcher import LLMMatchingEngine
from .rule_scorer import RuleMatchingEngine


class HybridMatchingEngine:
    """Two-stage matching: Rule pre-filter → LLM semantic re-rank."""

    def __init__(self, client: LLMClient, model: str, top_n: int = 5) -> None:
        self._rule = RuleMatchingEngine()
        self._llm = LLMMatchingEngine(client, model)
        self._top_n = top_n

    def score(
        self,
        evidence_cards: Sequence[EvidenceCard],
        profile: JobProfile,
    ) -> MatchingReport:
        if not evidence_cards:
            return self._rule.score([], profile)

        # Stage 1: Rule engine scores all cards rapidly
        rule_report = self._rule.score(evidence_cards, profile)

        # Sort cards by rule score (use score_breakdown total, fallback to K-score)
        cards_with_scores: list[tuple[EvidenceCard, float]] = []
        for card in evidence_cards:
            single = self._rule.score([card], profile)
            total = single.score_breakdown.get("total", 0.0)
            cards_with_scores.append((card, total))

        cards_with_scores.sort(key=lambda x: x[1], reverse=True)

        # Stage 2: LLM re-ranks only the top N
        top_cards = [c for c, _ in cards_with_scores[: self._top_n]]

        if len(top_cards) <= 1:
            # Too few cards for meaningful LLM re-ranking, use rule result
            return rule_report

        llm_report = self._llm.score(top_cards, profile)

        # Merge: LLM-selected cards + rule gap_tasks + blended scores
        rule_breakdown = rule_report.score_breakdown
        llm_breakdown = llm_report.score_breakdown

        merged_breakdown: dict[str, float] = {}
        for key in set(list(rule_breakdown.keys()) + list(llm_breakdown.keys())):
            rv = rule_breakdown.get(key, 0.0)
            lv = llm_breakdown.get(key, 0.0)
            merged_breakdown[key] = round(rv * 0.3 + lv * 0.7, 4)

        # Use LLM's card selection but fall back to rule selection
        selected_ids = llm_report.evidence_card_ids or tuple(c.id for c in top_cards)

        # Merge gap tasks: LLM gaps are more specific, keep both
        merged_gaps = llm_report.gap_tasks or rule_report.gap_tasks

        return MatchingReport(
            job_profile_id=profile.id,
            evidence_card_ids=selected_ids,
            score_breakdown=merged_breakdown,
            gap_tasks=merged_gaps,
        )
