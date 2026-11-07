"""个人档案文件读写访问（跨 handler 共享）。

``job_preferences`` 需要读写个人档案；档案路径与读写函数会被测试 patch，
因此统一在运行时从 ``profile`` 模块读取。
"""
from __future__ import annotations

from pathlib import Path


def _profile():
    from tools.sidecar.handlers import profile

    return profile


def profile_path() -> Path:
    return _profile()._PROFILE_PATH


def load_profile() -> dict[str, str]:
    return _profile()._load_profile()


def write_profile(fields: dict[str, str]) -> None:
    _profile()._write_profile(fields)


def utcnow_iso() -> str:
    return _profile()._utcnow_iso()
