from __future__ import annotations

from tools.errors.exceptions import (
    EvidenceValidationError,
    FabricationGuardError,
    PiProofError,
    PolicyError,
)


def route_error(exc: Exception) -> str:
    """Route an exception to its handling strategy.

    - terminate_run: unrecoverable business rule violation (evidence, fabrication, policy)
    - unknown_error: unexpected error, should be logged and run terminated
    """
    if isinstance(exc, (EvidenceValidationError, FabricationGuardError, PiProofError, PolicyError)):
        return "terminate_run"
    return "unknown_error"
