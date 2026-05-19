from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReadinessStep:
    name: str
    status: str
    command: tuple[str, ...]
    evidence: str
    message: str
    stdout_tail: str = ""
    stderr_tail: str = ""


@dataclass(frozen=True)
class ReadinessReport:
    run_id: str
    status: str
    generated_at: str
    include_gui: bool
    steps: tuple[ReadinessStep, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "generated_at": self.generated_at,
            "include_gui": self.include_gui,
            "steps": [
                {
                    "name": step.name,
                    "status": step.status,
                    "command": list(step.command),
                    "evidence": step.evidence,
                    "message": step.message,
                    "stdout_tail": step.stdout_tail,
                    "stderr_tail": step.stderr_tail,
                }
                for step in self.steps
            ],
        }


def build_run_id() -> str:
    return datetime.now(timezone.utc).strftime("demo_ready_%Y%m%d%H%M%S")


def run_readiness(
    *,
    root: Path,
    run_id: str,
    include_gui: bool,
    timeout_seconds: int,
) -> ReadinessReport:
    steps = [
        _run_step(
            root=root,
            name="core demo",
            command=(
                sys.executable,
                "-m",
                "tools.acceptance.demo_run",
                "--run-id",
                run_id,
            ),
            timeout_seconds=timeout_seconds,
            evidence=str(root / "outputs" / "demo" / run_id / "demo-report.md"),
            success_message="Core evidence-first demo artifacts are complete.",
            failure_message="Core demo failed; inspect the demo report and stdout/stderr tails.",
        )
    ]

    if include_gui:
        steps.append(
            _run_step(
                root=root,
                name="quick run native verifier",
                command=("pnpm", "--dir", "ui", "run", "e2e:quick-run"),
                timeout_seconds=timeout_seconds,
                evidence=str(root / "ui" / "test-results" / "quick-run-native"),
                success_message="Quick Run native verifier completed.",
                failure_message="Quick Run native verifier failed; inspect ui/test-results/quick-run-native.",
            )
        )

    status = "pass" if all(step.status == "pass" for step in steps) else "fail"
    return ReadinessReport(
        run_id=run_id,
        status=status,
        generated_at=_utcnow(),
        include_gui=include_gui,
        steps=tuple(steps),
    )


def write_readiness_report(root: Path, report: ReadinessReport) -> tuple[Path, Path]:
    output_dir = root / "outputs" / "demo" / report.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "readiness-report.json"
    markdown_path = output_dir / "readiness-report.md"
    json_path.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the PiProofForge pre-demo readiness checklist"
    )
    _ = parser.add_argument("--run-id", default="", help="Stable readiness run id")
    _ = parser.add_argument(
        "--include-gui",
        action="store_true",
        help="Also run the native Quick Run verifier",
    )
    _ = parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=240,
        help="Maximum time for each readiness step",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    run_id = str(args.run_id).strip() or build_run_id()
    report = run_readiness(
        root=root,
        run_id=run_id,
        include_gui=bool(args.include_gui),
        timeout_seconds=int(args.timeout_seconds),
    )
    json_path, markdown_path = write_readiness_report(root, report)
    print(f"[demo-readiness] status: {report.status}")
    print(f"[demo-readiness] report: {json_path}")
    print(f"[demo-readiness] report: {markdown_path}")
    return 0 if report.status == "pass" else 1


def _run_step(
    *,
    root: Path,
    name: str,
    command: tuple[str, ...],
    timeout_seconds: int,
    evidence: str,
    success_message: str,
    failure_message: str,
) -> ReadinessStep:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return ReadinessStep(
            name=name,
            status="fail",
            command=command,
            evidence=evidence,
            message=f"Step timed out after {timeout_seconds} seconds.",
            stdout_tail=str(exc.stdout or "")[-4000:],
            stderr_tail=str(exc.stderr or "")[-4000:],
        )

    return ReadinessStep(
        name=name,
        status="pass" if completed.returncode == 0 else "fail",
        command=command,
        evidence=evidence,
        message=success_message if completed.returncode == 0 else failure_message,
        stdout_tail=completed.stdout[-4000:],
        stderr_tail=completed.stderr[-4000:],
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _render_markdown(report: ReadinessReport) -> str:
    lines = [
        "# PiProofForge Demo Readiness",
        "",
        f"- Run ID: `{report.run_id}`",
        f"- Status: `{report.status}`",
        f"- Generated At: `{report.generated_at}`",
        f"- Include GUI: `{str(report.include_gui).lower()}`",
        "",
        "## Steps",
        "",
        "| Step | Status | Evidence | Message |",
        "|---|---:|---|---|",
    ]
    for step in report.steps:
        lines.append(
            f"| {step.name} | {step.status} | `{step.evidence}` | {step.message} |"
        )
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
