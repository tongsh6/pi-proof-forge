"""Stage-related types — re-exported from domain for convenience.

The canonical definitions live in tools.domain.protocols
(Stage, StageResult, Pipeline) and tools.domain.value_objects.
"""

from __future__ import annotations

from tools.domain.protocols import Stage as StageProtocol
from tools.domain.protocols import StageResult

RunContext = dict[str, object]

__all__ = ["StageProtocol", "StageResult", "RunContext"]
