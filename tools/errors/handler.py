from __future__ import annotations

from tools.errors.exceptions import (
    EvidenceValidationError,
    FabricationGuardError,
    PiProofError,
)


def route_error(exc: Exception) -> str:
    if isinstance(exc, (EvidenceValidationError, FabricationGuardError, PiProofError)):
        return "terminate_run"
    return "unknown_error"
