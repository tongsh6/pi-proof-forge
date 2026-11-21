from __future__ import annotations

import sys
from collections.abc import Sequence

from tools.cli.commands import (
    agent,
    check,
    evaluate,
    extract,
    extract_batch,
    generate,
    kb,
    match,
    pipeline,
)


COMMANDS = {
    "extract": extract.main,
    "extract-batch": extract_batch.main,
    "match": match.main,
    "generate": generate.main,
    "evaluate": evaluate.main,
    "pipeline": pipeline.main,
    "agent": agent.main,
    "check": check.main,
    "kb": kb.main,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python3 -m tools.cli.entrypoints <command> [args]")
        print("Commands: extract | extract-batch | match | generate | evaluate | pipeline | agent | check | kb")
        return 2

    command = args[0]
    handler = COMMANDS.get(command)
    if handler is None:
        print(f"Unknown command: {command}")
        print("Commands: extract | extract-batch | match | generate | evaluate | pipeline | agent | check | kb")
        return 2

    return int(handler(args[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
