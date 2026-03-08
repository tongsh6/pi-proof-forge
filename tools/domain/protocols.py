from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable

from tools.domain.models import (
    EvidenceCard,
    JobProfile,
    MatchingReport,
    ResumeOutput,
    Scorecard,
)
from tools.domain.result import Result
from tools.domain.value_objects import (
    ChannelFailure,
    DeliveryResult,
    GateDecision,
    GateFailure,
)


@dataclass(frozen=True)
class StageResult:
    success: bool
    data: Any
    errors: tuple[Any, ...] = ()


@runtime_checkable
class EvidenceExtractor(Protocol):
    def extract(self, raw_material: Any) -> EvidenceCard: ...


@runtime_checkable
class MatchingEngine(Protocol):
    def score(
        self, evidence_cards: Sequence[EvidenceCard], profile: JobProfile
    ) -> MatchingReport: ...


@runtime_checkable
class GenerationEngine(Protocol):
    def generate(
        self,
        report: MatchingReport,
        cards: Sequence[EvidenceCard],
        version: str,
        config: Any,
    ) -> ResumeOutput: ...


@runtime_checkable
class EvaluationEngine(Protocol):
    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard: ...


@runtime_checkable
class GateEngine(Protocol):
    def evaluate(self, request: Any) -> Result[GateDecision, GateFailure]: ...


@runtime_checkable
class DeliveryChannel(Protocol):
    channel_id: str

    def deliver(self, request: Any) -> Result[DeliveryResult, ChannelFailure]: ...


@runtime_checkable
class RunStore(Protocol):
    def append_event(self, event: Any) -> None: ...

    def load_events(self, run_id: str) -> Sequence[Any]: ...


@runtime_checkable
class Stage(Protocol):
    name: str

    def execute(self, context: Any) -> StageResult: ...
