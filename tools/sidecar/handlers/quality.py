"""突出点用户决策：否决/替换写入 app-data/quality_decisions.json，不写证据卡。"""
from __future__ import annotations

import re

from tools.infra import quality_judge_cache
from tools.sidecar.handlers import agent

_HIGHLIGHT_RE = re.compile(r"hl_b\d+_[A-Za-z0-9_-]{1,120}")
_SHA_RE = re.compile(r"[0-9a-f]{64}")


def handle_quality_decide_highlight(params: dict) -> dict:
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")
    resume_sha256 = params.get("resume_sha256")
    highlight = params.get("highlight_id")
    action = params.get("action")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", run_id):
        raise ValueError("quality_run_id_invalid")
    if not isinstance(resume_sha256, str) or not _SHA_RE.fullmatch(resume_sha256):
        raise ValueError("quality_resume_sha256_invalid")
    if not isinstance(highlight, str) or not _HIGHLIGHT_RE.fullmatch(highlight):
        raise ValueError("quality_highlight_invalid")
    if action not in {"reject", "select"}:
        raise ValueError("quality_decision_invalid")
    if not agent._get_quick_run_file(run_id).is_file():
        raise ValueError("quality_run_not_found")
    decisions = quality_judge_cache.save_highlight_decision(
        agent._PROJECT_ROOT, resume_sha256, highlight, action
    )
    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "resume_sha256": resume_sha256,
        "highlight_id": highlight,
        "action": action,
        "decisions": decisions,
    }
