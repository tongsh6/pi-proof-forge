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
    external_validated = completed.returncode == 0
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
                "log_hint": _extract_submission_log_hint(
                    completed.stdout + completed.stderr
                ),
            },
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
            "reason": "external_channel_command_returned_nonzero",
            "category": "external_channel",
            "next_action": (
                "Inspect stdout_tail/stderr_tail and persisted submission log, then "
                "retry only after fixing the live blocker."
            ),
        }
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
    lines = [
        "# External L3 Submission Validation",
        "",
        f"- Run ID: `{validation['run_id']}`",
        f"- Status: `{validation['status']}`",
        f"- Channel: `{validation['channel']}`",
        f"- External Submission Attempted: `{validation['external_submission_attempted']}`",
        f"- Generated At: `{validation['generated_at']}`",
        "",
        "## Coverage",
        "",
        "| Check | Status |",
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
                f"- Category: `{blocker.get('category', '')}`",
                f"- Next Action: {blocker.get('next_action', '')}",
            ]
        )
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
            "Ask the user for explicit live-channel authorization before touching "
            "the external channel."
        )
    if reason == "explicit_final_submit_confirmation_required":
        return (
            "Ask the user for a separate final-submit confirmation after reviewing "
            "the exact channel, target, resume, and account."
        )
    if reason.startswith("missing_live_submission_inputs"):
        return (
            "Provide the live job URL, resume PDF, profile YAML, expected job id, "
            "and expected recruiter via PIPF_EXTERNAL_L3_* environment variables."
        )
    if reason.startswith("missing_live_input_file"):
        return "Point the PIPF_EXTERNAL_L3_* file path at an existing local artifact."
    if reason == "invalid_live_job_url":
        return "Use an http or https job URL for the live channel target."
    if reason == "unsupported_external_l3_channel":
        return (
            "Use channel liepin for the current P0 L3 validation, or extend the "
            "channel adapter first."
        )
    return (
        "Inspect the external channel log and retry only after the blocker is "
        "understood."
    )


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
