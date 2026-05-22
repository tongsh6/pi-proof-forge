from __future__ import annotations

import json
import os
import subprocess
import sys
import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def build_external_l3_validation(
    *,
    root: Path,
    run_id: str,
    generated_at: str,
    default_timeout_seconds: int,
) -> dict[str, Any]:
    request = _request_from_env(root, default_timeout_seconds)
    request["external_l3_validation_run_id"] = run_id
    request["external_l3_validation_path"] = str(
        Path("outputs") / "acceptance" / run_id / "external-l3-validation.json"
    )
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
        "live_input_artifacts": _live_input_artifacts(request),
    }
    base["live_run_readiness"] = _live_run_readiness(
        request=request,
        blocker_reason=blocker_reason,
    )
    base["submit_safety_decision"] = _submit_safety_decision(
        request=request,
        readiness=base["live_run_readiness"],
        pre_submit_blocker_reason=blocker_reason,
        external_submission_attempted=False,
    )
    base["operator_handoff"] = _operator_handoff(
        request=request,
        blocker_reason=blocker_reason,
        external_submission_attempted=False,
    )

    if blocker_reason:
        live_blocker = {
            "reason": blocker_reason,
            "category": _blocker_category(blocker_reason),
            "next_action": _next_action(blocker_reason),
        }
        base.update(
            {
                "status": "live_blocker_recorded",
                "external_submission_attempted": False,
                "live_blocker": live_blocker,
                "post_submit_feedback_traceability": _post_submit_feedback_traceability(
                    request=request,
                    external_validated=False,
                    external_submission_attempted=False,
                    live_blocker=live_blocker,
                    submission_traceability={},
                ),
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
        expected_validation_run_id=run_id,
        expected_validation_path=str(request["external_l3_validation_path"]),
        expected_input_artifacts=base["live_input_artifacts"],
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
            "command": _redacted_submission_command(command),
            "command_redaction": {
                "raw_live_inputs_persisted": False,
                "redacted_arguments": [
                    "--job-url",
                    "--resume",
                    "--profile",
                    "--confirm-submit-job-id",
                    "--confirm-submit-recruiter",
                ],
            },
            "live_output_redaction": _live_output_redaction_evidence(),
            "returncode": completed.returncode,
            "stdout_tail": _redacted_live_output_tail(completed.stdout, request),
            "stderr_tail": _redacted_live_output_tail(completed.stderr, request),
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
    base["submit_safety_decision"] = _submit_safety_decision(
        request=request,
        readiness=base["live_run_readiness"],
        pre_submit_blocker_reason="",
        external_submission_attempted=True,
        command_returncode=completed.returncode,
        post_run_blocker_reason=blocker_after_run,
    )
    if not external_validated:
        base["live_blocker"] = {
            "reason": blocker_after_run,
            "category": _blocker_category(blocker_after_run),
            "next_action": _next_action(blocker_after_run),
        }
    base["post_submit_feedback_traceability"] = _post_submit_feedback_traceability(
        request=request,
        external_validated=external_validated,
        external_submission_attempted=True,
        live_blocker=base.get("live_blocker") or {},
        submission_traceability=submission_traceability,
    )
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
    submit_decision = validation.get("submit_safety_decision") or {}
    input_artifacts = validation.get("live_input_artifacts") or {}
    output_redaction = validation.get("live_output_redaction") or {}
    submission_traceability = validation.get("submission_traceability") or {}
    feedback_traceability = validation.get("post_submit_feedback_traceability") or {}
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
    if submit_decision:
        lines.extend(
            [
                "",
                "## 最终提交安全决策",
                "",
                f"- 决策: `{submit_decision.get('decision', '')}`",
                f"- 是否允许 submit 命令: `{submit_decision.get('submit_command_allowed', False)}`",
                f"- 是否已经执行外部提交命令: `{submit_decision.get('external_submission_attempted', False)}`",
                f"- 授权已确认: `{submit_decision.get('authorization_confirmed', False)}`",
                f"- 最终提交已确认: `{submit_decision.get('final_submit_confirmed', False)}`",
                f"- 真实输入已齐备: `{submit_decision.get('live_inputs_ready', False)}`",
                f"- 阻断原因: `{submit_decision.get('blocking_reason', '')}`",
                f"- 执行后阻断原因: `{submit_decision.get('post_run_blocker_reason', '')}`",
            ]
        )
        missing_gates = submit_decision.get("missing_gates") or []
        if missing_gates:
            lines.extend(["", "### 缺失 Gate", ""])
            for gate in missing_gates:
                lines.append(f"- `{gate}`")
    if output_redaction:
        lines.extend(
            [
                "",
                "## 执行输出脱敏",
                "",
                f"- Live 输入原值是否持久化: `{output_redaction.get('raw_live_inputs_persisted', True)}`",
                f"- 脱敏字段: `{', '.join(output_redaction.get('redacted_fields', []))}`",
            ]
        )
    if input_artifacts:
        job_url = input_artifacts.get("job_url") or {}
        files = input_artifacts.get("files") or []
        confirmations = input_artifacts.get("confirmations") or {}
        lines.extend(
            [
                "",
                "## 真实输入产物审计",
                "",
                f"- Job URL 已提供: `{job_url.get('present', False)}`",
                f"- Job URL Scheme: `{job_url.get('scheme', '')}`",
                f"- Job URL Host: `{job_url.get('hostname', '')}`",
                f"- Job URL 原值是否持久化: `{job_url.get('raw_value_persisted', False)}`",
                f"- 确认 job id 已提供: `{confirmations.get('confirm_submit_job_id_present', False)}`",
                f"- 确认 recruiter 已提供: `{confirmations.get('confirm_submit_recruiter_present', False)}`",
                "",
                "| 产物 | 已提供 | 存在文件 | 扩展名 | 大小 | SHA256 |",
                "|---|---:|---:|---|---:|---|",
            ]
        )
        for item in files:
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{item.get('id', '')}`",
                        f"`{item.get('provided', False)}`",
                        f"`{item.get('is_file', False)}`",
                        f"`{item.get('suffix', '')}`",
                        str(item.get("size_bytes", 0)),
                        f"`{item.get('sha256', '')}`",
                    ]
                )
                + " |"
            )
    if submission_traceability:
        lines.extend(
            [
                "",
                "## Submission Log 追溯",
                "",
                f"- 是否完成双向链接: `{submission_traceability.get('linked_to_validation', False)}`",
                f"- YAML: `{submission_traceability.get('log_yaml_path', '')}`",
                f"- JSON: `{submission_traceability.get('log_json_path', '')}`",
                f"- YAML 是否存在: `{submission_traceability.get('log_yaml_exists', False)}`",
                f"- JSON 是否存在: `{submission_traceability.get('log_json_exists', False)}`",
                f"- Submission log 是否反向链接: `{submission_traceability.get('log_links_back_to_validation', False)}`",
                f"- Submission log 输入产物是否匹配: `{submission_traceability.get('submission_log_input_artifacts_match', False)}`",
                f"- Failed Checks: `{', '.join(submission_traceability.get('failed_checks', []))}`",
                f"- 预期 validation run id: `{submission_traceability.get('expected_external_l3_validation_run_id', '')}`",
                f"- 记录 validation run id: `{submission_traceability.get('logged_external_l3_validation_run_id', '')}`",
                f"- 预期 validation path: `{submission_traceability.get('expected_external_l3_validation_path', '')}`",
                f"- 记录 validation path: `{submission_traceability.get('logged_external_l3_validation_path', '')}`",
            ]
        )
        trace_checks = submission_traceability.get("checks") or []
        if trace_checks:
            lines.extend(
                [
                    "",
                    "| 检查项 | 状态 | 说明 |",
                    "|---|---:|---|",
                ]
            )
            for check in trace_checks:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            f"`{check.get('id', '')}`",
                            f"`{check.get('status', '')}`",
                            str(check.get("detail", "")),
                        ]
                    )
                    + " |"
                )
    if feedback_traceability:
        lines.extend(
            [
                "",
                "## 提交后反馈追溯",
                "",
                f"- 是否可追溯: `{feedback_traceability.get('traceable', False)}`",
                f"- 状态: `{feedback_traceability.get('status', '')}`",
                f"- 来源类型: `{feedback_traceability.get('source_type', '')}`",
                f"- 来源产物: `{feedback_traceability.get('source_artifact_path', '')}`",
                f"- 下一步反馈路径: `{feedback_traceability.get('feedback_iteration_route', '')}`",
                f"- 下一步: {feedback_traceability.get('next_action', '')}",
            ]
        )
        required_evidence = feedback_traceability.get("required_follow_up_evidence") or []
        if required_evidence:
            lines.extend(["", "### 后续必需证据", ""])
            for item in required_evidence:
                lines.append(f"- `{item}`")
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
    for field in ("resume_pdf_path", "profile_path"):
        if not _request_path_exists(request, field):
            return f"missing_live_input_file:{field}"
    if not _request_path_has_suffix(request, "resume_pdf_path", {".pdf"}):
        return "invalid_live_resume_pdf"
    if not _request_path_has_suffix(request, "profile_path", {".yaml", ".yml"}):
        return "invalid_live_profile_yaml"
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
    if reason == "invalid_live_resume_pdf":
        return "将 PIPF_EXTERNAL_L3_RESUME_PDF 指向已审核的 PDF 文件。"
    if reason == "invalid_live_profile_yaml":
        return "将 PIPF_EXTERNAL_L3_PROFILE 指向已审核的 YAML 文件。"
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


def _submission_traceability(
    *,
    root: Path,
    output: str,
    expected_validation_run_id: str,
    expected_validation_path: str,
    expected_input_artifacts: dict[str, Any],
) -> dict[str, Any]:
    log_hint = _extract_submission_log_hint(output)
    yaml_path = _extract_submission_yaml_path(root=root, output=output)
    json_path = yaml_path.with_name("submission_log.json") if yaml_path else None
    log_payload, parse_error = _read_submission_json(json_path)
    logged_validation_run_id = str(
        log_payload.get("external_l3_validation_run_id", "")
    ) if log_payload else ""
    logged_validation_path = str(
        log_payload.get("external_l3_validation_path", "")
    ) if log_payload else ""
    log_links_back = (
        bool(log_payload)
        and logged_validation_run_id == expected_validation_run_id
        and logged_validation_path == expected_validation_path
    )
    logged_input_artifacts = log_payload.get("input_artifacts") if log_payload else {}
    input_artifacts_match = _input_artifacts_match(
        expected=expected_input_artifacts,
        actual=logged_input_artifacts if isinstance(logged_input_artifacts, dict) else {},
    )
    checks = _submission_traceability_checks(
        yaml_path=yaml_path,
        json_path=json_path,
        parse_error=parse_error,
        log_payload=log_payload,
        run_id_matches=logged_validation_run_id == expected_validation_run_id,
        path_matches=logged_validation_path == expected_validation_path,
        input_artifacts_match=input_artifacts_match,
    )
    return {
        "log_hint": log_hint,
        "log_yaml_path": str(yaml_path) if yaml_path else "",
        "log_json_path": str(json_path) if json_path else "",
        "log_yaml_exists": bool(yaml_path and yaml_path.exists()),
        "log_json_exists": bool(json_path and json_path.exists()),
        "expected_external_l3_validation_run_id": expected_validation_run_id,
        "expected_external_l3_validation_path": expected_validation_path,
        "logged_external_l3_validation_run_id": logged_validation_run_id,
        "logged_external_l3_validation_path": logged_validation_path,
        "log_links_back_to_validation": log_links_back,
        "submission_log_input_artifacts_match": input_artifacts_match,
        "log_json_parse_error": parse_error,
        "checks": checks,
        "failed_checks": [
            check["id"] for check in checks if check["status"] != "pass"
        ],
        "linked_to_validation": bool(
            yaml_path
            and json_path
            and yaml_path.exists()
            and json_path.exists()
            and log_links_back
            and input_artifacts_match
        ),
    }


def _submission_traceability_checks(
    *,
    yaml_path: Path | None,
    json_path: Path | None,
    parse_error: str,
    log_payload: dict[str, Any],
    run_id_matches: bool,
    path_matches: bool,
    input_artifacts_match: bool,
) -> list[dict[str, str]]:
    return [
        _traceability_check(
            check_id="submission_log_hint_found",
            passed=yaml_path is not None,
            detail="命令输出包含 submission_log.yaml 路径",
        ),
        _traceability_check(
            check_id="submission_log_yaml_exists",
            passed=bool(yaml_path and yaml_path.exists()),
            detail="submission_log.yaml 存在",
        ),
        _traceability_check(
            check_id="submission_log_json_exists",
            passed=bool(json_path and json_path.exists()),
            detail="submission_log.json 存在",
        ),
        _traceability_check(
            check_id="submission_log_json_parseable",
            passed=bool(log_payload) and not parse_error,
            detail=parse_error or "submission_log.json 可解析",
        ),
        _traceability_check(
            check_id="external_l3_validation_run_id_matches",
            passed=run_id_matches,
            detail="submission log 反向链接本次 validation run id",
        ),
        _traceability_check(
            check_id="external_l3_validation_path_matches",
            passed=path_matches,
            detail="submission log 反向链接本次 validation path",
        ),
        _traceability_check(
            check_id="input_artifacts_match_validation",
            passed=input_artifacts_match,
            detail="submission log 输入产物指纹匹配 validation record",
        ),
    ]


def _traceability_check(
    *,
    check_id: str,
    passed: bool,
    detail: str,
) -> dict[str, str]:
    return {
        "id": check_id,
        "status": "pass" if passed else "fail",
        "detail": detail,
    }


def _input_artifacts_match(
    *,
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> bool:
    expected_job_url = expected.get("job_url") or {}
    actual_job_url = actual.get("job_url") or {}
    if not isinstance(expected_job_url, dict) or not isinstance(actual_job_url, dict):
        return False
    if expected_job_url.get("scheme", "") != actual_job_url.get("scheme", ""):
        return False
    if expected_job_url.get("hostname", "") != actual_job_url.get("hostname", ""):
        return False

    expected_files = _artifact_files_by_id(expected)
    actual_files = _artifact_files_by_id(actual)
    for artifact_id, expected_file in expected_files.items():
        actual_file = actual_files.get(artifact_id)
        if actual_file is None:
            return False
        for field in ("basename", "suffix", "size_bytes", "sha256"):
            if expected_file.get(field) != actual_file.get(field):
                return False
        if actual_file.get("raw_content_persisted") is not False:
            return False
    return bool(expected_files)


def _artifact_files_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = payload.get("files") or []
    if not isinstance(files, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict):
            continue
        artifact_id = str(item.get("id", ""))
        if artifact_id:
            result[artifact_id] = item
    return result


def _read_submission_json(json_path: Path | None) -> tuple[dict[str, Any], str]:
    if json_path is None or not json_path.exists():
        return {}, ""
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, str(exc)
    if not isinstance(payload, dict):
        return {}, "submission_log.json root is not an object"
    return payload, ""


def _post_submit_feedback_traceability(
    *,
    request: dict[str, Any],
    external_validated: bool,
    external_submission_attempted: bool,
    live_blocker: dict[str, Any],
    submission_traceability: dict[str, Any],
) -> dict[str, Any]:
    validation_path = str(request["external_l3_validation_path"])
    if external_validated:
        source_artifact = str(
            submission_traceability.get("log_json_path")
            or submission_traceability.get("log_yaml_path")
            or validation_path
        )
        return {
            "traceable": bool(submission_traceability.get("linked_to_validation")),
            "status": "ready_for_feedback_review",
            "source_type": "submission_log",
            "source_status": "external_validated",
            "source_reason": "",
            "source_artifact_path": source_artifact,
            "related_submission_log_yaml": str(
                submission_traceability.get("log_yaml_path", "")
            ),
            "related_submission_log_json": str(
                submission_traceability.get("log_json_path", "")
            ),
            "feedback_iteration_route": "feedback_iteration_after_check_mode",
            "next_action": (
                "复核真实渠道 submission log 和后续招聘方反馈；如产生反馈项，"
                "进入 feedback iteration 并保留 source artifact。"
            ),
            "required_follow_up_evidence": [
                "submission_log.yaml",
                "submission_log.json",
                "external-l3-validation.json",
                "feedback_iteration_record.json",
            ],
        }

    reason = str(live_blocker.get("reason", "unknown"))
    return {
        "traceable": bool(reason and validation_path),
        "status": "blocked_by_live_blocker",
        "source_type": "live_blocker",
        "source_status": (
            "external_submission_attempted_blocked"
            if external_submission_attempted
            else "pre_submit_blocked"
        ),
        "source_reason": reason,
        "source_artifact_path": validation_path,
        "related_submission_log_yaml": str(
            submission_traceability.get("log_yaml_path", "")
        ),
        "related_submission_log_json": str(
            submission_traceability.get("log_json_path", "")
        ),
        "feedback_iteration_route": "resolve_live_blocker_before_feedback_iteration",
        "next_action": str(live_blocker.get("next_action") or _next_action(reason)),
        "required_follow_up_evidence": [
            "external-l3-validation.json",
            "live_run_readiness",
            "operator_handoff",
        ],
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
    job_url_present = bool(request["job_url"])
    resume_path_present = bool(request["resume_pdf_path"])
    profile_path_present = bool(request["profile_path"])
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
            passed=job_url_present,
            detail="真实岗位 URL 已提供",
        ),
        _readiness_gate(
            gate_id="job_url_valid",
            passed=job_url_present
            and str(request["job_url"]).startswith(("http://", "https://")),
            detail="真实岗位 URL 使用 http/https",
        ),
        _readiness_gate(
            gate_id="resume_pdf_present",
            passed=resume_path_present,
            detail="已审核简历 PDF 路径已提供",
        ),
        _readiness_gate(
            gate_id="resume_pdf_file_ready",
            passed=resume_path_present
            and _request_path_exists(request, "resume_pdf_path")
            and _request_path_has_suffix(request, "resume_pdf_path", {".pdf"}),
            detail="已审核简历 PDF 文件存在且扩展名有效",
        ),
        _readiness_gate(
            gate_id="profile_yaml_present",
            passed=profile_path_present,
            detail="已审核 profile YAML 路径已提供",
        ),
        _readiness_gate(
            gate_id="profile_yaml_file_ready",
            passed=profile_path_present
            and _request_path_exists(request, "profile_path")
            and _request_path_has_suffix(request, "profile_path", {".yaml", ".yml"}),
            detail="已审核 profile YAML 文件存在且扩展名有效",
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


def _submit_safety_decision(
    *,
    request: dict[str, Any],
    readiness: dict[str, Any],
    pre_submit_blocker_reason: str,
    external_submission_attempted: bool,
    command_returncode: int | None = None,
    post_run_blocker_reason: str = "",
) -> dict[str, Any]:
    live_input_gate_ids = {
        "job_url_present",
        "job_url_valid",
        "resume_pdf_present",
        "resume_pdf_file_ready",
        "profile_yaml_present",
        "profile_yaml_file_ready",
        "confirm_job_id_present",
        "confirm_recruiter_present",
    }
    live_inputs_ready = all(
        gate["status"] == "pass"
        for gate in readiness.get("gates", [])
        if gate.get("id") in live_input_gate_ids
    )
    submit_command_allowed = bool(readiness.get("submit_command_allowed"))
    if external_submission_attempted:
        decision = "allowed_and_executed"
    elif submit_command_allowed:
        decision = "allowed_pending_execution"
    else:
        decision = "blocked_before_command"
    blocking_reason = pre_submit_blocker_reason
    return {
        "decision": decision,
        "submit_command_allowed": submit_command_allowed,
        "external_submission_attempted": external_submission_attempted,
        "authorization_confirmed": bool(request["authorized"]),
        "final_submit_confirmed": bool(request["final_submit_confirmed"]),
        "supported_channel_confirmed": request["channel"] == "liepin",
        "live_inputs_ready": live_inputs_ready,
        "missing_gates": list(readiness.get("missing_gates") or []),
        "blocking_reason": blocking_reason,
        "post_run_blocker_reason": post_run_blocker_reason,
        "command_returncode": command_returncode,
        "requires_explicit_user_authorization": True,
        "requires_separate_final_submit_confirmation": True,
        "credentials_or_challenge_inputs_accepted": False,
        "confirmation_scope": [
            "用户显式授权接触真实外部渠道",
            "用户单独确认允许最终提交路径进入真实渠道命令",
            "确认岗位 ID 与页面目标一致",
            "确认招聘方与页面目标一致",
            "resume PDF 与 profile YAML 已审核",
        ],
    }


def _readiness_gate(*, gate_id: str, passed: bool, detail: str) -> dict[str, str]:
    return {
        "id": gate_id,
        "status": "pass" if passed else "blocked",
        "detail": detail,
    }


def _live_input_artifacts(request: dict[str, Any]) -> dict[str, Any]:
    parsed_job_url = urlparse(str(request["job_url"]))
    return {
        "job_url": {
            "present": bool(request["job_url"]),
            "scheme": parsed_job_url.scheme,
            "hostname": parsed_job_url.hostname or "",
            "supported_scheme": parsed_job_url.scheme in {"http", "https"},
            "raw_value_persisted": False,
        },
        "files": [
            _file_artifact_evidence(
                request=request,
                field="resume_pdf_path",
                artifact_id="resume_pdf",
                expected_suffixes={".pdf"},
            ),
            _file_artifact_evidence(
                request=request,
                field="profile_path",
                artifact_id="profile_yaml",
                expected_suffixes={".yaml", ".yml"},
            ),
        ],
        "confirmations": {
            "confirm_submit_job_id_present": bool(request["confirm_submit_job_id"]),
            "confirm_submit_recruiter_present": bool(
                request["confirm_submit_recruiter"]
            ),
            "raw_values_persisted": False,
        },
    }


def _file_artifact_evidence(
    *,
    request: dict[str, Any],
    field: str,
    artifact_id: str,
    expected_suffixes: set[str],
) -> dict[str, Any]:
    provided = bool(request[field])
    path = _resolve_request_path(request, field) if provided else Path("")
    is_file = provided and path.exists() and path.is_file()
    suffix = path.suffix.lower() if provided else ""
    return {
        "id": artifact_id,
        "provided": provided,
        "basename": path.name if provided else "",
        "suffix": suffix,
        "expected_suffixes": sorted(expected_suffixes),
        "suffix_valid": suffix in expected_suffixes,
        "exists": bool(provided and path.exists()),
        "is_file": bool(is_file),
        "size_bytes": path.stat().st_size if is_file else 0,
        "sha256": _sha256_file(path) if is_file else "",
        "raw_content_persisted": False,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_request_path(request: dict[str, Any], field: str) -> Path:
    path = Path(str(request[field]))
    if not path.is_absolute():
        path = Path(str(request["root"])) / path
    return path


def _request_path_exists(request: dict[str, Any], field: str) -> bool:
    path = _resolve_request_path(request, field)
    return path.exists() and path.is_file()


def _request_path_has_suffix(
    request: dict[str, Any],
    field: str,
    suffixes: set[str],
) -> bool:
    path = _resolve_request_path(request, field)
    return path.suffix.lower() in suffixes


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
        "--external-l3-validation-run-id",
        str(request["external_l3_validation_run_id"]),
        "--external-l3-validation-path",
        str(request["external_l3_validation_path"]),
        "--submit",
    ]
    command.append("--headless" if request["headless"] else "--no-headless")
    return tuple(command)


def _redacted_submission_command(command: tuple[str, ...]) -> list[str]:
    redacted_flags = {
        "--job-url",
        "--resume",
        "--profile",
        "--confirm-submit-job-id",
        "--confirm-submit-recruiter",
    }
    redacted: list[str] = []
    redact_next = False
    for token in command:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        redacted.append(token)
        if token in redacted_flags:
            redact_next = True
    return redacted


def _live_output_redaction_evidence() -> dict[str, Any]:
    return {
        "raw_live_inputs_persisted": False,
        "redacted_fields": [
            "job_url",
            "resume_pdf_path",
            "profile_path",
            "confirm_submit_job_id",
            "confirm_submit_recruiter",
        ],
    }


def _redacted_live_output_tail(output: str, request: dict[str, Any]) -> str:
    return _redact_live_output(output, request)[-4000:]


def _redact_live_output(output: str, request: dict[str, Any]) -> str:
    redacted = output
    for value in _live_output_redaction_values(request):
        redacted = redacted.replace(value, "<redacted>")
    return redacted


def _live_output_redaction_values(request: dict[str, Any]) -> list[str]:
    values = [
        str(request["job_url"]),
        str(request["resume_pdf_path"]),
        str(request["profile_path"]),
        str(request["confirm_submit_job_id"]),
        str(request["confirm_submit_recruiter"]),
    ]
    for field in ("resume_pdf_path", "profile_path"):
        if request[field]:
            values.append(str(_resolve_request_path(request, field)))

    unique_values = {value for value in values if value}
    return sorted(unique_values, key=len, reverse=True)


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
            "pass" if (has_external_result or has_live_blocker) else "fail"
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
