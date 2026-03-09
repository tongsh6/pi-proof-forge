from __future__ import annotations

from collections.abc import Sequence

from tools.cli.commands._runner import run_legacy_main


def main(argv: Sequence[str] | None = None) -> int:
    return run_legacy_main("tools.run_matching_scoring", argv)
