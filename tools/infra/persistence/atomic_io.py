"""文件原子写入的唯一实现。

同一目录临时文件 → 写入 → fsync → `os.replace`，失败时清理临时文件。
替换散落在各 handler/infra 模块里的手写版本，保证：
- 写一半崩溃不会留下半截文件；
- 并发读永远看到旧内容或新内容，不会看到中间态；
- 临时文件不会残留。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    """原子写文本；`mode` 用于显式设置权限（如凭据文件 0600）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: object, *, indent: int = 2) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=indent) + "\n")
