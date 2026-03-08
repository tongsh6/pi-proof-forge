from __future__ import annotations

import importlib.util
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "ui" / "scripts" / "verify_packaged_app.py"
)
SPEC = importlib.util.spec_from_file_location("verify_packaged_app", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
PARSE_SUMMARY = cast(
    Callable[[str], dict[str, object]], getattr(MODULE, "_parse_summary")
)
RESOLVE_APP_BINARY = cast(
    Callable[[Path], Path], getattr(MODULE, "_resolve_app_binary")
)


class VerifyPackagedAppTests(unittest.TestCase):
    def test_parse_summary_returns_last_json_result(self) -> None:
        stdout = 'noise\n{"ok": true, "ping": {"state": "ready"}}\n'

        summary = PARSE_SUMMARY(stdout)
        ping = cast(dict[str, object], summary["ping"])

        self.assertTrue(summary["ok"])
        self.assertEqual(ping["state"], "ready")

    def test_resolve_app_binary_raises_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app_path = Path(temp_dir) / "PiProofForge.app"
            _ = app_path.mkdir()

            with self.assertRaises(RuntimeError):
                _ = RESOLVE_APP_BINARY(app_path)


if __name__ == "__main__":
    _ = unittest.main()
