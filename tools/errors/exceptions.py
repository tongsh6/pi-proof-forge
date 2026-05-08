"""Unrecoverable exceptions — re-exported from domain layer.

Domain exceptions (FabricationGuardError, EvidenceValidationError) are
defined in domain/invariants.py where the business rules live. This
module re-exports them for convenience and adds config-layer errors.
"""

from __future__ import annotations

from tools.domain.invariants import EvidenceValidationError, FabricationGuardError


class PiProofError(Exception):
    """Base class for all PiProof unrecoverable errors."""


class PolicyError(PiProofError):
    """Configuration or policy validation error."""


__all__ = [
    "PiProofError",
    "EvidenceValidationError",
    "FabricationGuardError",
    "PolicyError",
]
