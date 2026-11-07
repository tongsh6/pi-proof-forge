"""Quick Run 进度：由 run_log 事件推导四阶段真实状态。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ._shared.agent_runtime import _elapsed_seconds_between, _utcnow_iso


def _facade():
    """门面模块：路径常量、Popen 与运行态由 handlers/agent.py 持有（可被测试 patch）。"""
    from tools.sidecar.handlers import agent

    return agent

def _stage_progress_from_events(
    events: list[dict[str, Any]],
    *,
    started_at: str = "",
    final_status: str = "",
    now: str | None = None,
) -> dict[str, Any]:
    """由 run_log.json 事件推导 Quick Run 四阶段进度（纯函数，不读写文件）。

    stage: {key, status(waiting|running|done|error|skipped), started_at?, finished_at?, elapsed_seconds?}
    final_status 为空时使用 PIPELINE_DONE/PIPELINE_FAILED 事件内的终态；
    传入进程真实终态（DONE/SKIPPED/FAILED/TIMEOUT/stopped）时以其为准。
    """
    stages: dict[str, dict[str, Any]] = {
        key: {"key": key, "status": "waiting"} for key in _facade()._QUICK_RUN_STAGES
    }
    if started_at and stages["extract"]["status"] == "waiting":
        stages["extract"]["status"] = "running"
        stages["extract"]["started_at"] = started_at

    event_terminal_status = ""
    terminal_timestamp = ""
    failed_step = ""

    def stage_for_step(step: Any) -> dict[str, Any] | None:
        key = _facade()._QUICK_RUN_STEP_STAGES.get(str(step or ""))
        return stages.get(key) if key else None

    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        timestamp = str(event.get("timestamp") or "")
        if event_type == "PIPELINE_STEP_START":
            stage = stage_for_step(payload.get("step"))
            if stage is not None:
                stage["status"] = "running"
                start_stamp = timestamp or started_at
                if start_stamp:
                    stage.setdefault("started_at", start_stamp)
        elif event_type == "PIPELINE_STEP_SUCCESS":
            stage = stage_for_step(payload.get("step"))
            if stage is not None:
                start_stamp = timestamp or started_at
                if start_stamp:
                    stage.setdefault("started_at", start_stamp)
                finish_stamp = timestamp or stage.get("started_at", "")
                if finish_stamp:
                    stage["finished_at"] = finish_stamp
                stage["status"] = "done"
        elif event_type == "PIPELINE_STEP_FAILURE":
            stage = stage_for_step(payload.get("step"))
            if stage is not None:
                start_stamp = timestamp or started_at
                if start_stamp:
                    stage.setdefault("started_at", start_stamp)
                finish_stamp = timestamp or stage.get("started_at", "")
                if finish_stamp:
                    stage["finished_at"] = finish_stamp
                stage["status"] = "error"
        elif event_type in {"PIPELINE_DONE", "PIPELINE_FAILED"}:
            event_terminal_status = str(
                payload.get("status") or event_terminal_status
            )
            failed_step = str(payload.get("failed_step") or failed_step)
            terminal_timestamp = timestamp or terminal_timestamp

    effective_status = final_status or event_terminal_status
    normalized = effective_status.upper() if effective_status else ""
    if normalized:
        failed_stage = stage_for_step(failed_step)
        if normalized == "DONE":
            for stage in stages.values():
                if stage["status"] != "done":
                    if started_at:
                        stage.setdefault("started_at", started_at)
                    finish_stamp = terminal_timestamp or stage.get("started_at", "")
                    if finish_stamp:
                        stage["finished_at"] = finish_stamp
                    stage["status"] = "done"
        elif normalized == "SKIPPED":
            for stage in stages.values():
                if stage["status"] != "done":
                    stage["status"] = "skipped"
                    stage["finished_at"] = (
                        terminal_timestamp
                        or stage.get("finished_at")
                        or stage.get("started_at", "")
                    )
        elif normalized in {"FAILED", "TIMEOUT"}:
            if failed_stage is not None and failed_stage["status"] != "done":
                failed_stage["status"] = "error"
                if started_at:
                    failed_stage.setdefault("started_at", started_at)
                finish_stamp = terminal_timestamp or failed_stage.get("started_at", "")
                if finish_stamp:
                    failed_stage["finished_at"] = finish_stamp
            for stage in stages.values():
                if stage["status"] == "running":
                    stage["status"] = "error"
                    stage["finished_at"] = (
                        terminal_timestamp
                        or stage.get("finished_at")
                        or stage.get("started_at", "")
                    )
            if not any(stage["status"] == "error" for stage in stages.values()):
                for key in _facade()._QUICK_RUN_STAGES:
                    stage = stages[key]
                    if stage["status"] != "done":
                        stage["status"] = "error"
                        if started_at:
                            stage.setdefault("started_at", started_at)
                        finish_stamp = terminal_timestamp or stage.get(
                            "started_at", ""
                        )
                        if finish_stamp:
                            stage["finished_at"] = finish_stamp
                        break
        elif normalized == "STOPPED":
            # 用户取消不是错误：未开始的阶段保持 waiting，正在执行的阶段标记 skipped。
            for stage in stages.values():
                if stage["status"] == "running":
                    stage["status"] = "skipped"
                    stage["finished_at"] = terminal_timestamp or now or _utcnow_iso()

    current_timestamp = now or _utcnow_iso()
    for stage in stages.values():
        started = stage.get("started_at")
        finished = stage.get("finished_at")
        if started and finished:
            elapsed = _elapsed_seconds_between(started, finished)
        elif started and normalized in {"", "RUNNING"}:
            elapsed = _elapsed_seconds_between(started, current_timestamp)
        else:
            elapsed = None
        if elapsed is not None:
            stage["elapsed_seconds"] = elapsed

    current_stage: str | None = None
    if normalized in {"", "RUNNING"}:
        for key in _facade()._QUICK_RUN_STAGES:
            if stages[key]["status"] == "running":
                current_stage = key
                break
        if current_stage is None:
            for key in _facade()._QUICK_RUN_STAGES:
                if stages[key]["status"] == "waiting":
                    current_stage = key
                    break

    return {
        "stages": [stages[key] for key in _facade()._QUICK_RUN_STAGES],
        "current_stage": current_stage,
        "updated_at": current_timestamp,
    }


def _pipeline_run_log_path(run_id: str) -> Path:
    return _facade()._PROJECT_ROOT / "outputs" / "agent_runs" / run_id / "run_log.json"


def _read_pipeline_run_events(run_id: str) -> list[dict[str, Any]]:
    path = _pipeline_run_log_path(run_id)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def _refresh_quick_run_progress(run_id: str) -> None:
    events = _read_pipeline_run_events(run_id)
    with _facade()._QUICK_RUN_LOCK:
        try:
            payload = _facade()._load_quick_run(run_id)
        except KeyError:
            return
        run_payload = payload.get("run")
        started_at = (
            str(run_payload.get("started_at") or "")
            if isinstance(run_payload, dict)
            else ""
        )
        payload["progress"] = _stage_progress_from_events(
            events, started_at=started_at
        )
        _facade()._save_quick_run(_facade()._get_quick_run_file(run_id), payload)


def _quick_run_envelope(payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    run_payload = payload.get("run")
    if not isinstance(run_payload, dict):
        run_payload = {}
    run_id = str(run_payload.get("run_id") or "")
    progress = payload.get("progress")
    if not isinstance(progress, dict):
        # 兼容不含 progress 的旧记录：按 run_log 事件与终态推导，避免终态仍显示“进行中”。
        status = str(run_payload.get("status") or "")
        progress = _stage_progress_from_events(
            _read_pipeline_run_events(run_id),
            started_at=str(run_payload.get("started_at") or ""),
            final_status=status if status in _facade()._QUICK_RUN_TERMINAL_STATUSES else "",
        )
    envelope: dict[str, Any] = {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "status": str(run_payload.get("status") or ""),
        "started_at": str(run_payload.get("started_at") or ""),
        "finished_at": str(run_payload.get("finished_at") or ""),
        "exit_code": run_payload.get("exit_code"),
        "run_record": str(Path("outputs") / "agent_runs" / run_id / "run_log.json"),
        "summary": str(Path("outputs") / "agent_runs" / run_id / "summary.json"),
        "llm_config_summary": run_payload.get("llm_config_summary") or {},
        "material_source": run_payload.get("material_source"),
        "job_profile": run_payload.get("job_profile") or {},
        "selected_evidence_card_ids": list(
            run_payload.get("selected_evidence_card_ids") or []
        ),
        "progress": progress,
    }
    for key, value in payload.items():
        if key not in _facade()._QUICK_RUN_ENVELOPE_KEYS:
            envelope[key] = value
    return envelope
