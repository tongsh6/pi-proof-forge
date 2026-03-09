from __future__ import annotations

from tools.domain.models import EvidenceCard
from tools.errors.exceptions import EvidenceValidationError


class EvidenceValidator:
    def validate(self, card: EvidenceCard) -> None:
        if not card.results:
            raise EvidenceValidationError(card.id)
        if not card.artifacts:
            raise EvidenceValidationError(card.id)
