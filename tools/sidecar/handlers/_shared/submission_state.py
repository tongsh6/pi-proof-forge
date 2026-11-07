"""投递记录状态访问（跨 handler 共享）。

``platform_feedback`` 等只读消费者需要 submission handler 的投递目录与日志
解析函数；这些符号会被测试 patch，因此统一在运行时从 ``submission`` 模块读取。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _submission():
    from tools.sidecar.handlers import submission

    return submission


def submissions_dir() -> Path:
    return _submission()._SUBMISSIONS_DIR


def job_lead_dir() -> Path:
    return _submission()._JOB_LEAD_DIR


def submission_log_paths() -> list[Path]:
    return _submission()._submission_log_paths()


def load_submission_log(path: Path) -> dict[str, Any]:
    return _submission()._load_submission_log(path)


def managed_delivery(payload: dict[str, Any]) -> bool:
    return _submission()._managed_delivery(payload)
