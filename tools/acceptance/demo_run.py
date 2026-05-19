from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_EVENT_TYPES: tuple[str, ...] = (
    "PIPELINE_START",
    "PIPELINE_STEP_SUCCESS",
    "PIPELINE_DONE",
)

REQUIRED_ARTIFACT_KEYS: tuple[str, ...] = (
    "evidence",
    "matching",
    "resume_dir",
    "scorecard",
    "run_record",
)


@dataclass(frozen=True)
class DemoCheck:
    name: str
    status: str
    evidence: str
    message: str


@dataclass(frozen=True)
class DemoReport:
    run_id: str
    status: str
    generated_at: str
    command: tuple[str, ...]
    artifacts: dict[str, str]
    checks: tuple[DemoCheck, ...]
    stdout_tail: str
    stderr_tail: str

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "generated_at": self.generated_at,
            "command": list(self.command),
            "artifacts": self.artifacts,
            "checks": [check.__dict__ for check in self.checks],
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


def build_run_id() -> str:
    return datetime.now(timezone.utc).strftime("demo_%Y%m%d%H%M%S")


def run_demo_pipeline(
    *,
    root: Path,
    run_id: str,
    raw_path: str,
    job_profile_path: str,
    timeout_seconds: int,
) -> tuple[int, tuple[str, ...], str, str]:
    command = (
        sys.executable,
        str(root / "tools" / "run_pipeline.py"),
        "--raw",
        raw_path,
        "--job-profile",
        job_profile_path,
        "--run-id",
        run_id,
    )
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        cwd=str(root),
    )
    return completed.returncode, command, completed.stdout, completed.stderr


def build_demo_report(
    *,
    root: Path,
    run_id: str,
    command: tuple[str, ...],
    exit_code: int,
    stdout: str,
    stderr: str,
) -> DemoReport:
    summary_path = root / "outputs" / "agent_runs" / run_id / "summary.json"
    checks: list[DemoCheck] = []
    artifacts: dict[str, str] = {}

    checks.append(
        _check_file(
            root=root,
            label="pipeline summary",
            path=summary_path,
            required=True,
        )
    )
    summary = _load_json_object(summary_path)
    summary_artifacts = summary.get("artifacts", {})
    if isinstance(summary_artifacts, dict):
        artifacts = {
            str(key): str(value)
            for key, value in summary_artifacts.items()
            if isinstance(key, str) and isinstance(value, str)
        }

    checks.append(
        DemoCheck(
            name="pipeline exit",
            status="pass" if exit_code == 0 else "fail",
            evidence=str(exit_code),
            message="Pipeline exited successfully."
            if exit_code == 0
            else "Pipeline exited with a non-zero status.",
        )
    )

    for key in REQUIRED_ARTIFACT_KEYS:
        path_value = artifacts.get(key, "")
        checks.append(
            _check_file(
                root=root,
                label=f"artifact:{key}",
                path=_resolve_report_path(root, path_value),
                required=True,
            )
        )

    resume_dir = _resolve_report_path(root, artifacts.get("resume_dir", ""))
    for variant in ("A", "B"):
        checks.append(
            _check_file(
                root=root,
                label=f"resume {variant}",
                path=resume_dir / f"resume_mr-{run_id}_{variant}.md"
                if resume_dir is not None
                else None,
                required=True,
            )
        )

    run_log = _resolve_report_path(root, artifacts.get("run_record", ""))
    checks.extend(_check_run_events(run_log))

    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    return DemoReport(
        run_id=run_id,
        status=status,
        generated_at=_utcnow(),
        command=command,
        artifacts=artifacts,
        checks=tuple(checks),
        stdout_tail=stdout[-4000:],
        stderr_tail=stderr[-4000:],
    )


def write_demo_report(root: Path, report: DemoReport) -> tuple[Path, Path]:
    output_dir = root / "outputs" / "demo" / report.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "demo-report.json"
    markdown_path = output_dir / "demo-report.md"
    json_path.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic local PiProofForge demo acceptance flow"
    )
    _ = parser.add_argument("--run-id", default="", help="Stable demo run id")
    _ = parser.add_argument(
        "--raw",
        default="tools/sample_raw.txt",
        help="Raw material fixture used by the demo",
    )
    _ = parser.add_argument(
        "--job-profile",
        default="job_profiles/jp-2026-001.yaml",
        help="Job profile fixture used by the demo",
    )
    _ = parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="Maximum time to allow the local pipeline to run",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    run_id = str(args.run_id).strip() or build_run_id()
    exit_code, command, stdout, stderr = run_demo_pipeline(
        root=root,
        run_id=run_id,
        raw_path=str(args.raw),
        job_profile_path=str(args.job_profile),
        timeout_seconds=int(args.timeout_seconds),
    )
    report = build_demo_report(
        root=root,
        run_id=run_id,
        command=command,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
    )
    json_path, markdown_path = write_demo_report(root, report)
    print(f"[demo] status: {report.status}")
    print(f"[demo] report: {json_path}")
    print(f"[demo] report: {markdown_path}")
    return 0 if report.status == "pass" else 1


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _resolve_report_path(root: Path, value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def _check_file(
    *, root: Path, label: str, path: Path | None, required: bool
) -> DemoCheck:
    if path is None:
        return DemoCheck(
            name=label,
            status="fail" if required else "blocked",
            evidence="",
            message="Artifact path is missing.",
        )
    display_path = _display_path(root, path)
    if not path.exists():
        return DemoCheck(
            name=label,
            status="fail" if required else "blocked",
            evidence=display_path,
            message="Expected artifact does not exist.",
        )
    if path.is_file() and path.stat().st_size == 0:
        return DemoCheck(
            name=label,
            status="fail",
            evidence=display_path,
            message="Expected artifact is empty.",
        )
    return DemoCheck(
        name=label,
        status="pass",
        evidence=display_path,
        message="Artifact is present.",
    )


def _check_run_events(run_log: Path | None) -> tuple[DemoCheck, ...]:
    if run_log is None:
        return tuple(
            DemoCheck(
                name=f"event:{required}",
                status="fail",
                evidence="",
                message="Run log path is missing.",
            )
            for required in REQUIRED_EVENT_TYPES
        )
    events_raw = _load_json_list(run_log)
    event_types = [
        str(item.get("event_type", ""))
        for item in events_raw
        if isinstance(item, dict)
    ]
    checks: list[DemoCheck] = []
    for required in REQUIRED_EVENT_TYPES:
        checks.append(
            DemoCheck(
                name=f"event:{required}",
                status="pass" if required in event_types else "fail",
                evidence=", ".join(event_types),
                message="Required run event is recorded."
                if required in event_types
                else "Required run event is missing.",
            )
        )
    return tuple(checks)


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_json_list(path: Path) -> list[Any]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _render_markdown(report: DemoReport) -> str:
    lines = [
        "# PiProofForge Demo Report",
        "",
        f"- Run ID: `{report.run_id}`",
        f"- Status: `{report.status}`",
        f"- Generated At: `{report.generated_at}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Evidence | Message |",
        "|---|---:|---|---|",
    ]
    for check in report.checks:
        lines.append(
            f"| {check.name} | {check.status} | `{check.evidence}` | {check.message} |"
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
        ]
    )
    for key, value in sorted(report.artifacts.items()):
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
