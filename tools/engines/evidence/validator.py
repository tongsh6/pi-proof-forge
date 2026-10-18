from __future__ import annotations

from tools.domain.models import EvidenceCard
from tools.errors.exceptions import EvidenceValidationError
from tools.infra.evidence_provenance import normalize_provenance


class EvidenceValidator:
    def validate(self, card: EvidenceCard) -> None:
        if not card.results:
            raise EvidenceValidationError(card.id)
        if not card.artifacts:
            raise EvidenceValidationError(card.id)
        for field, value in (("time_range", card.time_range_provenance), ("role_scope", card.role_scope_provenance)):
            if value is not None and normalize_provenance(value, field=field) is None:
                raise EvidenceValidationError(card.id)
