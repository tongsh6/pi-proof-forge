"""门禁检查命令：架构约束 / 路线图 / AIEF / 投递就绪 / BOSS CLI live smoke。

实现位于 ``tools/tooling/``；本命令只做子命令分发，不实现检查规则。
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

from tools.tooling import aief_l3, arch_constraints, boss_agent_cli, roadmap, submission_readiness

USAGE = (
    "Usage: python3 -m tools.cli.entrypoints check <command> [args]\n"
    "Commands: arch | roadmap | aief | submission-readiness | boss-cli"
)

COMMANDS = {
    "arch": arch_constraints.main,
    "roadmap": roadmap.main,
    "aief": aief_l3.main,
    "submission-readiness": submission_readiness.main,
    "boss-cli": boss_agent_cli.main,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    if not args:
        print(USAGE)
        return 2
    command = args[0]
    handler = COMMANDS.get(command)
    if handler is None:
        print(f"Unknown check command: {command}")
        print(USAGE)
        return 2
    return int(handler(args[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
