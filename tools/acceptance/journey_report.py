from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.acceptance.journey_contract import JourneyContract, load_journey_contract


ALLOWED_REPORT_STATUSES = {"pass", "fail", "blocked", "not_started"}
STATUS_ORDER = ("fail", "blocked", "pass", "not_started")


@dataclass(frozen=True)
class JourneyStepResult:
    status: str
    evidence: str = ""
    message: str = ""
    phase: str = ""

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_REPORT_STATUSES:
            raise ValueError(f"invalid journey step status: {self.status}")


@dataclass(frozen=True)
class JourneyReportStep:
    case_id: str
    rule_id: str
    level: str
    stage: str
    phase: str
    status: str
    evidence: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {
            "case_id": self.case_id,
            "rule_id": self.rule_id,
            "level": self.level,
            "stage": self.stage,
            "phase": self.phase,
            "status": self.status,
            "evidence": self.evidence,
            "message": self.message,
        }


@dataclass(frozen=True)
class JourneyReport:
    run_id: str
    status: str
    generated_at: str
    contract_version: str
    steps: tuple[JourneyReportStep, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "generated_at": self.generated_at,
            "contract_version": self.contract_version,
            "summary": summarize_steps(self.steps),
            "steps": [step.to_json() for step in self.steps],
        }


def build_journey_report(
    contract: JourneyContract,
    *,
    run_id: str,
    generated_at: str | None = None,
    results: dict[str, JourneyStepResult] | None = None,
) -> JourneyReport:
    result_map = results or {}
    steps: list[JourneyReportStep] = []

    for case_contract in contract.case_contracts:
        for rule in case_contract.acceptance_rules:
            override = result_map.get(rule.rule_id)
            steps.append(
                JourneyReportStep(
                    case_id=rule.case_id,
                    rule_id=rule.rule_id,
                    level=rule.level,
                    stage=rule.stage,
                    phase=override.phase if override else "",
                    status=override.status if override else rule.status,
                    evidence=override.evidence if override else rule.evidence,
                    message=override.message if override and override.message else rule.message,
                )
            )

    return JourneyReport(
        run_id=run_id,
        status=overall_status(tuple(steps)),
        generated_at=generated_at or _utcnow(),
        contract_version=contract.version,
        steps=tuple(steps),
    )


def build_artifact_check_step(
    *,
    case_id: str,
    rule_id: str,
    level: str,
    stage: str,
    phase: str,
    artifact_path: Path,
    artifact_label: str,
) -> JourneyReportStep:
    evidence = str(artifact_path)
    if artifact_path.exists() and artifact_path.is_file() and artifact_path.stat().st_size > 0:
        return JourneyReportStep(
            case_id=case_id,
            rule_id=rule_id,
            level=level,
            stage=stage,
            phase=phase,
            status="pass",
            evidence=evidence,
            message=f"{phase} artifact exists: {artifact_label}.",
        )

    return JourneyReportStep(
        case_id=case_id,
        rule_id=rule_id,
        level=level,
        stage=stage,
        phase=phase,
        status="fail",
        evidence=evidence,
        message=f"{phase} artifact missing or empty: {artifact_label} at {artifact_path}.",
    )


def write_journey_report(root: Path, report: JourneyReport) -> tuple[Path, Path]:
    output_dir = root / "outputs" / "acceptance" / report.run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "journey-report.json"
    markdown_path = output_dir / "journey-report.md"

    import json

    json_path.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a JSON/Markdown journey acceptance report from the journey contract."
    )
    _ = parser.add_argument("--contract", default="acceptance/journey_contract.yaml")
    _ = parser.add_argument("--run-id", default="")
    _ = parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)

    root = Path(str(args.root)).resolve()
    contract_path = root / str(args.contract)
    run_id = str(args.run_id).strip() or _default_run_id()
    contract = load_journey_contract(contract_path)
    report = build_journey_report(contract, run_id=run_id)
    json_path, markdown_path = write_journey_report(root, report)
    print(f"[journey-report] status: {report.status}")
    print(f"[journey-report] report: {json_path}")
    print(f"[journey-report] report: {markdown_path}")
    return 0


def render_markdown(report: JourneyReport) -> str:
    summary = summarize_steps(report.steps)
    lines = [
        "# PiProofForge Journey Acceptance",
        "",
        f"- Run ID: `{report.run_id}`",
        f"- Status: `{report.status}`",
        f"- Generated At: `{report.generated_at}`",
        f"- Contract Version: `{report.contract_version}`",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|---|---:|",
    ]
    for status in STATUS_ORDER:
        lines.append(f"| `{status}` | {summary[status]} |")

    lines.extend(
        [
            "",
            "## Steps",
            "",
            "| Case | Rule | Level | Stage | Status | Evidence | Message |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for step in report.steps:
        stage = step.stage if not step.phase else f"{step.stage}/{step.phase}"
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(step.case_id),
                    _md(step.rule_id),
                    _md(step.level),
                    _md(stage),
                    f"`{step.status}`",
                    _md(step.evidence),
                    _md(step.message),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def summarize_steps(steps: tuple[JourneyReportStep, ...]) -> dict[str, int]:
    summary = {status: 0 for status in STATUS_ORDER}
    for step in steps:
        summary[step.status] = summary.get(step.status, 0) + 1
    return summary


def overall_status(steps: tuple[JourneyReportStep, ...]) -> str:
    statuses = {step.status for step in steps}
    if "fail" in statuses:
        return "fail"
    if "blocked" in statuses:
        return "blocked"
    if statuses == {"pass"}:
        return "pass"
    return "not_started"


def _md(value: str) -> str:
    escaped = value.replace("|", "\\|").replace("\n", " ")
    return escaped or "-"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("journey_%Y%m%d%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
