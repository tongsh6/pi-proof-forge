"""v2 架构约束门禁：仓库通过 + 违规形态能被抓到。"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path("tools/check_v2_constraints.py").resolve()


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_repo(root: Path) -> None:
    """满足唯一实现检查的最小骨架。"""
    for rel in (
        "tools/__init__.py",
        "tools/domain/__init__.py",
        "tools/infra/__init__.py",
        "tools/engines/__init__.py",
        "tools/orchestration/__init__.py",
        "tools/cli/__init__.py",
    ):
        _write(root / rel, "")
    _write(
        root / "tools" / "infra" / "client.py",
        "def post_json():\n    return None\n\n"
        "def extract_content():\n    return None\n\n"
        "def parse_simple_yaml():\n    return None\n",
    )


class CheckV2ConstraintsTests(unittest.TestCase):
    def test_constraints_script_passes_on_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, "tools/check_v2_constraints.py", "--root", "."],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("PASS v2 constraints", result.stdout)

    def test_detects_infra_depending_on_engines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_repo(root)
            _write(
                root / "tools" / "infra" / "bad.py",
                "from tools.engines.matching import rule_scorer\n",
            )
            result = _run(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("Layer dependency violation", result.stdout)
        self.assertIn("tools/infra/bad.py", result.stdout)

    def test_detects_engines_depending_on_orchestration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_repo(root)
            _write(
                root / "tools" / "engines" / "bad.py",
                "from tools.orchestration.pipeline import run_pipeline_flow\n",
            )
            result = _run(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("may not depend on orchestration", result.stdout)

    def test_detects_legacy_double_route_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_repo(root)
            _write(
                root / "tools" / "cli" / "legacy.py",
                'import os\nif os.getenv("PPF_FORCE_LEGACY_MAIN") == "1":\n    pass\n',
            )
            result = _run(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("Legacy entrypoint pattern", result.stdout)

    def test_detects_legacy_root_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_repo(root)
            _write(root / "tools" / "run_pipeline.py", "print('legacy')\n")
            result = _run(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("Forbidden legacy root script: tools/run_pipeline.py", result.stdout)

    def test_detects_argparse_in_orchestration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_repo(root)
            _write(
                root / "tools" / "orchestration" / "bad.py",
                "import argparse\nparser = argparse.ArgumentParser()\n",
            )
            result = _run(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("argparse found in orchestration layer", result.stdout)

    def test_detects_duplicate_llm_helper_outside_infra(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _minimal_repo(root)
            _write(
                root / "tools" / "engines" / "dup.py",
                "def post_json():\n    return None\n",
            )
            result = _run(root)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("Duplicate LLM client helper defs", result.stdout)


if __name__ == "__main__":
    _ = unittest.main()
