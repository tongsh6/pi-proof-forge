"""CLI 导入链不得依赖可选第三方库。

App 的 sidecar/Pipeline 子进程环境可能没有安装 PyYAML（曾导致 Quick Run 直接
FAILED：entrypoints → check 命令 → tooling.roadmap 顶层 `import yaml`）。
本测试在模拟「yaml 不可用」的子进程中导入 CLI 入口，锁定导入链只依赖标准库。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_entrypoints_import_without_pyyaml():
    code = (
        "import sys; "
        "sys.modules['yaml'] = None; "  # 模拟未安装 PyYAML（import yaml 抛 ImportError）
        "import tools.cli.entrypoints; "
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-800:]
    assert "ok" in result.stdout
