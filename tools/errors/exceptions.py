from __future__ import annotations


class PiProofError(Exception):
    pass


class EvidenceValidationError(PiProofError):
    pass


class FabricationGuardError(PiProofError):
    pass


class PolicyError(PiProofError):
    pass
