"""原有 JSON 审批队列的原子写入与进程互斥。"""
import os
from contextlib import contextmanager
from pathlib import Path

from tools.infra.persistence.atomic_io import atomic_write_json


@contextmanager
def locked_review_queue(path: Path):
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
