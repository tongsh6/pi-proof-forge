from __future__ import annotations

from collections.abc import Sequence

from tools.domain.models import EvidenceCard, JobProfile, MatchingReport

from .report_builder import ReportBuilder


class RuleMatchingEngine:
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
                gap_tasks=tuple(f"补充 {kw} 相关证据" for kw in profile.must_have),
            )

        keyword_hits = 0
        all_signals: list[str] = []
        card_ids: list[str] = []
        quantified_cards = 0
        artifact_cards = 0

        for card in evidence_cards:
            card_ids.append(card.id)
            all_signals.extend(card.tags)
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

        gap_tasks = tuple(
            f"补充 {must_have} 相关证据"
            for must_have in profile.must_have
            if must_have.casefold() not in normalized_signals
        )

        return self._builder.build(
            job_profile_id=profile.id,
            card_ids=tuple(card_ids),
            score_breakdown={
                "K": round(k_score, 4),
                "Q": round(q_score, 4),
                "E": round(e_score, 4),
                "total": round(total, 4),
            },
            gap_tasks=gap_tasks,
        )
