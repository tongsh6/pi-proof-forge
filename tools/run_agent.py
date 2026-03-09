from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cli.commands.agent import main as cli_main


def main() -> int:
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
