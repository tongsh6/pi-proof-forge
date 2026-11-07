"""岗位画像/招聘线索仓储访问（跨 handler 共享）。

``native_pdf``、``submission`` 等模块需要读取 jobs handler 的岗位目录与
循迹函数；这些符号会被测试 patch，因此统一在运行时从 ``jobs`` 模块读取。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _jobs():
    from tools.sidecar.handlers import jobs

    return jobs


def job_profile_dir() -> Path:
    return _jobs()._JOB_PROFILE_DIR


def job_lead_dir() -> Path:
    return _jobs()._JOB_LEAD_DIR


def profile_path(job_profile_id: str) -> Path:
    return _jobs()._profile_path(job_profile_id)


def lead_path(job_lead_id: str) -> Path:
    return _jobs()._lead_path(job_lead_id)


def find_lead_path(job_lead_id: str) -> Path | None:
    return _jobs()._find_lead_path(job_lead_id)


def read_yaml_doc(path: Path):
    return _jobs()._read_yaml_doc(path)


def bound_lead(job_lead_id: object, source_url: str = ""):
    return _jobs()._bound_lead(job_lead_id, source_url)


def platform_from_url(source_url: str) -> str:
    return _jobs().platform_from_url(source_url)


def check_source_url_accessible(source_url: str, timeout_seconds: int = 5) -> dict[str, Any]:
    return _jobs()._check_source_url_accessible(source_url, timeout_seconds)
