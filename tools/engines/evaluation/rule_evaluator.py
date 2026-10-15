from __future__ import annotations

import re

from tools.domain.models import JobProfile, ResumeOutput, Scorecard
from .keyword_coverage import keyword_coverage


class RuleEvaluationEngine:
    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard:
        content = resume.content
        coverage = keyword_coverage(content, profile.keywords)["ratio"]
        coverage = 0.5 if coverage is None else coverage

        quantified_bullets = len(re.findall(r"\d", content))
        total_lines = max(
            len([line for line in content.splitlines() if line.strip()]), 1
        )
        quant = min(quantified_bullets / total_lines, 1.0)

        clarity = 1.0 if len(content) <= 4000 else 0.7
        length = 1.0 if 150 <= len(content) <= 4000 else 0.6
        citation = 1.0 if "-" in content else 0.5

        total = (
            (coverage * 0.35)
            + (quant * 0.2)
            + (clarity * 0.2)
            + (length * 0.15)
            + (citation * 0.1)
        )

        return Scorecard(
            resume_version=resume.version,
            job_profile_id=profile.id,
            total_score=round(total, 4),
            dimension_scores={
                "coverage": round(coverage, 4),
                "quant": round(quant, 4),
                "clarity": round(clarity, 4),
                "length": round(length, 4),
                "citation": round(citation, 4),
            },
        )
