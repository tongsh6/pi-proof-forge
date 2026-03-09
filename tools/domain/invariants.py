from __future__ import annotations

from collections.abc import Sequence

from tools.domain.models import EvidenceCard
from tools.errors.exceptions import FabricationGuardError


def check_evidence_eligible(card: EvidenceCard) -> bool:
    return len(card.results) > 0 and len(card.artifacts) > 0


def check_no_fabrication(content: str, evidence_cards: Sequence[EvidenceCard]) -> None:
    if not evidence_cards:
        raise FabricationGuardError(content)

    source_tokens: set[str] = set()
    for card in evidence_cards:
        for result in card.results:
            token = result.strip()
            if token:
                source_tokens.add(token)
        for artifact in card.artifacts:
            token = artifact.strip()
            if token:
                source_tokens.add(token)

    if not source_tokens:
        raise FabricationGuardError(content)

    for token in source_tokens:
        if token in content:
            return

    raise FabricationGuardError(content)
