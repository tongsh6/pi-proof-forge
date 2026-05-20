from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.acceptance.journey_contract import load_journey_contract
from tools.acceptance.journey_report import (
    JourneyStepResult,
    build_journey_report,
    write_journey_report,
)


VALID_LEVELS = ("L1", "L2", "L3")
L1_SCENARIO_TESTS = (
    (
        "first_launch_configure_lm_studio",
        "tests/acceptance/test_scenario_first_launch_configure_lm_studio.py",
        (
            "LM Studio settings, structured connection check, and run-page provider "
            "summary validation passed."
        ),
    ),
    (
        "setup_profile_and_material_library",
        "tests/acceptance/test_scenario_setup_profile_and_material_library.py",
        (
            "Profile, uploaded resume, raw material library, readiness feedback, "
            "and evidence material source validation passed."
        ),
    ),
)


@dataclass(frozen=True)
class AcceptanceStep:
    level: str
    name: str
    status: str
    command: tuple[str, ...]
    evidence: str
    message: str
    stdout_tail: str = ""
    stderr_tail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "name": self.name,
            "status": self.status,
            "command": list(self.command),
            "evidence": self.evidence,
            "message": self.message,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
        }


@dataclass(frozen=True)
class AcceptanceReport:
    run_id: str
    status: str
    generated_at: str
    levels: tuple[str, ...]
    steps: tuple[AcceptanceStep, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "generated_at": self.generated_at,
            "levels": list(self.levels),
            "summary": summarize_by_level(self.steps),
            "steps": [step.to_json() for step in self.steps],
        }


def build_run_id() -> str:
    return datetime.now(timezone.utc).strftime("acceptance_%Y%m%d%H%M%S")


def run_acceptance(
    *,
    root: Path,
    run_id: str,
    levels: tuple[str, ...],
    timeout_seconds: int,
) -> AcceptanceReport:
    normalized_levels = _normalize_levels(levels)
    steps: list[AcceptanceStep] = []

    for level in normalized_levels:
        if level == "L1":
            steps.extend(_run_l1_steps(root=root, timeout_seconds=timeout_seconds))
            continue
        steps.append(_not_started_step(level))

    return AcceptanceReport(
        run_id=run_id,
        status=_overall_status(tuple(steps)),
        generated_at=_utcnow(),
        levels=normalized_levels,
        steps=tuple(steps),
    )


def write_acceptance_report(
    root: Path,
    report: AcceptanceReport,
) -> tuple[Path, Path, Path, Path]:
    output_dir = root / "outputs" / "acceptance" / report.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "acceptance-report.json"
    markdown_path = output_dir / "acceptance-report.md"
    json_path.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")

    contract_path = root / "acceptance" / "journey_contract.yaml"
    if not contract_path.exists():
        contract_path = Path(__file__).resolve().parents[2] / "acceptance" / "journey_contract.yaml"
    journey_report = build_journey_report(
        load_journey_contract(contract_path),
        run_id=report.run_id,
        results=_journey_results(report),
    )
    journey_json_path, journey_markdown_path = write_journey_report(root, journey_report)
    return json_path, markdown_path, journey_json_path, journey_markdown_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run PiProofForge journey acceptance levels and write reports."
    )
    _ = parser.add_argument("--run-id", default="", help="Stable acceptance run id")
    _ = parser.add_argument(
        "--level",
        action="append",
        choices=VALID_LEVELS,
        help="Acceptance level to run. Defaults to L1. Repeat for multiple levels.",
    )
    _ = parser.add_argument(
        "--all",
        action="store_true",
        help="Run all implemented levels and report gated levels as not_started.",
    )
    _ = parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=240,
        help="Maximum time for each executable acceptance step",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    run_id = str(args.run_id).strip() or build_run_id()
    levels = VALID_LEVELS if bool(args.all) else tuple(args.level or ("L1",))
    report = run_acceptance(
        root=root,
        run_id=run_id,
        levels=levels,
        timeout_seconds=int(args.timeout_seconds),
    )
    json_path, markdown_path, journey_json_path, journey_markdown_path = (
        write_acceptance_report(root, report)
    )
    print(f"[acceptance] status: {report.status}")
    print(f"[acceptance] report: {json_path}")
    print(f"[acceptance] report: {markdown_path}")
    print(f"[acceptance] journey: {journey_json_path}")
    print(f"[acceptance] journey: {journey_markdown_path}")
    return 1 if report.status == "fail" else 0


def summarize_by_level(steps: tuple[AcceptanceStep, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for level in VALID_LEVELS:
        level_steps = [step for step in steps if step.level == level]
        if not level_steps:
            continue
        result[level] = _overall_status(tuple(level_steps))
    return result


def _run_l1_steps(*, root: Path, timeout_seconds: int) -> tuple[AcceptanceStep, ...]:
    return tuple(
        _run_l1_scenario_step(
            root=root,
            timeout_seconds=timeout_seconds,
            scenario_name=scenario_name,
            test_path=test_path,
            pass_message=pass_message,
        )
        for scenario_name, test_path, pass_message in L1_SCENARIO_TESTS
    )


def _run_l1_scenario_step(
    *,
    root: Path,
    timeout_seconds: int,
    scenario_name: str,
    test_path: str,
    pass_message: str,
) -> AcceptanceStep:
    command = (
        sys.executable,
        "-m",
        "pytest",
        test_path,
        "-q",
    )
    evidence = str(root / test_path)
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
        return AcceptanceStep(
            level="L1",
            name=scenario_name,
            status="fail",
            command=command,
            evidence=evidence,
            message=f"L1 scenario validation timed out after {timeout_seconds} seconds.",
            stdout_tail=str(exc.stdout or "")[-4000:],
            stderr_tail=str(exc.stderr or "")[-4000:],
        )

    passed = completed.returncode == 0
    return AcceptanceStep(
        level="L1",
        name=scenario_name,
        status="pass" if passed else "fail",
        command=command,
        evidence=evidence,
        message=(
            pass_message
            if passed
            else f"{scenario_name} L1 scenario validation failed; inspect stdout/stderr tails."
        ),
        stdout_tail=completed.stdout[-4000:],
        stderr_tail=completed.stderr[-4000:],
    )


def _not_started_step(level: str) -> AcceptanceStep:
    return AcceptanceStep(
        level=level,
        name=f"{level.lower()}_journey_validation",
        status="not_started",
        command=(),
        evidence="",
        message=f"{level} is gated until its implementation plan reaches done.",
    )


def _journey_results(report: AcceptanceReport) -> dict[str, JourneyStepResult]:
    results: dict[str, JourneyStepResult] = {}
    lm_step = _find_step(report, "first_launch_configure_lm_studio")
    if lm_step is not None:
        status = "pass" if lm_step.status == "pass" else "fail"
        results["lm_studio_config_persisted"] = JourneyStepResult(
            status=status,
            evidence=lm_step.evidence,
            message=lm_step.message,
        )
        results["lm_studio_connection_check_structured"] = JourneyStepResult(
            status=status,
            evidence=lm_step.evidence,
            message=lm_step.message,
        )

    materials_step = _find_step(report, "setup_profile_and_material_library")
    if materials_step is not None:
        status = "pass" if materials_step.status == "pass" else "fail"
        results["profile_and_materials_persisted"] = JourneyStepResult(
            status=status,
            evidence=materials_step.evidence,
            message=materials_step.message,
        )

    l2_step = next((step for step in report.steps if step.level == "L2"), None)
    if l2_step is not None and l2_step.status != "not_started":
        results["lm_studio_visible_to_run_pages"] = JourneyStepResult(
            status="pass" if l2_step.status == "pass" else "fail",
            evidence=l2_step.evidence,
            message=l2_step.message,
        )
    return results


def _find_step(report: AcceptanceReport, name: str) -> AcceptanceStep | None:
    return next((step for step in report.steps if step.name == name), None)


def _normalize_levels(levels: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    normalized: list[str] = []
    for level in levels:
        if level not in VALID_LEVELS:
            raise ValueError(f"unsupported acceptance level: {level}")
        if level not in seen:
            normalized.append(level)
            seen.add(level)
    return tuple(normalized or ("L1",))


def _overall_status(steps: tuple[AcceptanceStep, ...]) -> str:
    statuses = {step.status for step in steps}
    if "fail" in statuses:
        return "fail"
    if statuses == {"not_started"}:
        return "not_started"
    return "pass"


def _render_markdown(report: AcceptanceReport) -> str:
    summary = summarize_by_level(report.steps)
    lines = [
        "# PiProofForge Acceptance Runner",
        "",
        f"- Run ID: `{report.run_id}`",
        f"- Status: `{report.status}`",
        f"- Generated At: `{report.generated_at}`",
        f"- Levels: `{', '.join(report.levels)}`",
        "",
        "## Summary",
        "",
        "| Level | Status |",
        "|---|---:|",
    ]
    for level in report.levels:
        lines.append(f"| `{level}` | `{summary.get(level, 'not_started')}` |")
    lines.extend(
        [
            "",
            "## Steps",
            "",
            "| Level | Step | Status | Evidence | Message |",
            "|---|---|---:|---|---|",
        ]
    )
    for step in report.steps:
        lines.append(
            f"| `{step.level}` | {step.name} | `{step.status}` | `{step.evidence or '-'}` | {step.message} |"
        )
    lines.append("")
    return "\n".join(lines)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


if __name__ == "__main__":
    raise SystemExit(main())
