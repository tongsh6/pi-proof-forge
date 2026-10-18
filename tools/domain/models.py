from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceCard:
    id: str
    title: str
    raw_source: str
    results: tuple[str, ...]
    artifacts: tuple[str, ...]
    tags: tuple[str, ...] = ()
    stack: tuple[str, ...] = ()
    period: str = ""
    context: str = ""
    role_scope: str = ""
    time_range_provenance: dict | None = None
    role_scope_provenance: dict | None = None

    def is_eligible(self) -> bool:
        return len(self.results) > 0 and len(self.artifacts) > 0


@dataclass(frozen=True)
class JobProfile:
    id: str
    title: str
    keywords: tuple[str, ...]
    level: str
    tone: str = ""
    must_have: tuple[str, ...] = ()
    nice_to_have: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatchingReport:
    job_profile_id: str
    evidence_card_ids: tuple[str, ...]
    score_breakdown: dict[str, float]
    gap_tasks: tuple[str, ...]


@dataclass(frozen=True)
class ResumeOutput:
    version: str
    job_profile_id: str
    content: str
    format: str


@dataclass(frozen=True)
class QualityFailure:
    """单条质量判据缺口：必须能定位到具体 bullet 或证据卡。"""

    rule: str
    target: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"rule": self.rule, "target": self.target, "reason": self.reason}


@dataclass(frozen=True)
class TierResult:
    """质量报告单层结果；metrics/matrix/highlights 按层取用。"""

    passed: bool
    failures: tuple[QualityFailure, ...] = ()
    metrics: dict[str, object] = field(default_factory=dict)
    matrix: tuple[dict[str, object], ...] = ()
    highlights: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "failures": [failure.to_dict() for failure in self.failures],
            "metrics": self.metrics,
            "matrix": list(self.matrix),
            "highlights": list(self.highlights),
        }


@dataclass(frozen=True)
class Scorecard:
    resume_version: str
    job_profile_id: str
    total_score: float
    dimension_scores: dict[str, float]
    quality_report: dict[str, object] | None = None


# --- GUI entities ---


@dataclass(frozen=True)
class PersonalProfile:
    name: str
    phone: str
    email: str
    city: str
    current_title: str


@dataclass(frozen=True)
class JobLead:
    id: str
    source: str
    url: str
    company: str
    title: str
    status: str
    favorited: bool


@dataclass(frozen=True)
class UploadedResume:
    id: str
    filename: str
    language: str
    uploaded_at: str
    source_channel: str


@dataclass(frozen=True)
class ActivityLog:
    type: str
    timestamp: str
    description: str
    resource_id: str
