"""Quick Run：单次四阶段 pipeline 的启动、执行、取消与生命周期。

从原 handlers/agent.py 拆出；进度推导在 quick_run_progress.py，材料/路径/结果
解析在 quick_run_results.py。对外入口由 handlers/agent.py 门面 re-export。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.persistence.atomic_io import atomic_write_text
from tools.infra.persistence.yaml_io import parse_simple_yaml

from ._shared.agent_runtime import (
    _coerce_positive_int,
    _utcnow_iso,
    _validate_run_resource_id,
)
from .quick_run_progress import (
    _quick_run_envelope,
    _read_pipeline_run_events,
    _refresh_quick_run_progress,
    _stage_progress_from_events,
)
from .quick_run_results import (
    _direction_precheck_cache_dir,
    _load_job_profile_context,
    _read_job_profile_context,
    _official_target_pin,
    _official_stage_path,
    require_current_official_run,
    is_unpinned_official_run,
    _quick_run_paths,
    _quick_run_positioning,
    _quick_run_result_details,
    _selected_evidence_cards,
    _stage_selected_evidence,
)


def _facade():
    """门面模块：路径常量、Popen 与运行态由 handlers/agent.py 持有（可被测试 patch）。"""
    from tools.sidecar.handlers import agent

    return agent

def _ensure_quick_run_dir() -> None:
    _facade()._QUICK_RUN_DIR.mkdir(parents=True, exist_ok=True)


def _build_quick_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"qr_{timestamp}"


def _get_quick_run_file(run_id: str) -> Path:
    _ensure_quick_run_dir()
    return _facade()._QUICK_RUN_DIR / f"{run_id}.json"


def _load_quick_run(run_id: str) -> dict[str, Any]:
    run_file = _get_quick_run_file(run_id)
    if not run_file.exists():
        raise KeyError(f"NOT_FOUND: quick run not found: {run_id}")
    return json.loads(run_file.read_text(encoding="utf-8"))


def _save_quick_run(run_file: Path, payload: dict[str, Any]) -> None:
    # 原子替换：后台线程写进度时，读取方不会看到半截 JSON。
    atomic_write_text(run_file, json.dumps(payload, ensure_ascii=False, indent=2))


def _read_temp_file_text(handle: Any) -> str:
    try:
        handle.flush()
        handle.seek(0)
        data = handle.read()
    except (OSError, ValueError):
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _wait_for_process_exit(process: Any, timeout: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            if process.poll() is not None:
                return True
        except OSError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _terminate_quick_run_process(process: Any) -> None:
    """超时/取消时尽量终止管线进程：先 terminate，宽限期后 kill。"""
    try:
        process.terminate()
    except OSError:
        pass
    if _wait_for_process_exit(process, _facade()._QUICK_RUN_TERMINATE_GRACE_SECONDS):
        return
    try:
        process.kill()
    except OSError:
        pass
    _wait_for_process_exit(process, _facade()._QUICK_RUN_TERMINATE_GRACE_SECONDS)


def _official_run_changed(run: dict) -> bool:
    if "official_target" not in run:
        return False
    try:
        require_current_official_run(run, _facade()._PROJECT_ROOT)
    except ValueError:
        return True
    return False


def _mark_official_run_historical(payload: dict) -> dict:
    readiness = payload.get("resume_readiness")
    readiness = readiness if isinstance(readiness, dict) else {}
    run = payload.get("run") or {}
    context = run.get("job_profile") or {}
    no_resume = readiness.get("status") in (None, "NOT_GENERATED")
    return {**payload, "reason": "quick_official_target_changed",
            "run": {**run, "job_profile": {**context, "active_target_eligible": False}},
            "resume_readiness": {**readiness, "content_ready": False, "deliverable": False,
                                 "quality_passed": False, "manual_override_allowed": False,
                                 "status": "NOT_GENERATED" if no_resume else "NEEDS_REVIEW",
                                 "reasons": ["官方岗位来源或启动版本无法核对，请重新准备。" if no_resume else
                                             "官方岗位来源或启动版本无法核对，已有产物仅供历史查看，请重新准备。"]}}


def _finalize_quick_run(
    run_id: str,
    *,
    status: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    official_target_changed: bool = False,
) -> None:
    """把管线终态、阶段终态与结果详情一次性写回 quick_runs JSON。

    详情组装（含 PDF 导出）期间保持 RUNNING，避免 UI 在详情就绪前停止轮询。
    """

    try:
        # 详情组装（含 PDF 导出）可能耗时数百毫秒到数秒，必须在锁外进行：
        # 期间 run.quick.get 仍能读到 RUNNING，且不被阻塞。
        with _facade()._QUICK_RUN_LOCK:
            snapshot = _load_quick_run(run_id)
            snapshot_run = snapshot.get("run")
            if not isinstance(snapshot_run, dict):
                snapshot_run = {}
            started_at = str(snapshot_run.get("started_at") or "")
            selected_ids = [
                str(item)
                for item in snapshot_run.get("selected_evidence_card_ids") or []
            ]
            positioning = snapshot_run.get("resume_positioning")
        target_changed = official_target_changed or _official_run_changed(snapshot_run)
        if target_changed and status == "DONE":
            status = "FAILED"
        events = _read_pipeline_run_events(run_id)
        progress = _stage_progress_from_events(
            events, started_at=started_at, final_status=status
        )
        try:
            details = _quick_run_result_details(
                run_id,
                stdout,
                stderr,
                selected_evidence_card_ids=selected_ids,
                resume_positioning=positioning
                if isinstance(positioning, dict)
                else None,
                **({"export_pdf": False} if target_changed else {}),
            )
        except Exception as exc:  # noqa: BLE001 - 结果组装失败也必须落终态
            details = {
                "stdout": stdout[-4000:],
                "stderr": (
                    stderr + f"\n[quick-run] result assembly failed: {exc}"
                )[-4000:],
            }
        target_changed = target_changed or _official_run_changed(snapshot_run)
        if target_changed and status == "DONE":
            status = "FAILED"
            progress = _stage_progress_from_events(events, started_at=started_at, final_status=status)
        with _facade()._QUICK_RUN_LOCK:
            payload = _load_quick_run(run_id)
            run_payload = payload.get("run")
            if not isinstance(run_payload, dict):
                run_payload = {}
                payload["run"] = run_payload
            run_payload["status"] = status
            run_payload["exit_code"] = exit_code
            run_payload["finished_at"] = _utcnow_iso()
            payload["progress"] = progress
            payload.update(details)
            if target_changed:
                payload = _mark_official_run_historical(payload)
            payload["stdout"] = str(details.get("stdout") or stdout[-4000:])
            payload["stderr"] = str(details.get("stderr") or stderr[-4000:])
            _save_quick_run(_get_quick_run_file(run_id), payload)
            active = _facade()._QUICK_RUN_ACTIVE
            if active is not None and active.get("run_id") == run_id:
                _facade()._QUICK_RUN_ACTIVE = None
    finally:
        with _facade()._QUICK_RUN_LOCK:
            active = _facade()._QUICK_RUN_ACTIVE
            if active is not None and active.get("run_id") == run_id:
                _facade()._QUICK_RUN_ACTIVE = None


def _execute_quick_run(
    run_id: str,
    command: list[str],
    llm_env: dict[str, str],
    timeout_seconds: int,
    cancel_event: threading.Event,
) -> None:
    """后台线程：Popen 执行 run_pipeline，轮询 run_log 写真实阶段进度。"""
    status = "FAILED"
    exit_code: int | None = None
    stdout_text = ""
    stderr_text = ""
    process: Any = None
    official_target_changed = False
    # stdout/stderr 写临时文件，避免管道填满阻塞子进程。
    out_handle = tempfile.TemporaryFile()
    err_handle = tempfile.TemporaryFile()
    try:
        if cancel_event.is_set():
            status = "stopped"
        else:
            try:
                run = _load_quick_run(run_id)["run"]
                if "official_target" in run:
                    try:
                        require_current_official_run(run, _facade()._PROJECT_ROOT, command=command)
                    except ValueError:
                        official_target_changed = True
                        raise
                process = _facade().Popen(
                    command,
                    stdout=out_handle,
                    stderr=err_handle,
                    cwd=str(_facade()._PROJECT_ROOT),
                    env={**os.environ, **llm_env},
                )
            except OSError as exc:
                stderr_text = f"[quick-run] failed to start pipeline: {exc}\n"
            if process is not None:
                with _facade()._QUICK_RUN_LOCK:
                    active = _facade()._QUICK_RUN_ACTIVE
                    if active is not None and active.get("run_id") == run_id:
                        active["process"] = process
                deadline = time.monotonic() + timeout_seconds
                while True:
                    returncode = process.poll()
                    if returncode is not None:
                        exit_code = returncode
                        status = (
                            "DONE"
                            if returncode == 0
                            else ("SKIPPED" if returncode == 2 else "FAILED")
                        )
                        break
                    if cancel_event.is_set():
                        status = "stopped"
                        _terminate_quick_run_process(process)
                        exit_code = process.poll()
                        break
                    if time.monotonic() >= deadline:
                        status = "TIMEOUT"
                        _terminate_quick_run_process(process)
                        exit_code = process.poll()
                        break
                    try:
                        _refresh_quick_run_progress(run_id)
                    except OSError:
                        pass
                    cancel_event.wait(_facade()._QUICK_RUN_POLL_INTERVAL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - 后台线程异常不得泄漏，落 FAILED 终态
        status = "FAILED"
        stderr_text += f"\n[quick-run] internal error: {exc}\n"
    finally:
        stdout_text = _read_temp_file_text(out_handle)
        stderr_text = stderr_text + _read_temp_file_text(err_handle)
        try:
            out_handle.close()
        except OSError:
            pass
        try:
            err_handle.close()
        except OSError:
            pass
        _finalize_quick_run(
            run_id,
            status=status,
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            official_target_changed=official_target_changed,
        )


def _run_quick_run_worker(
    run_id: str,
    command: list[str],
    llm_env: dict[str, str],
    timeout_seconds: int,
    cancel_event: threading.Event,
) -> None:

    try:
        _execute_quick_run(run_id, command, llm_env, timeout_seconds, cancel_event)
    except Exception:  # noqa: BLE001 - 最外层兜底，确保活跃标记被清理
        with _facade()._QUICK_RUN_LOCK:
            active = _facade()._QUICK_RUN_ACTIVE
            if active is not None and active.get("run_id") == run_id:
                _facade()._QUICK_RUN_ACTIVE = None


def _join_quick_run_thread(timeout: float | None = None) -> None:
    thread = _facade()._QUICK_RUN_LAST_THREAD
    if thread is not None and thread.is_alive():
        thread.join(timeout)


def handle_quick_check_direction(params: dict[str, Any]) -> dict[str, Any]:
    """启动前方向预检：只读分析并返回建议；excluded 时要求用户确认，但不阻断。"""
    correlation_id = params["meta"]["correlation_id"]
    job_profile_id = _validate_run_resource_id(
        "job_profile_id", params.get("job_profile_id")
    )
    job_profile_path = _facade()._PROJECT_ROOT / "job_profiles" / f"{job_profile_id}.yaml"
    if not job_profile_path.is_file():
        raise ValueError(f"job_profile_path does not exist: {job_profile_path}")
    # 与正式运行共用同一 active / 官方来源门禁。
    _load_job_profile_context(job_profile_id, job_profile_path)

    def response(
        direction: dict[str, Any] | None,
        requires_confirmation: bool = False,
        unavailable_reason: str = "",
    ) -> dict[str, Any]:
        return {
            "meta": {"correlation_id": correlation_id},
            "direction": direction,
            "requires_confirmation": requires_confirmation,
            "unavailable_reason": unavailable_reason,
        }

    from tools.infra.job_preferences import assess_direction, load_preferences

    personal_profile = _facade()._PROJECT_ROOT / "personal_profile.yaml"
    preferences = load_preferences(personal_profile) if personal_profile.is_file() else None
    if not preferences:
        # 未确认求职偏好时不做方向判断，也不阻断启动。
        return response(None, False, "no_preferences")

    doc = parse_simple_yaml(job_profile_path.read_text(encoding="utf-8"))
    from tools.infra.job_context import load_jd_source
    jd, _jd_path = load_jd_source(
        str(doc["scalars"].get("source_jd", "")), job_profile_path
    )
    if not jd.strip():
        return response(None, False, "jd_missing")

    llm_summary, llm_env = _facade()._persisted_llm_runtime_context()
    provider = str(llm_env.get("LLM_PROVIDER", "")).strip()
    model = str(llm_env.get("LLM_MODEL", "")).strip()
    api_key = str(llm_env.get("LLM_API_KEY", "")).strip()
    from tools.infra.llm.client import LLMClient, llm_request_available
    if not llm_request_available(provider=provider, api_key=api_key, model=model,
                                 base_url=str(llm_env.get("LLM_BASE_URL", "")).strip()):
        return response(None, False, "llm_unavailable")
    try:
        client = LLMClient(
            base_url=str(llm_env.get("LLM_BASE_URL", "")).strip(),
            api_key=api_key,
            timeout=int(llm_env.get("LLM_TIMEOUT") or 60),
            provider=provider,
            thinking_enabled=llm_summary.get("thinking_enabled"),
            reasoning_effort=str(llm_summary.get("thinking_effort") or "high"),
        )
        review = assess_direction(
            preferences, jd, client, model, _direction_precheck_cache_dir()
        )
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        # 预检只做建议；失败时前端 fail-open，继续走正常启动流程。
        detail = str(exc) or type(exc).__name__
        return response(None, False, f"direction_unavailable:{detail}"[:300])
    review = {**review, "preferences_revision": preferences["revision"]}
    return response(review, review.get("status") == "excluded", "")


def handle_quick_start(params: dict[str, Any]) -> dict[str, Any]:
    """启动单次 pipeline；立即返回 RUNNING，由后台线程执行并回写逐阶段进度。"""

    correlation_id = params["meta"]["correlation_id"]
    job_profile_id = _validate_run_resource_id(
        "job_profile_id", params.get("job_profile_id")
    )
    evidence_id = params.get("evidence_id")
    if evidence_id is not None:
        _validate_run_resource_id("evidence_id", evidence_id)
    options = params.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("options must be an object")
    # 方向评估是建议而非门禁：用户在看到预检分析后仍选择运行时记录确认，
    # 仅供审计与结果页展示，不参与启动放行判断。
    direction_acknowledged = options.get("direction_acknowledged") is True

    # 同步校验保持原顺序：校验失败在返回前直接抛错，不会启动后台线程。
    raw_path, job_profile_path, material_context = _quick_run_paths(job_profile_id, options)
    job_profile_context, profile_bytes, official_lead = _read_job_profile_context(job_profile_id, job_profile_path)
    official_target = _official_target_pin(profile_bytes, official_lead) if official_lead is not None else None
    selected_evidence_cards = _selected_evidence_cards(
        str(evidence_id).strip() if evidence_id is not None else None, options
    )
    selected_evidence_card_ids = [
        str(card["evidence_id"]) for card in selected_evidence_cards
    ]
    resume_positioning = _quick_run_positioning(options)
    llm_config_summary, llm_env = _facade()._persisted_llm_runtime_context()

    # 同进程一次只允许一个活跃 Quick Run；已结束的残留标记允许清理。
    with _facade()._QUICK_RUN_LOCK:
        active = _facade()._QUICK_RUN_ACTIVE
        active_thread = active.get("thread") if isinstance(active, dict) else None
        if isinstance(active_thread, threading.Thread) and active_thread.is_alive():
            raise ValueError("quick_run_already_running")

    run_id = _facade()._build_quick_run_id()
    evidence_dir = Path("outputs") / "quick_runs" / run_id / "evidence_cards"
    _stage_selected_evidence(selected_evidence_cards, evidence_dir)
    staged_profile = job_profile_path
    if official_target is not None:
        staged_profile = _official_stage_path(_facade()._PROJECT_ROOT, run_id, job_profile_id)
        atomic_write_text(staged_profile, profile_bytes.decode("utf-8"), mode=0o400)
    started_at = _utcnow_iso()
    command = [
        sys.executable,
        "-m",
        "tools.cli.entrypoints",
        "pipeline",
        "--raw",
        str(raw_path),
        "--job-profile",
        str(staged_profile),
        "--evidence-dir",
        str(evidence_dir),
        "--run-id",
        run_id,
        "--skip-evidence-extraction",
        "--personal-profile",
        str(_facade()._PROJECT_ROOT / "personal_profile.yaml"),
        "--resume-positioning",
        resume_positioning["mode"],
        "--custom-positioning",
        resume_positioning["custom"],
    ]
    timeout_seconds = _coerce_positive_int(options.get("timeout_seconds"), 120)
    if options.get("use_llm") is True:
        command.append("--use-llm")
    if options.get("require_llm") is True:
        command.append("--require-llm")

    payload = {
        "run": {
            "run_id": run_id,
            "status": "RUNNING",
            "started_at": started_at,
            "finished_at": "",
            "job_profile_id": job_profile_id,
            "evidence_id": evidence_id or "",
            "job_profile": job_profile_context,
            "selected_evidence_card_ids": selected_evidence_card_ids,
            "raw_path": str(raw_path),
            "job_profile_path": str(job_profile_path),
            **({"official_target": official_target} if official_target is not None else {}),
            "material_source": material_context,
            "evidence_dir": str(evidence_dir),
            "resume_positioning": resume_positioning,
            "command": command,
            "exit_code": None,
            "options": options,
            "direction_acknowledgement": {
                "acknowledged": direction_acknowledged,
                "acknowledged_at": started_at if direction_acknowledged else "",
            },
            "llm_config_summary": llm_config_summary,
        },
        "progress": _stage_progress_from_events([], started_at=started_at),
    }
    cancel_event = threading.Event()
    thread = threading.Thread(
        target=_run_quick_run_worker,
        args=(run_id, command, llm_env, timeout_seconds, cancel_event),
        name=f"quick-run-{run_id}",
        daemon=True,
    )
    with _facade()._QUICK_RUN_LOCK:
        active = _facade()._QUICK_RUN_ACTIVE
        active_thread = active.get("thread") if isinstance(active, dict) else None
        if isinstance(active_thread, threading.Thread) and active_thread.is_alive():
            raise ValueError("quick_run_already_running")
        # 先落盘再启动线程，保证 start 返回后 run.quick.get 立即可读到 RUNNING。
        _save_quick_run(_get_quick_run_file(run_id), payload)
        _facade()._QUICK_RUN_ACTIVE = {
            "run_id": run_id,
            "process": None,
            "cancel_event": cancel_event,
            "thread": thread,
        }
        _facade()._QUICK_RUN_LAST_THREAD = thread
        thread.start()

    return _quick_run_envelope(payload, correlation_id)


def _hide_unverifiable_saved_coverage(payload: dict) -> dict:
    review = payload.get("semantic_review")
    if not isinstance(review, dict) or review.get("occurrence_coverage_known") is True:
        return payload
    def without_occurrence(row):
        return {**row, "resume_status":"unassessed",
                "citations":[{**c, "in_resume":False, "render_lines":[]} for c in row.get("citations", [])]}
    historical = {**review, "occurrence_coverage_known":False, "resume_score":None,
                  "all_requirements_supported":False,
                  "requirements":[{**without_occurrence(row),
                                   "checks":[without_occurrence(c) for c in row.get("checks", [])]}
                                  for row in review.get("requirements", [])]}
    readiness = payload.get("resume_readiness") or {}
    return {**payload, "semantic_review":historical, "quality_report":None,
            "resume_readiness":{**readiness, "quality_report":None, "quality_passed":False, "auto_pass":False,
                                 "reasons":[*readiness.get("reasons", []),
                                            "旧稿缺少逐条事实呈现记录，请重新生成以核验覆盖。"]}}


def handle_quick_get(params: dict[str, Any]) -> dict[str, Any]:
    """读取 Quick Run 当前状态与真实阶段进度；终态时附带完整结果详情。"""
    correlation_id = params["meta"]["correlation_id"]
    run_id = _validate_run_resource_id("run_id", params.get("run_id"))
    with _facade()._QUICK_RUN_LOCK:
        payload = _load_quick_run(run_id)
    run = payload.get("run", {})
    if isinstance(run, dict) and run.get("status") == "DONE" and (
        _official_run_changed(run) or ("official_target" not in run and is_unpinned_official_run(run))
    ):
        payload = _mark_official_run_historical(payload)
    return _quick_run_envelope(_hide_unverifiable_saved_coverage(payload), correlation_id)


def handle_quick_cancel(params: dict[str, Any]) -> dict[str, Any]:
    """取消 Quick Run：写取消标记并通知后台线程 terminate 管线进程。"""
    correlation_id = params["meta"]["correlation_id"]
    run_id = _validate_run_resource_id("run_id", params.get("run_id"))
    run_file = _get_quick_run_file(run_id)
    cancel_event: threading.Event | None = None
    with _facade()._QUICK_RUN_LOCK:
        payload = _load_quick_run(run_id)
        run_payload = payload.get("run")
        if not isinstance(run_payload, dict):
            run_payload = {}
            payload["run"] = run_payload
        run_payload["cancel_requested_at"] = _utcnow_iso()
        active = _facade()._QUICK_RUN_ACTIVE
        active_thread = active.get("thread") if isinstance(active, dict) else None
        if (
            isinstance(active, dict)
            and active.get("run_id") == run_id
            and isinstance(active_thread, threading.Thread)
            and active_thread.is_alive()
        ):
            event = active.get("cancel_event")
            if isinstance(event, threading.Event):
                cancel_event = event
        elif run_payload.get("status") not in _facade()._QUICK_RUN_TERMINAL_STATUSES:
            # 没有活跃后台线程（例如 sidecar 重启后的残留记录）时直接落 stopped。
            run_payload["status"] = "stopped"
            run_payload["finished_at"] = _utcnow_iso()
            payload["progress"] = _stage_progress_from_events(
                _read_pipeline_run_events(run_id),
                started_at=str(run_payload.get("started_at") or ""),
                final_status="stopped",
            )
        _save_quick_run(run_file, payload)
    if cancel_event is not None:
        cancel_event.set()

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": True,
    }
