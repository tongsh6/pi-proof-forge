from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceCard:
    id: str
    title: str
    raw_source: str
    results: tuple[str, ...]
    artifacts: tuple[str, ...]
    tags: tuple[str, ...] = ()
    period: str = ""
    context: str = ""

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
class Scorecard:
    resume_version: str
    job_profile_id: str
    total_score: float
    dimension_scores: dict[str, float]


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
