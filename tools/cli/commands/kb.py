"""知识索引命令：转发到 tooling/knowledge（build/tree/find/grep/read/refs/cards/leads/verify/coverage）。

用法见 AIEF/docs/plans/2026-10-17-knowledge-index.md；索引只做导航，引用前必须
用 ``kb read`` 回原文，并以 material_id/document_id/sha256 锚定。
"""

from __future__ import annotations

from collections.abc import Sequence

from tools.tooling.knowledge import main as knowledge_main


def main(argv: Sequence[str] | None = None) -> int:
    return knowledge_main(list(argv) if argv is not None else None)


if __name__ == "__main__":
    raise SystemExit(main())
