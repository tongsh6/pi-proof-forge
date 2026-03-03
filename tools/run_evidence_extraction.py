#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path
from typing import cast


def main() -> int:
    parser = argparse.ArgumentParser(description="Run evidence extraction workflow")
    _ = parser.add_argument("--input", required=True, help="Raw material path")
    _ = parser.add_argument("--output", required=True, help="Output evidence card path")
    _ = parser.add_argument("--id", help="Evidence card id (optional)")
    args = parser.parse_args()

    input_path = cast(str, args.input)
    output_path = cast(str, args.output)
    id_arg = cast(str | None, args.id)

    cmd = [
        "python3",
        "tools/extract_evidence.py",
        "--input",
        input_path,
        "--output",
        output_path,
    ]
    if id_arg:
        cmd.extend(["--id", id_arg])

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(cmd, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
