from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def build_external_l3_validation(
    *,
    root: Path,
    run_id: str,
    generated_at: str,
    default_timeout_seconds: int,
) -> dict[str, Any]:
    request = _request_from_env(root, default_timeout_seconds)
    blocker_reason = _blocker_reason(request)
    base: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": generated_at,
        "level": "L3",
        "step": "external_l3_submission_validation",
        "channel": request["channel"],
        "authorized": request["authorized"],
        "final_submit_confirmed": request["final_submit_confirmed"],
        "safety_invariants": {
            "explicit_user_authorization_required": True,
            "explicit_final_submit_gate_required": True,
            "credentials_not_accepted_by_runner": True,
            "captcha_or_sms_bypass_not_accepted_by_runner": True,
            "secrets_are_not_persisted": True,
        },
        "inputs": {
            "job_url_present": bool(request["job_url"]),
            "resume_pdf_path_present": bool(request["resume_pdf_path"]),
            "profile_path_present": bool(request["profile_path"]),
            "confirm_submit_job_id_present": bool(request["confirm_submit_job_id"]),
            "confirm_submit_recruiter_present": bool(request["confirm_submit_recruiter"]),
            "session_dir": request["session_dir"],
            "output_dir": request["output_dir"],
        },
    }
    base["live_run_readiness"] = _live_run_readiness(
        request=request,
        blocker_reason=blocker_reason,
    )
    base["operator_handoff"] = _operator_handoff(
        request=request,
        blocker_reason=blocker_reason,
        external_submission_attempted=False,
    )

    if blocker_reason:
        base.update(
            {
                "status": "live_blocker_recorded",
                "external_submission_attempted": False,
                "live_blocker": {
                    "reason": blocker_reason,
                    "category": _blocker_category(blocker_reason),
                    "next_action": _next_action(blocker_reason),
                },
                "coverage": _coverage(
                    authorized=request["authorized"],
                    final_submit_confirmed=request["final_submit_confirmed"],
                    has_external_result=False,
                    has_live_blocker=True,
                ),
            }
        )
        return base

    command = _submission_command(request)
    completed = subprocess.run(
        list(command),
        cwd=str(root),
        check=False,
        capture_output=True,
        text=True,
        timeout=request["timeout_seconds"],
    )
    submission_traceability = _submission_traceability(
        root=root,
        output=completed.stdout + completed.stderr,
    )
    command_succeeded = completed.returncode == 0
    external_validated = command_succeeded and bool(
        submission_traceability["linked_to_validation"]
    )
    blocker_after_run = _post_command_blocker_reason(
        command_succeeded=command_succeeded,
        submission_traceability=submission_traceability,
    )
    base.update(
        {
            "status": (
                "external_validated" if external_validated else "live_blocker_recorded"
            ),
            "external_submission_attempted": True,
            "command": list(command),
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
            "live_result": {
                "status": "success" if external_validated else "blocked_or_failed",
                "log_hint": submission_traceability["log_hint"],
            },
            "submission_traceability": submission_traceability,
            "coverage": _coverage(
                authorized=True,
                final_submit_confirmed=True,
                has_external_result=external_validated,
                has_live_blocker=not external_validated,
            ),
        }
    )
    if not external_validated:
        base["live_blocker"] = {
            "reason": blocker_after_run,
            "category": _blocker_category(blocker_after_run),
            "next_action": _next_action(blocker_after_run),
        }
    base["live_run_readiness"] = _live_run_readiness(
        request=request,
        blocker_reason=blocker_after_run,
    )
    base["operator_handoff"] = _operator_handoff(
        request=request,
        blocker_reason=blocker_after_run,
        external_submission_attempted=True,
    )
    return base


def write_external_l3_validation(
    *,
    root: Path,
    run_id: str,
    validation: dict[str, Any],
) -> tuple[Path, Path]:
    output_dir = root / "outputs" / "acceptance" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "external-l3-validation.json"
    markdown_path = output_dir / "external-l3-validation.md"
    json_path.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_external_l3_validation_markdown(validation),
        encoding="utf-8",
    )
    return json_path, markdown_path


def render_external_l3_validation_markdown(validation: dict[str, Any]) -> str:
    blocker = validation.get("live_blocker") or {}
    coverage = validation.get("coverage") or {}
    readiness = validation.get("live_run_readiness") or {}
    submission_traceability = validation.get("submission_traceability") or {}
    handoff = validation.get("operator_handoff") or {}
    lines = [
        "# External L3 投递验证",
        "",
        f"- Run ID: `{validation['run_id']}`",
        f"- 状态: `{validation['status']}`",
        f"- 渠道: `{validation['channel']}`",
        f"- 是否触发外部提交: `{validation['external_submission_attempted']}`",
        f"- 生成时间: `{validation['generated_at']}`",
        "",
        "## 覆盖项",
        "",
        "| 检查项 | 状态 |",
        "|---|---:|",
    ]
    for key, status in coverage.items():
        lines.append(f"| `{key}` | `{status}` |")
    if blocker:
        lines.extend(
            [
                "",
                "## Live Blocker",
                "",
                f"- Reason: `{blocker.get('reason', '')}`",
                f"- 分类: `{blocker.get('category', '')}`",
                f"- 下一步: {blocker.get('next_action', '')}",
            ]
        )
    if readiness:
        lines.extend(
            [
                "",
                "## Live Run Readiness",
                "",
                f"- 是否就绪: `{readiness.get('ready', False)}`",
                f"- 是否允许启动 submit 命令: `{readiness.get('submit_command_allowed', False)}`",
                f"- 阻断原因: `{readiness.get('blocking_reason', '')}`",
                "",
                "| Gate | 状态 | 说明 |",
                "|---|---:|---|",
            ]
        )
        for gate in readiness.get("gates", []):
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{gate.get('id', '')}`",
                        f"`{gate.get('status', '')}`",
                        str(gate.get("detail", "")),
                    ]
                )
                + " |"
            )
    if submission_traceability:
        lines.extend(
            [
                "",
                "## Submission Log Traceability",
                "",
                f"- Linked: `{submission_traceability.get('linked_to_validation', False)}`",
                f"- YAML: `{submission_traceability.get('log_yaml_path', '')}`",
                f"- JSON: `{submission_traceability.get('log_json_path', '')}`",
                f"- YAML Exists: `{submission_traceability.get('log_yaml_exists', False)}`",
                f"- JSON Exists: `{submission_traceability.get('log_json_exists', False)}`",
            ]
        )
    if handoff:
        lines.extend(
            [
                "",
                "## 授权交接包",
                "",
                f"- 状态: `{handoff.get('status', '')}`",
                f"- 下一步: {handoff.get('next_action', '')}",
                "",
                "| 必需环境变量 | 是否存在 | 是否敏感 |",
                "|---|---:|---:|",
            ]
        )
        for item in handoff.get("required_env", []):
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{item.get('name', '')}`",
                        f"`{item.get('present', False)}`",
                        f"`{item.get('sensitive', False)}`",
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "### 运行前检查清单",
                "",
            ]
        )
        for item in handoff.get("pre_run_checklist", []):
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _request_from_env(root: Path, default_timeout_seconds: int) -> dict[str, Any]:
    return {
        "authorized": _env_bool("PIPF_EXTERNAL_L3_AUTHORIZED"),
        "final_submit_confirmed": _env_bool("PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED"),
        "channel": os.environ.get("PIPF_EXTERNAL_L3_CHANNEL", "liepin").strip()
        or "liepin",
        "job_url": os.environ.get("PIPF_EXTERNAL_L3_JOB_URL", "").strip(),
        "resume_pdf_path": os.environ.get("PIPF_EXTERNAL_L3_RESUME_PDF", "").strip(),
        "profile_path": os.environ.get("PIPF_EXTERNAL_L3_PROFILE", "").strip(),
        "confirm_submit_job_id": os.environ.get(
            "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID", ""
        ).strip(),
        "confirm_submit_recruiter": os.environ.get(
            "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER", ""
        ).strip(),
        "session_dir": os.environ.get("PIPF_EXTERNAL_L3_SESSION_DIR", ".sessions").strip()
        or ".sessions",
        "output_dir": os.environ.get(
            "PIPF_EXTERNAL_L3_OUTPUT_DIR", "outputs/submissions"
        ).strip()
        or "outputs/submissions",
        "timeout_seconds": _env_int(
            "PIPF_EXTERNAL_L3_TIMEOUT_SECONDS",
            default_timeout_seconds,
        ),
        "timeout_ms": _env_int("PIPF_EXTERNAL_L3_TIMEOUT_MS", 45000),
        "headless": _env_bool("PIPF_EXTERNAL_L3_HEADLESS"),
        "root": str(root),
    }


def _blocker_reason(request: dict[str, Any]) -> str:
    if not request["authorized"]:
        return "explicit_user_authorization_required"
    if not request["final_submit_confirmed"]:
        return "explicit_final_submit_confirmation_required"
    if request["channel"] != "liepin":
        return "unsupported_external_l3_channel"
    missing = [
        name
        for name in (
            "job_url",
            "resume_pdf_path",
            "profile_path",
            "confirm_submit_job_id",
            "confirm_submit_recruiter",
        )
        if not request[name]
    ]
    if missing:
        return "missing_live_submission_inputs:" + ",".join(missing)
    root = Path(str(request["root"]))
    for field in ("resume_pdf_path", "profile_path"):
        path = Path(str(request[field]))
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            return f"missing_live_input_file:{field}"
    if not str(request["job_url"]).startswith(("http://", "https://")):
        return "invalid_live_job_url"
    return ""


def _blocker_category(reason: str) -> str:
    if reason.startswith("explicit_"):
        return "authorization"
    if reason.startswith("missing_") or reason.startswith("invalid_"):
        return "input_readiness"
    if reason.startswith("unsupported_"):
        return "channel_support"
    return "external_channel"


def _next_action(reason: str) -> str:
    if reason == "explicit_user_authorization_required":
        return (
            "先取得用户对真实外部渠道验证的显式授权；未授权前不得触碰外部渠道。"
        )
    if reason == "explicit_final_submit_confirmation_required":
        return (
            "在用户复核渠道、目标岗位、简历和账号后，要求单独最终提交确认。"
        )
    if reason.startswith("missing_live_submission_inputs"):
        return (
            "通过 PIPF_EXTERNAL_L3_* 环境变量补齐真实岗位 URL、简历 PDF、"
            "profile YAML、确认 job id 和确认 recruiter。"
        )
    if reason.startswith("missing_live_input_file"):
        return "将 PIPF_EXTERNAL_L3_* 文件路径指向已存在的本地产物。"
    if reason == "invalid_live_job_url":
        return "为真实渠道目标提供 http 或 https 岗位 URL。"
    if reason == "unsupported_external_l3_channel":
        return (
            "当前 P0 L3 只支持 liepin；如需其他渠道，先扩展渠道适配器。"
        )
    if reason == "submission_log_not_linked":
        return (
            "真实渠道命令已返回成功，但没有解析到可验证的 submission_log.yaml/json；"
            "请检查命令输出和 submission recorder。"
        )
    if reason == "external_channel_command_returned_nonzero":
        return (
            "检查 stdout_tail、stderr_tail 和持久化 submission log，确认 live "
            "blocker 已修复后再重试。"
        )
    return (
        "检查外部渠道日志，理解并修复 blocker 后再重试。"
    )


def _post_command_blocker_reason(
    *,
    command_succeeded: bool,
    submission_traceability: dict[str, Any],
) -> str:
    if not command_succeeded:
        return "external_channel_command_returned_nonzero"
    if not submission_traceability["linked_to_validation"]:
        return "submission_log_not_linked"
    return ""


def _submission_traceability(*, root: Path, output: str) -> dict[str, Any]:
    log_hint = _extract_submission_log_hint(output)
    yaml_path = _extract_submission_yaml_path(root=root, output=output)
    json_path = yaml_path.with_name("submission_log.json") if yaml_path else None
    return {
        "log_hint": log_hint,
        "log_yaml_path": str(yaml_path) if yaml_path else "",
        "log_json_path": str(json_path) if json_path else "",
        "log_yaml_exists": bool(yaml_path and yaml_path.exists()),
        "log_json_exists": bool(json_path and json_path.exists()),
        "linked_to_validation": bool(
            yaml_path
            and json_path
            and yaml_path.exists()
            and json_path.exists()
        ),
    }


def _extract_submission_yaml_path(*, root: Path, output: str) -> Path | None:
    for line in reversed(output.splitlines()):
        if "submission_log.yaml" not in line:
            continue
        candidate = line.split("log:", 1)[-1].strip()
        if "submission_log.yaml" in candidate:
            candidate = candidate[: candidate.index("submission_log.yaml") + len("submission_log.yaml")]
        path = Path(candidate)
        if not path.is_absolute():
            path = root / path
        return path
    return None


def _operator_handoff(
    *,
    request: dict[str, Any],
    blocker_reason: str,
    external_submission_attempted: bool,
) -> dict[str, Any]:
    if external_submission_attempted and not blocker_reason:
        status = "executed_with_guarded_live_result"
        next_action = "复核真实渠道结果、submission log 和后续反馈记录。"
    elif blocker_reason:
        status = "blocked_until_operator_action"
        next_action = _next_action(blocker_reason)
    else:
        status = "ready_for_authorized_live_run"
        next_action = "运行 L3 前再次复核账号、岗位、简历和最终提交确认。"

    return {
        "status": status,
        "next_action": next_action,
        "required_env": _required_env_handoff(request),
        "pre_run_checklist": [
            "用户已明确授权接触真实外部渠道。",
            "用户已单独确认允许最终提交路径进入真实渠道命令。",
            "岗位 URL、确认 job id、确认 recruiter 与页面目标一致。",
            "resume PDF 与 profile YAML 指向本地已审核产物。",
            "确认不会输入、保存或绕过密码、验证码、短信码。",
        ],
        "forbidden_inputs": [
            "password",
            "captcha_code",
            "sms_code",
            "raw_api_key",
            "unconfirmed_submit",
        ],
        "command_template": (
            "PIPF_EXTERNAL_L3_AUTHORIZED=true "
            "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=true "
            "PIPF_EXTERNAL_L3_JOB_URL=<https-url> "
            "PIPF_EXTERNAL_L3_RESUME_PDF=<resume.pdf> "
            "PIPF_EXTERNAL_L3_PROFILE=<profile.yaml> "
            "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID=<job-id> "
            "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER=<recruiter> "
            "bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3"
        ),
    }


def _live_run_readiness(
    *,
    request: dict[str, Any],
    blocker_reason: str,
) -> dict[str, Any]:
    gates = [
        _readiness_gate(
            gate_id="user_authorization",
            passed=bool(request["authorized"]),
            detail="用户显式授权接触真实外部渠道",
        ),
        _readiness_gate(
            gate_id="final_submit_confirmation",
            passed=bool(request["final_submit_confirmed"]),
            detail="用户单独确认最终提交路径",
        ),
        _readiness_gate(
            gate_id="supported_channel",
            passed=request["channel"] == "liepin",
            detail=f"channel={request['channel']}",
        ),
        _readiness_gate(
            gate_id="job_url_present",
            passed=bool(request["job_url"]),
            detail="真实岗位 URL 已提供",
        ),
        _readiness_gate(
            gate_id="resume_pdf_present",
            passed=bool(request["resume_pdf_path"]),
            detail="已审核简历 PDF 路径已提供",
        ),
        _readiness_gate(
            gate_id="profile_yaml_present",
            passed=bool(request["profile_path"]),
            detail="已审核 profile YAML 路径已提供",
        ),
        _readiness_gate(
            gate_id="confirm_job_id_present",
            passed=bool(request["confirm_submit_job_id"]),
            detail="确认岗位 ID 已提供",
        ),
        _readiness_gate(
            gate_id="confirm_recruiter_present",
            passed=bool(request["confirm_submit_recruiter"]),
            detail="确认招聘方已提供",
        ),
    ]
    ready = all(gate["status"] == "pass" for gate in gates) and not blocker_reason
    return {
        "ready": ready,
        "submit_command_allowed": ready,
        "blocking_reason": blocker_reason,
        "gates": gates,
        "missing_gates": [
            gate["id"] for gate in gates if gate["status"] != "pass"
        ],
    }


def _readiness_gate(*, gate_id: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "id": gate_id,
        "status": "pass" if passed else "blocked",
        "detail": detail,
    }


def _required_env_handoff(request: dict[str, Any]) -> list[dict[str, Any]]:
    fields = (
        ("PIPF_EXTERNAL_L3_AUTHORIZED", request["authorized"], False, "真实渠道授权"),
        (
            "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED",
            request["final_submit_confirmed"],
            False,
            "最终提交确认",
        ),
        ("PIPF_EXTERNAL_L3_JOB_URL", bool(request["job_url"]), False, "目标岗位 URL"),
        (
            "PIPF_EXTERNAL_L3_RESUME_PDF",
            bool(request["resume_pdf_path"]),
            False,
            "已审核简历 PDF",
        ),
        (
            "PIPF_EXTERNAL_L3_PROFILE",
            bool(request["profile_path"]),
            False,
            "已审核 profile YAML",
        ),
        (
            "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID",
            bool(request["confirm_submit_job_id"]),
            False,
            "确认岗位 ID",
        ),
        (
            "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER",
            bool(request["confirm_submit_recruiter"]),
            False,
            "确认招聘方",
        ),
    )
    return [
        {
            "name": name,
            "present": bool(present),
            "sensitive": sensitive,
            "description": description,
        }
        for name, present, sensitive, description in fields
    ]


def _submission_command(request: dict[str, Any]) -> tuple[str, ...]:
    command = [
        sys.executable,
        "-m",
        "tools.submission.run_submission",
        "--platform",
        str(request["channel"]),
        "--job-url",
        str(request["job_url"]),
        "--resume",
        str(request["resume_pdf_path"]),
        "--profile",
        str(request["profile_path"]),
        "--output-dir",
        str(request["output_dir"]),
        "--session-dir",
        str(request["session_dir"]),
        "--timeout-ms",
        str(request["timeout_ms"]),
        "--confirm-submit-job-id",
        str(request["confirm_submit_job_id"]),
        "--confirm-submit-recruiter",
        str(request["confirm_submit_recruiter"]),
        "--submit",
    ]
    command.append("--headless" if request["headless"] else "--no-headless")
    return tuple(command)


def _coverage(
    *,
    authorized: bool,
    final_submit_confirmed: bool,
    has_external_result: bool,
    has_live_blocker: bool,
) -> dict[str, str]:
    return {
        "user_authorized_external_session": "pass" if authorized else "blocked_recorded",
        "explicit_final_submit_gate": (
            "pass" if final_submit_confirmed else "blocked_recorded"
        ),
        "live_channel_result_or_blocker_recorded": (
            "pass" if (has_external_result or has_live_blocker) else "fail"
        ),
        "post_submit_feedback_traceability": (
            "pass" if has_external_result else "not_applicable_live_blocker"
        ),
        "no_secret_or_captcha_bypass": "pass",
    }


def _extract_submission_log_hint(output: str) -> str:
    for line in reversed(output.splitlines()):
        if "log:" in line:
            return line.strip()
    return ""


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default
