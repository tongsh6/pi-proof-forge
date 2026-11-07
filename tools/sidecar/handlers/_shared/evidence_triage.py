"""证据卡补全分流（triage）旁路文件的共享访问。

``evidence_reconcile`` 与 ``evidence_inference`` 拆分后都需要读取分流记录；
应用数据目录会被测试 patch，因此运行时从 ``evidence`` 原模块读取。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _evidence():
    from tools.sidecar.handlers import evidence

    return evidence


def triage_path() -> Path:
    return _evidence()._APP_DATA_DIR / "evidence_triage.json"


def load_triage() -> dict[str, Any]:
    path = triage_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("evidence_triage_unreadable") from exc
    if not isinstance(data, dict):
        raise ValueError("evidence_triage_unreadable")
    return data


def card_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
