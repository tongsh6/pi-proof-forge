"""材料目录定位的唯一实现。

profile 可以放在任意路径（CLI 的 --personal-profile、验收时的临时副本），
材料目录不一定与它同级。这里统一约定：优先 profile 同级 materials，
不存在时回退到工作区 materials，避免各模块各自拼路径导致误报
"来源材料已变化"或 FileNotFoundError。
"""
from __future__ import annotations

from pathlib import Path


def materials_dir_for(profile_path: Path, *, fallback: Path | None = None) -> Path:
    candidate = Path(profile_path).parent / "materials"
    if candidate.is_dir():
        return candidate
    return fallback if fallback is not None else Path("materials")
