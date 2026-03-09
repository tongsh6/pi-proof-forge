from __future__ import annotations

from tools.domain.models import Scorecard


class ScorecardBuilder:
    def build(
        self,
        resume_version: str,
        job_profile_id: str,
        dimension_scores: dict[str, float],
    ) -> Scorecard:
        if dimension_scores:
            total = sum(dimension_scores.values()) / len(dimension_scores)
        else:
            total = 0.0
        return Scorecard(
            resume_version=resume_version,
            job_profile_id=job_profile_id,
            total_score=round(total, 4),
            dimension_scores=dimension_scores,
        )
