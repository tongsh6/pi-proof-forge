"""agent 域运行时状态访问（跨 handler 共享）。

``native_pdf``、``quality`` 等模块需要读取 Quick Run / Agent Run / Review 的
路径常量、运行态与队列读写函数。这些符号放在 ``handlers/agent.py`` 门面并会被
测试 patch；本模块在运行时从门面读取，避免复制或静态绑定。
"""
from __future__ import annotations

from typing import Any


def _agent():
    from tools.sidecar.handlers import agent

    return agent


def project_root():
    return _agent()._PROJECT_ROOT


def review_queue_dir():
    return _agent()._REVIEW_QUEUE_DIR


def agent_run_dir():
    return _agent()._AGENT_RUN_DIR


def quick_run_dir():
    return _agent()._QUICK_RUN_DIR


def utcnow_iso() -> str:
    return _agent()._utcnow_iso()


def build_agent_run_id() -> str:
    return _agent()._build_agent_run_id()


def get_quick_run_file(run_id: str):
    return _agent()._get_quick_run_file(run_id)


def get_queue_file(run_id: str):
    return _agent()._get_queue_file(run_id)


def get_agent_run_file(run_id: str):
    return _agent()._get_agent_run_file(run_id)


def load_queue(path):
    return _agent()._load_queue(path)


def save_queue(path, queue) -> None:
    _agent()._save_queue(path, queue)


def load_agent_run(run_id: str):
    return _agent()._load_agent_run(run_id)


def sync_review_run(run_id: str, queue, deliveries) -> None:
    _agent()._sync_review_run(run_id, queue, deliveries)
