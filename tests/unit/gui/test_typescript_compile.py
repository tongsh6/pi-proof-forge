"""TypeScript 编译门禁：UI 必须能通过 tsc（pnpm build 的前半段）。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ui_typecheck_passes():
    tsc = ROOT / "ui" / "node_modules" / ".bin" / "tsc"
    result = subprocess.run(
        [str(tsc), "--noEmit", "-p", "tsconfig.json"],
        cwd=ROOT / "ui", capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
