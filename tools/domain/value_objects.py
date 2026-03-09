from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering


@total_ordering
@dataclass(frozen=True)
class Score:
    value: float

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Score):
            return NotImplemented
        return self.value < other.value


@dataclass(frozen=True)
class GapTask:
    description: str
    priority: str
    source: str


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    direction: str
    company: str
    job_url: str
    confidence: float
    source: str
    merged_sources: tuple[str, ...]
    legal_entity: str = ""


@dataclass(frozen=True)
class GateDecision:
    passed: bool
    pass_count: int
    details: str


@dataclass(frozen=True)
class GateFailure:
    reason: str
    details: str


@dataclass(frozen=True)
class ChannelFailure:
    channel_id: str
    reason: str
    details: str


@dataclass(frozen=True)
class DeliveryResult:
    channel_id: str
    success: bool
    submission_id: str
    message: str


# --- GUI value objects ---


@dataclass(frozen=True)
class MatchTrendPoint:
    date: str
    score: float
    job_profile_id: str


@dataclass(frozen=True)
class GapItem:
    description: str
    category: str
    severity: str


@dataclass(frozen=True)
class SubmissionStep:
    step_name: str
    status: str
    timestamp: str


@dataclass(frozen=True)
class ScreenshotRef:
    resource_id: str
    step_name: str
    mime_type: str


# --- REVIEW (manual delivery mode) ---


@dataclass(frozen=True)
class ReviewCandidate:
    """待审批投递候选；design.md / tasks A2。"""

    job_lead_id: str
    company: str
    position: str
    matching_score: float
    evaluation_score: float
    round_index: int
    resume_version: str
    job_url: str = ""
    score_breakdown: tuple[tuple[str, float], ...] = ()
    gap_tasks: tuple[GapTask, ...] = ()
    gate_decision: GateDecision | None = None


@dataclass(frozen=True)
class ReviewDecision:
    """用户审批结果；design.md / tasks A2。"""

    job_lead_id: str
    action: str  # approve | reject | skip | skip_all
    decided_by: str
    decided_at: str  # ISO 8601
    note: str = ""
