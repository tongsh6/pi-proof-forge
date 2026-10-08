from __future__ import annotations

import datetime
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


_REDACTED_LIVE_INPUT = "<redacted>"
SUCCESS_SUBMISSION_REQUIRED_STEPS = (
    "rate_limit", "login_check", "target_verify",
    "submit_safety", "chat_send_resume", "submit",
)
API_SUBMISSION_REQUIRED_STEPS = (
    'idempotency', 'credential_check', 'target_check', 'resume_observed',
    'authorization', 'api_submit', 'receipt',
)


def submission_required_steps_evidence(log_payload: dict[str, Any]) -> dict[str, Any]:
    """共享步骤审计口径；非成功日志的 passed 不代表已投递。"""
    required = API_SUBMISSION_REQUIRED_STEPS if log_payload.get('transport') == 'liepin_api' else SUCCESS_SUBMISSION_REQUIRED_STEPS
    steps = log_payload.get("steps") if log_payload else []
    if not isinstance(steps, list):
        steps = []
    recorded_steps = [
        {"name": str(step.get("name", "")), "status": str(step.get("status", ""))}
        for step in steps if isinstance(step, dict)
    ]
    steps_by_name = {step["name"]: step for step in recorded_steps}
    if log_payload.get("status") != "success":
        return {
            "required_for_successful_submit": list(required),
            "recorded_steps": recorded_steps,
            "missing_steps": [],
            "failed_steps": [],
            "passed": bool(log_payload),
            "not_required_reason": (
                "submission_log_status_not_success" if log_payload else "missing_submission_log"
            ),
        }
    missing_steps = [name for name in required if name not in steps_by_name]
    failed_steps = [
        name for name in required
        if name in steps_by_name and steps_by_name[name]["status"] != "success"
    ]
    external_observation = log_payload.get('input_artifacts', {}).get('receipt_source') == 'website_history'
    return {
        "required_for_successful_submit": list(required),
        "recorded_steps": recorded_steps,
        "missing_steps": missing_steps,
        "failed_steps": failed_steps,
        "passed": not missing_steps and not failed_steps and not external_observation,
        "not_required_reason": "external_observation_not_app_verified" if external_observation else "",
    }


@dataclass
class SubmissionStep:
    name: str
    status: str
    detail: str
    screenshot: str = ""


@dataclass
class SubmissionRecord:
    run_id: str
    platform: str
    mode: str
    started_at: str
    transport: str = 'browser'
    ended_at: str = ""
    status: str = "running"
    error: str = ""
    job_url: str = ""
    resume_path: str = ""
    profile_path: str = ""
    headless: bool = True
    browser_channel: str = "chrome"
    external_l3_validation_run_id: str = ""
    external_l3_validation_path: str = ""
    live_inputs_redacted: bool = False
    input_artifacts: dict[str, object] = field(default_factory=dict)
    steps: list[SubmissionStep] = field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def make_run_id() -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y%m%d-%H%M%S")


class SubmissionRecorder:
    output_root: Path
    run_dir: Path
    screenshot_dir: Path
    log_yaml: Path
    log_json: Path
    record: SubmissionRecord
    _redaction_values: list[str]

    def __init__(self, output_root: Path, platform: str, mode: str, *, run_id: str | None = None, transport: str = 'browser') -> None:
        run_id = run_id or make_run_id()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', run_id):
            raise ValueError('invalid_submission_run_id')
        self.output_root = output_root
        self.run_dir = output_root / platform / run_id
        self.screenshot_dir = self.run_dir / "screenshots"
        self.log_yaml = self.run_dir / "submission_log.yaml"
        self.log_json = self.run_dir / "submission_log.json"
        self.record = SubmissionRecord(
            run_id=run_id,
            platform=platform,
            mode=mode,
            started_at=utc_now_iso(),
            transport=transport,
        )
        self._redaction_values = []
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def set_meta(
        self,
        job_url: str,
        resume_path: str,
        profile_path: str,
        headless: bool,
        browser_channel: str = "chrome",
        *,
        external_l3_validation_run_id: str = "",
        external_l3_validation_path: str = "",
        redaction_values: Iterable[str] = (),
        redact_inputs: bool = False,
    ) -> None:
        redact_live_inputs = bool(
            external_l3_validation_run_id or external_l3_validation_path or redact_inputs
        )
        if redact_live_inputs:
            values = [job_url, resume_path, profile_path, *redaction_values]
            for path_text in (resume_path, profile_path):
                if path_text:
                    values.append(str(Path(path_text).resolve()))
            self._redaction_values = _unique_redaction_values(
                values
            )
        else:
            self._redaction_values = []
        self.record.job_url = _REDACTED_LIVE_INPUT if redact_live_inputs else job_url
        self.record.resume_path = _REDACTED_LIVE_INPUT if redact_live_inputs else resume_path
        self.record.profile_path = _REDACTED_LIVE_INPUT if redact_live_inputs else profile_path
        self.record.headless = headless
        self.record.browser_channel = browser_channel
        self.record.external_l3_validation_run_id = external_l3_validation_run_id
        self.record.external_l3_validation_path = external_l3_validation_path
        self.record.live_inputs_redacted = redact_live_inputs
        self.record.input_artifacts = _input_artifacts(
            job_url=job_url,
            resume_path=resume_path,
            profile_path=profile_path,
            redact_file_names=redact_live_inputs,
        )

    @classmethod
    def load_existing(cls, log_path: Path) -> 'SubmissionRecorder':
        payload = json.loads(log_path.read_text(encoding='utf-8'))
        if payload['run_id'] != log_path.parent.name:
            raise ValueError('submission_record_identity_mismatch')
        steps = [SubmissionStep(**step) for step in payload.pop('steps')]
        instance = cls.__new__(cls)
        instance.run_dir = log_path.parent
        instance.output_root = log_path.parent.parent.parent
        instance.screenshot_dir = instance.run_dir / 'screenshots'
        instance.log_json = log_path
        instance.log_yaml = instance.run_dir / 'submission_log.yaml'
        instance.record = SubmissionRecord(**payload, steps=steps)
        instance._redaction_values = []  # 已落盘字段已经脱敏，新回执仅允许固定摘要。
        return instance

    def add_step(self, name: str, status: str, detail: str, screenshot: Path | None = None) -> None:
        screenshot_rel = ""
        if screenshot is not None and not self.record.live_inputs_redacted:
            screenshot_rel = str(screenshot.relative_to(self.run_dir))
        self.record.steps.append(
            SubmissionStep(
                name=name,
                status=status,
                detail=self._redact_live_text(detail),
                screenshot=screenshot_rel,
            )
        )

    def screenshot_path(self, step_name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in step_name)
        return self.screenshot_dir / f"{len(self.record.steps)+1:02d}_{safe}.png"

    def finish(self, status: str, error: str = "") -> None:
        self.record.status = status
        self.record.error = self._redact_live_text(error)
        self.record.ended_at = utc_now_iso()
        self._write_json()
        self._write_yaml()

    def confirmed_submission(self) -> bool:
        """只认可本次调用结束后实际落盘的真实提交成功记录。"""
        if self.record.mode != "submit" or self.record.status != "success" or self.record.error:
            return False
        try:
            payload = json.loads(self.log_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return (
            payload == asdict(self.record)
            and submission_required_steps_evidence(payload)["passed"] is True
        )

    def _redact_live_text(self, value: str) -> str:
        redacted = value
        for raw_value in self._redaction_values:
            redacted = redacted.replace(raw_value, _REDACTED_LIVE_INPUT)
        return redacted

    def _write_json(self) -> None:
        payload = {
            "run_id": self.record.run_id,
            "platform": self.record.platform,
            "mode": self.record.mode,
            "started_at": self.record.started_at,
            "transport": self.record.transport,
            "ended_at": self.record.ended_at,
            "status": self.record.status,
            "error": self.record.error,
            "job_url": self.record.job_url,
            "resume_path": self.record.resume_path,
            "profile_path": self.record.profile_path,
            "headless": self.record.headless,
            "browser_channel": self.record.browser_channel,
            "external_l3_validation_run_id": self.record.external_l3_validation_run_id,
            "external_l3_validation_path": self.record.external_l3_validation_path,
            "live_inputs_redacted": self.record.live_inputs_redacted,
            "input_artifacts": self.record.input_artifacts,
            "steps": [
                {
                    "name": s.name,
                    "status": s.status,
                    "detail": s.detail,
                    "screenshot": s.screenshot,
                }
                for s in self.record.steps
            ],
        }
        from tools.infra.persistence.review_queue import atomic_write_json
        atomic_write_json(self.log_json, payload)

    def _write_yaml(self) -> None:
        lines: list[str] = [
            f"run_id: \"{_escape(self.record.run_id)}\"",
            f"platform: \"{_escape(self.record.platform)}\"",
            f"mode: \"{_escape(self.record.mode)}\"",
            f"transport: \"{_escape(self.record.transport)}\"",
            f"started_at: \"{_escape(self.record.started_at)}\"",
            f"ended_at: \"{_escape(self.record.ended_at)}\"",
            f"status: \"{_escape(self.record.status)}\"",
            f"error: \"{_escape(self.record.error)}\"",
            f"job_url: \"{_escape(self.record.job_url)}\"",
            f"resume_path: \"{_escape(self.record.resume_path)}\"",
            f"profile_path: \"{_escape(self.record.profile_path)}\"",
            f"headless: {'true' if self.record.headless else 'false'}",
            f"browser_channel: \"{_escape(self.record.browser_channel)}\"",
            f"external_l3_validation_run_id: \"{_escape(self.record.external_l3_validation_run_id)}\"",
            f"external_l3_validation_path: \"{_escape(self.record.external_l3_validation_path)}\"",
            f"live_inputs_redacted: {'true' if self.record.live_inputs_redacted else 'false'}",
            "input_artifacts:",
            f"  job_url_scheme: \"{_escape(str(_nested_get(self.record.input_artifacts, 'job_url', 'scheme')))}\"",
            f"  job_url_hostname: \"{_escape(str(_nested_get(self.record.input_artifacts, 'job_url', 'hostname')))}\"",
            f"  job_url_raw_value_persisted: {'true' if _nested_get(self.record.input_artifacts, 'job_url', 'raw_value_persisted') else 'false'}",
            "  files:",
        ]
        for item in self.record.input_artifacts.get("files", []):
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    f"    - id: \"{_escape(str(item.get('id', '')))}\"",
                    f"      basename: \"{_escape(str(item.get('basename', '')))}\"",
                    f"      basename_persisted: {'true' if item.get('basename_persisted') else 'false'}",
                    f"      suffix: \"{_escape(str(item.get('suffix', '')))}\"",
                    f"      exists: {'true' if item.get('exists') else 'false'}",
                    f"      is_file: {'true' if item.get('is_file') else 'false'}",
                    f"      size_bytes: {int(item.get('size_bytes') or 0)}",
                    f"      sha256: \"{_escape(str(item.get('sha256', '')))}\"",
                    f"      raw_content_persisted: {'true' if item.get('raw_content_persisted') else 'false'}",
                ]
            )
        lines.extend(
            [
                "steps:",
            ]
        )
        for step in self.record.steps:
            lines.append(f"  - name: \"{_escape(step.name)}\"")
            lines.append(f"    status: \"{_escape(step.status)}\"")
            lines.append(f"    detail: \"{_escape(step.detail)}\"")
            lines.append(f"    screenshot: \"{_escape(step.screenshot)}\"")
        _ = self.log_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _unique_redaction_values(values: Iterable[str]) -> list[str]:
    unique = {str(value) for value in values if str(value)}
    return sorted(unique, key=len, reverse=True)


def _input_artifacts(
    *,
    job_url: str,
    resume_path: str,
    profile_path: str,
    redact_file_names: bool = False,
) -> dict[str, object]:
    parsed_job_url = urlparse(job_url)
    return {
        "job_url": {
            "present": bool(job_url),
            "scheme": parsed_job_url.scheme,
            "hostname": parsed_job_url.hostname or "",
            "supported_scheme": parsed_job_url.scheme in {"http", "https"},
            "raw_value_persisted": False,
        },
        "files": [
            _file_artifact(
                artifact_id="resume_pdf",
                path_text=resume_path,
                expected_suffixes={".pdf"},
                redact_file_name=redact_file_names,
            ),
            _file_artifact(
                artifact_id="profile_yaml",
                path_text=profile_path,
                expected_suffixes={".yaml", ".yml"},
                redact_file_name=redact_file_names,
            ),
        ],
    }


def _file_artifact(
    *,
    artifact_id: str,
    path_text: str,
    expected_suffixes: set[str],
    redact_file_name: bool = False,
) -> dict[str, object]:
    provided = bool(path_text)
    path = Path(path_text) if provided else Path("")
    suffix = path.suffix.lower() if provided else ""
    exists = provided and path.exists()
    is_file = exists and path.is_file()
    basename = _REDACTED_LIVE_INPUT if provided and redact_file_name else path.name
    return {
        "id": artifact_id,
        "provided": provided,
        "basename": basename if provided else "",
        "basename_persisted": bool(provided and not redact_file_name),
        "suffix": suffix,
        "expected_suffixes": sorted(expected_suffixes),
        "suffix_valid": suffix in expected_suffixes,
        "exists": exists,
        "is_file": is_file,
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


def _nested_get(payload: dict[str, object], *keys: str) -> object:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key, "")
    return current
