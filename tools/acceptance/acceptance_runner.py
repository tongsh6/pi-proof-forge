from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

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
    (
        "generate_review_and_complete_evidence_card",
        "tests/acceptance/test_scenario_generate_review_and_complete_evidence_card.py",
        (
            "Markdown material draft generation, strict JSON handling, human review "
            "gate, traceability, and candidate-pool eligibility validation passed."
        ),
    ),
    (
        "setup_job_target",
        "tests/acceptance/test_scenario_setup_job_target.py",
        (
            "Pasted JD parsing, strict JSON handling, human review gate, active target "
            "eligibility, source URL check, and Job Lead linking validation passed."
        ),
    ),
    (
        "quick_run_generate_and_evaluate_resume",
        "tests/acceptance/test_scenario_quick_run_generate_and_evaluate_resume.py",
        (
            "Complete target selection, eligible evidence selection, LLM-required "
            "Quick Run outputs, PDF export, scorecard, gap tasks, and traceability "
            "validation passed."
        ),
    ),
    (
        "agent_run_guided_batch",
        "tests/acceptance/test_scenario_agent_run_guided_batch.py",
        (
            "Guided Agent Run preflight, selected candidates, gate events, review "
            "queue, run log traceability, and no-submit delivery plan validation passed."
        ),
    ),
    (
        "channel_session_setup",
        "tests/acceptance/test_scenario_channel_session_setup.py",
        (
            "Channel session setup, manual login boundary, positive-signal validity, "
            "credential/challenge safety, session metadata, and selected-channel clear "
            "validation passed."
        ),
    ),
    (
        "submission_check_mode",
        "tests/acceptance/test_scenario_submission_check_mode.py",
        (
            "Submission check-mode preflight, shared session reuse, target and resume "
            "verification, rate limit, attachment status, submission log, and "
            "submit-skipped safety validation passed."
        ),
    ),
    (
        "feedback_iteration_after_check_mode",
        "tests/acceptance/test_scenario_feedback_iteration_after_check_mode.py",
        (
            "Feedback iteration listing, selected action gating, source snapshot, "
            "artifact preservation, evidence-linked comparison, new resume version, "
            "and next check-mode candidate validation passed."
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
            steps.extend(
                _run_l1_steps(
                    root=root,
                    run_id=run_id,
                    timeout_seconds=timeout_seconds,
                )
            )
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


def _run_l1_steps(
    *,
    root: Path,
    run_id: str,
    timeout_seconds: int,
) -> tuple[AcceptanceStep, ...]:
    scenario_steps = tuple(
        _run_l1_scenario_step(
            root=root,
            timeout_seconds=timeout_seconds,
            scenario_name=scenario_name,
            test_path=test_path,
            pass_message=pass_message,
        )
        for scenario_name, test_path, pass_message in L1_SCENARIO_TESTS
    )
    return scenario_steps + (
        _run_closed_loop_audit_step(root=root, run_id=run_id, prior_steps=scenario_steps),
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


def _run_closed_loop_audit_step(
    *,
    root: Path,
    run_id: str,
    prior_steps: tuple[AcceptanceStep, ...],
) -> AcceptanceStep:
    command = (
        "internal",
        "closed_loop_e2e_audit",
    )
    output_dir = root / "outputs" / "acceptance" / run_id
    audit_json_path = output_dir / "closed-loop-audit.json"
    audit_md_path = output_dir / "closed-loop-audit.md"
    required_inputs = (
        root / "acceptance" / "journey_contract.yaml",
        root / "acceptance" / "journey_implementation_matrix.yaml",
    )
    if any(not path.exists() for path in required_inputs):
        return AcceptanceStep(
            level="L1",
            name="closed_loop_e2e_audit",
            status="not_started",
            command=command,
            evidence=str(audit_json_path),
            message="Closed-loop audit requires a project root with acceptance contracts.",
        )
    try:
        audit = _build_closed_loop_audit(root=root, run_id=run_id, prior_steps=prior_steps)
        output_dir.mkdir(parents=True, exist_ok=True)
        audit_json_path.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        audit_md_path.write_text(_render_closed_loop_audit_markdown(audit), encoding="utf-8")
    except Exception as exc:
        return AcceptanceStep(
            level="L1",
            name="closed_loop_e2e_audit",
            status="fail",
            command=command,
            evidence=str(audit_json_path),
            message=f"Closed-loop audit failed: {exc}",
        )

    failed = [check for check in audit["checks"] if check["status"] != "pass"]
    return AcceptanceStep(
        level="L1",
        name="closed_loop_e2e_audit",
        status="fail" if failed else "pass",
        command=command,
        evidence=str(audit_json_path),
        message=(
            "Closed-loop audit passed: L1 scenarios, journey rules, native evidence, "
            "and cross-stage traceability are connected."
            if not failed
            else f"Closed-loop audit found {len(failed)} failing check(s)."
        ),
    )


def _build_closed_loop_audit(
    *,
    root: Path,
    run_id: str,
    prior_steps: tuple[AcceptanceStep, ...],
) -> dict[str, Any]:
    contract = load_journey_contract(root / "acceptance" / "journey_contract.yaml")
    partial_report = AcceptanceReport(
        run_id=run_id,
        status=_overall_status(prior_steps),
        generated_at=_utcnow(),
        levels=("L1",),
        steps=prior_steps,
    )
    journey_report = build_journey_report(
        contract,
        run_id=run_id,
        results=_journey_results(partial_report),
    )

    matrix = yaml.safe_load(
        (root / "acceptance" / "journey_implementation_matrix.yaml").read_text(
            encoding="utf-8"
        )
    )
    checks = [
        _audit_l1_scenarios(contract.selected_cases, prior_steps),
        _audit_journey_l1_rules(journey_report.to_json()),
        _audit_deep_evidence(root, matrix),
        _audit_native_traceability(root),
    ]
    return {
        "run_id": run_id,
        "status": "pass" if all(check["status"] == "pass" for check in checks) else "fail",
        "generated_at": _utcnow(),
        "checks": checks,
        "journey_summary": journey_report.to_json()["summary"],
        "audited_steps": [step.name for step in prior_steps],
    }


def _audit_l1_scenarios(
    selected_cases: tuple[str, ...],
    prior_steps: tuple[AcceptanceStep, ...],
) -> dict[str, Any]:
    step_by_name = {step.name: step for step in prior_steps}
    missing = [case_id for case_id in selected_cases if case_id not in step_by_name]
    failing = [
        step.name
        for step in prior_steps
        if step.name in selected_cases and step.status != "pass"
    ]
    return {
        "id": "all_l1_scenarios_in_runner",
        "status": "pass" if not missing and not failing else "fail",
        "message": "All selected L1 scenarios are present and passing.",
        "details": {
            "selected_cases": list(selected_cases),
            "missing": missing,
            "failing": failing,
        },
    }


def _audit_journey_l1_rules(journey_payload: dict[str, Any]) -> dict[str, Any]:
    l1_steps = [
        step
        for step in journey_payload.get("steps", [])
        if step.get("level") == "L1"
    ]
    failing = [
        step.get("rule_id", "")
        for step in l1_steps
        if step.get("status") != "pass"
    ]
    return {
        "id": "journey_report_all_mainline_rules_pass",
        "status": "pass" if l1_steps and not failing else "fail",
        "message": "All L1 journey rules are marked pass.",
        "details": {
            "l1_rule_count": len(l1_steps),
            "failing": failing,
        },
    }


def _audit_deep_evidence(root: Path, matrix: dict[str, Any]) -> dict[str, Any]:
    missing: list[dict[str, str]] = []
    checked: list[dict[str, str]] = []
    for step in matrix.get("steps", []):
        if step.get("status") != "deep_verified":
            continue
        acceptance = step.get("acceptance") or {}
        for evidence in acceptance.get("evidence") or []:
            evidence_text = str(evidence)
            matches = _evidence_matches(root, evidence_text)
            checked.append(
                {
                    "step": str(step.get("id", "")),
                    "evidence": evidence_text,
                    "matches": str(len(matches)),
                }
            )
            if not matches:
                missing.append(
                    {
                        "step": str(step.get("id", "")),
                        "evidence": evidence_text,
                    }
                )
    return {
        "id": "native_evidence_for_deep_steps_present",
        "status": "pass" if not missing else "fail",
        "message": "All deep_verified evidence paths resolve to at least one artifact.",
        "details": {
            "checked": checked,
            "missing": missing,
        },
    }


def _evidence_matches(root: Path, evidence: str) -> list[str]:
    pattern = str(root / evidence)
    if any(char in evidence for char in "*?["):
        return sorted(glob.glob(pattern))
    path = root / evidence
    return [str(path)] if path.exists() else []


def _audit_native_traceability(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    quick_path, quick_payload = _latest_json_artifact(root, "outputs/quick_runs/qr_*.json")
    agent_path, agent_payload = _latest_json_artifact(root, "outputs/agent_runs/ar_*.json")
    submission_path, submission_payload = _latest_json_artifact(
        root,
        "outputs/submissions/liepin/sc_*/submission_log.json",
    )
    feedback_path, feedback_payload = _latest_json_artifact(
        root,
        "outputs/feedback_iterations/fi_*/iteration_record.json",
    )

    if not quick_payload:
        errors.append("missing quick_run artifact")
    else:
        quick_run = quick_payload.get("run") or {}
        traceability = quick_payload.get("traceability") or {}
        if quick_run.get("status") != "DONE":
            errors.append("quick_run did not finish DONE")
        if traceability.get("fact_preserving_traceability") is not True:
            errors.append("quick_run fact-preserving trace missing")
        if traceability.get("matching_uses_selected_evidence") is not True:
            errors.append("quick_run matching trace did not use selected evidence")
        if traceability.get("resume_traceable") is not True:
            errors.append("quick_run resume traceability missing")
        if quick_run.get("selected_evidence_card_ids") != traceability.get("selected_evidence_card_ids"):
            errors.append("quick_run selected evidence mismatch")
        if not _path_exists(root, str(quick_payload.get("resume_pdf") or traceability.get("resume_pdf") or "")):
            errors.append("quick_run resume_pdf artifact missing")

    if not agent_payload:
        errors.append("missing agent_run artifact")
    else:
        agent_run = agent_payload.get("run") or {}
        delivery_plan = agent_run.get("delivery_plan") or {}
        review_queue = agent_run.get("review_queue") or {}
        if agent_run.get("guided_batch") is not True:
            errors.append("agent_run was not a guided batch")
        if int(review_queue.get("pending_count") or 0) < 1:
            errors.append("agent_run review queue was empty")
        if agent_run.get("status") != "REVIEW_PENDING":
            errors.append("agent_run did not stop at REVIEW_PENDING")
        if delivery_plan.get("external_submission_attempted") is not False:
            errors.append("agent_run external submission attempted")
        if delivery_plan.get("delivery_events") != 0:
            errors.append("agent_run delivery events were recorded")
        if delivery_plan.get("submit_enabled") is not False:
            errors.append("agent_run delivery submit was enabled")
        if not _path_exists(root, str(agent_run.get("run_log", ""))):
            errors.append("agent_run run_log missing")

    if not submission_payload or not feedback_payload:
        errors.append("missing submissions check-mode or feedback artifact")
    else:
        if submission_payload.get("status") != "check_mode_success_submit_skipped":
            errors.append("check-mode did not end submit_skipped")
        if submission_payload.get("final_submit_attempted") is not False:
            errors.append("check-mode final submit attempted")
        if feedback_payload.get("source_run_id") != submission_payload.get("submission_id"):
            errors.append("feedback source_run_id does not match check-mode submission")
        new_resume_version = str(feedback_payload.get("new_resume_version_id_or_none") or "")
        if feedback_payload.get("previous_resume_version_id") == new_resume_version:
            errors.append("feedback did not create a distinct resume version")
        candidate = feedback_payload.get("next_check_mode_candidate") or {}
        if new_resume_version and candidate.get("resume_version_id") != new_resume_version:
            errors.append("next check-mode candidate does not use new resume version")
        if candidate.get("real_submit_disabled") is not True:
            errors.append("next check-mode candidate does not disable real submit")
        if not _path_exists(root, str(feedback_payload.get("record_path", ""))):
            errors.append("feedback iteration record missing")
        if not _path_exists(root, str(feedback_payload.get("source_snapshot_path", ""))):
            errors.append("feedback source snapshot missing")

    return {
        "id": "traceability_paths_connect_across_stages",
        "status": "pass" if not errors else "fail",
        "message": "External page automation artifacts connect Quick Run, Agent Run, Submissions, and feedback iteration.",
        "details": {
            "errors": errors,
            "quick_run_artifact": str(quick_path.relative_to(root)) if quick_path else "",
            "agent_run_artifact": str(agent_path.relative_to(root)) if agent_path else "",
            "submission_artifact": str(submission_path.relative_to(root)) if submission_path else "",
            "feedback_artifact": str(feedback_path.relative_to(root)) if feedback_path else "",
        },
    }


def _latest_json_artifact(root: Path, pattern: str) -> tuple[Path | None, dict[str, Any]]:
    paths = [Path(path) for path in glob.glob(str(root / pattern))]
    for path in sorted(paths, key=lambda candidate: candidate.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(payload, dict):
            return path, payload
    return None, {}


def _path_exists(root: Path, path_text: str) -> bool:
    if not path_text:
        return False
    path = Path(path_text)
    if not path.is_absolute():
        path = root / path
    return path.exists()


def _render_closed_loop_audit_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Closed Loop E2E Audit",
        "",
        f"- Run ID: `{audit['run_id']}`",
        f"- Status: `{audit['status']}`",
        f"- Generated At: `{audit['generated_at']}`",
        "",
        "| Check | Status | Message |",
        "|---|---|---|",
    ]
    for check in audit["checks"]:
        lines.append(
            f"| `{check['id']}` | `{check['status']}` | {check['message']} |"
        )
    lines.append("")
    return "\n".join(lines)


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

    evidence_step = _find_step(report, "generate_review_and_complete_evidence_card")
    if evidence_step is not None:
        status = "pass" if evidence_step.status == "pass" else "fail"
        results["evidence_card_requires_review"] = JourneyStepResult(
            status=status,
            evidence=evidence_step.evidence,
            message=evidence_step.message,
        )

    job_step = _find_step(report, "setup_job_target")
    if job_step is not None:
        status = "pass" if job_step.status == "pass" else "fail"
        results["job_target_ready_for_runs"] = JourneyStepResult(
            status=status,
            evidence=job_step.evidence,
            message=job_step.message,
        )

    quick_step = _find_step(report, "quick_run_generate_and_evaluate_resume")
    if quick_step is not None:
        status = "pass" if quick_step.status == "pass" else "fail"
        results["quick_run_outputs_are_traceable"] = JourneyStepResult(
            status=status,
            evidence=quick_step.evidence,
            message=quick_step.message,
        )

    agent_guided_step = _find_step(report, "agent_run_guided_batch")
    if agent_guided_step is not None:
        status = "pass" if agent_guided_step.status == "pass" else "fail"
        results["agent_run_batch_is_guarded"] = JourneyStepResult(
            status=status,
            evidence=agent_guided_step.evidence,
            message=agent_guided_step.message,
        )

    channel_session_step = _find_step(report, "channel_session_setup")
    if channel_session_step is not None:
        status = "pass" if channel_session_step.status == "pass" else "fail"
        results["channel_session_validity_is_positive_signal_based"] = JourneyStepResult(
            status=status,
            evidence=channel_session_step.evidence,
            message=channel_session_step.message,
        )

    submission_check_step = _find_step(report, "submission_check_mode")
    if submission_check_step is not None:
        status = "pass" if submission_check_step.status == "pass" else "fail"
        results["check_mode_never_final_submits"] = JourneyStepResult(
            status=status,
            evidence=submission_check_step.evidence,
            message=submission_check_step.message,
        )

    feedback_iteration_step = _find_step(report, "feedback_iteration_after_check_mode")
    if feedback_iteration_step is not None:
        status = "pass" if feedback_iteration_step.status == "pass" else "fail"
        results["feedback_iteration_preserves_traceability"] = JourneyStepResult(
            status=status,
            evidence=feedback_iteration_step.evidence,
            message=feedback_iteration_step.message,
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
