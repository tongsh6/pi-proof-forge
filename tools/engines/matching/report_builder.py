from __future__ import annotations

from tools.domain.models import MatchingReport


class ReportBuilder:
    def build(
        self,
        job_profile_id: str,
        card_ids: tuple[str, ...],
        score_breakdown: dict[str, float],
        gap_tasks: tuple[str, ...],
    ) -> MatchingReport:
        return MatchingReport(
            job_profile_id=job_profile_id,
            evidence_card_ids=card_ids,
            score_breakdown=score_breakdown,
            gap_tasks=gap_tasks,
        )
