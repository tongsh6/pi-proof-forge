from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path


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
    ended_at: str = ""
    status: str = "running"
    error: str = ""
    job_url: str = ""
    resume_path: str = ""
    profile_path: str = ""
    headless: bool = True
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

    def __init__(self, output_root: Path, platform: str, mode: str) -> None:
        run_id = make_run_id()
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
        )
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def set_meta(self, job_url: str, resume_path: str, profile_path: str, headless: bool) -> None:
        self.record.job_url = job_url
        self.record.resume_path = resume_path
        self.record.profile_path = profile_path
        self.record.headless = headless

    def add_step(self, name: str, status: str, detail: str, screenshot: Path | None = None) -> None:
        screenshot_rel = ""
        if screenshot is not None:
            screenshot_rel = str(screenshot.relative_to(self.run_dir))
        self.record.steps.append(
            SubmissionStep(
                name=name,
                status=status,
                detail=detail,
                screenshot=screenshot_rel,
            )
        )

    def screenshot_path(self, step_name: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in step_name)
        return self.screenshot_dir / f"{len(self.record.steps)+1:02d}_{safe}.png"

    def finish(self, status: str, error: str = "") -> None:
        self.record.status = status
        self.record.error = error
        self.record.ended_at = utc_now_iso()
        self._write_json()
        self._write_yaml()

    def _write_json(self) -> None:
        payload = {
            "run_id": self.record.run_id,
            "platform": self.record.platform,
            "mode": self.record.mode,
            "started_at": self.record.started_at,
            "ended_at": self.record.ended_at,
            "status": self.record.status,
            "error": self.record.error,
            "job_url": self.record.job_url,
            "resume_path": self.record.resume_path,
            "profile_path": self.record.profile_path,
            "headless": self.record.headless,
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
        _ = self.log_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_yaml(self) -> None:
        lines: list[str] = [
            f"run_id: \"{_escape(self.record.run_id)}\"",
            f"platform: \"{_escape(self.record.platform)}\"",
            f"mode: \"{_escape(self.record.mode)}\"",
            f"started_at: \"{_escape(self.record.started_at)}\"",
            f"ended_at: \"{_escape(self.record.ended_at)}\"",
            f"status: \"{_escape(self.record.status)}\"",
            f"error: \"{_escape(self.record.error)}\"",
            f"job_url: \"{_escape(self.record.job_url)}\"",
            f"resume_path: \"{_escape(self.record.resume_path)}\"",
            f"profile_path: \"{_escape(self.record.profile_path)}\"",
            f"headless: {'true' if self.record.headless else 'false'}",
            "steps:",
        ]
        for step in self.record.steps:
            lines.append(f"  - name: \"{_escape(step.name)}\"")
            lines.append(f"    status: \"{_escape(step.status)}\"")
            lines.append(f"    detail: \"{_escape(step.detail)}\"")
            lines.append(f"    screenshot: \"{_escape(step.screenshot)}\"")
        _ = self.log_yaml.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
