from __future__ import annotations

import argparse
import glob
import hashlib
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tools.acceptance.external_l3 import (
    build_external_l3_validation,
    submission_log_error_blocker_reason,
    write_external_l3_validation,
)
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
        if level == "L3":
            steps.append(
                _run_l3_external_validation_step(
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


def _run_l3_external_validation_step(
    *,
    root: Path,
    run_id: str,
    timeout_seconds: int,
) -> AcceptanceStep:
    command = ("internal", "external_l3_submission_validation")
    json_path = root / "outputs" / "acceptance" / run_id / "external-l3-validation.json"
    try:
        validation = build_external_l3_validation(
            root=root,
            run_id=run_id,
            generated_at=_utcnow(),
            default_timeout_seconds=timeout_seconds,
        )
        json_path, _ = write_external_l3_validation(
            root=root,
            run_id=run_id,
            validation=validation,
        )
    except Exception as exc:
        return AcceptanceStep(
            level="L3",
            name="external_l3_submission_validation",
            status="fail",
            command=command,
            evidence=str(json_path),
            message=f"External L3 validation failed before writing evidence: {exc}",
        )

    if validation["status"] == "external_validated":
        message = "External L3 validation recorded a real guarded channel result."
    else:
        blocker = validation.get("live_blocker") or {}
        attempted = validation.get("external_submission_attempted") is True
        execution_scope = (
            "external submit was attempted and blocked after command"
            if attempted
            else "no external submit was attempted"
        )
        message = (
            "External L3 validation recorded live blocker "
            f"`{blocker.get('reason', 'unknown')}`; {execution_scope}."
        )
    return AcceptanceStep(
        level="L3",
        name="external_l3_submission_validation",
        status="pass",
        command=command,
        evidence=str(json_path),
        message=message,
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

    external_l3_step = _find_step(report, "external_l3_submission_validation")
    if external_l3_step is not None:
        status = "pass" if external_l3_step.status == "pass" else "fail"
        results["external_l3_result_or_blocker_recorded"] = JourneyStepResult(
            status=status,
            evidence=external_l3_step.evidence,
            message=external_l3_step.message,
        )
        results["external_l3_submit_safety_decision_recorded"] = (
            _external_l3_submit_safety_result(external_l3_step)
        )
        results["external_l3_live_input_artifacts_fingerprinted"] = (
            _external_l3_live_input_artifacts_result(external_l3_step)
        )
        results["external_l3_input_artifact_basenames_redacted"] = (
            _external_l3_input_artifact_basenames_redacted_result(external_l3_step)
        )
        results["external_l3_human_readable_redaction_evidence_recorded"] = (
            _external_l3_human_readable_redaction_evidence_result(external_l3_step)
        )
        results["external_l3_rate_limit_policy_recorded"] = (
            _external_l3_rate_limit_policy_result(external_l3_step)
        )
        results["external_l3_forbidden_inputs_rejected"] = (
            _external_l3_forbidden_inputs_result(external_l3_step)
        )
        results["external_l3_target_confirmation_matches_url"] = (
            _external_l3_target_confirmation_result(external_l3_step)
        )
        results["external_l3_live_command_redacted"] = (
            _external_l3_live_command_redaction_result(external_l3_step)
        )
        results["external_l3_live_output_redacted"] = (
            _external_l3_live_output_redaction_result(external_l3_step)
        )
        results["external_l3_post_submit_feedback_traceable"] = (
            _external_l3_feedback_trace_result(external_l3_step)
        )
        results["external_l3_post_command_blocker_diagnostics_recorded"] = (
            _external_l3_post_command_blocker_diagnostics_result(external_l3_step)
        )
        results["external_l3_submission_log_summary_recorded"] = (
            _external_l3_submission_log_summary_result(external_l3_step)
        )
        results["external_l3_submission_log_path_guarded"] = (
            _external_l3_submission_log_path_guard_result(external_l3_step)
        )
        results["external_l3_submission_log_required_steps_recorded"] = (
            _external_l3_submission_log_required_steps_result(external_l3_step)
        )
        results["external_l3_submission_log_raw_inputs_redacted"] = (
            _external_l3_submission_log_raw_inputs_redacted_result(external_l3_step)
        )
        results["external_l3_submission_log_step_details_redacted"] = (
            _external_l3_submission_log_step_details_redacted_result(external_l3_step)
        )
        results["external_l3_submission_log_browser_artifacts_redacted"] = (
            _external_l3_submission_log_browser_artifacts_redacted_result(
                external_l3_step
            )
        )
        results["external_l3_authorization_packet_recorded"] = (
            _external_l3_authorization_packet_result(external_l3_step)
        )
        results["external_l3_handoff_command_template_matches_effective_policy"] = (
            _external_l3_handoff_command_template_result(external_l3_step)
        )
        results["external_l3_handoff_command_template_review_recorded"] = (
            _external_l3_handoff_command_template_review_result(external_l3_step)
        )
        results["external_l3_evidence_manifest_recorded"] = (
            _external_l3_evidence_manifest_result(external_l3_step)
        )
        results["external_l3_outcome_summary_recorded"] = (
            _external_l3_outcome_summary_result(external_l3_step)
        )
        results["external_l3_manual_session_ready_confirmed_before_command"] = (
            _external_l3_manual_session_readiness_result(external_l3_step)
        )
        results["external_l3_pre_submit_blocker_diagnostics_recorded"] = (
            _external_l3_pre_submit_blocker_diagnostics_result(external_l3_step)
        )
        results["external_l3_timeout_recorded_as_live_blocker"] = (
            _external_l3_timeout_blocker_result(external_l3_step)
        )
        results["external_l3_command_error_recorded_as_live_blocker"] = (
            _external_l3_command_error_blocker_result(external_l3_step)
        )

    l2_step = next((step for step in report.steps if step.level == "L2"), None)
    if l2_step is not None and l2_step.status != "not_started":
        results["lm_studio_visible_to_run_pages"] = JourneyStepResult(
            status="pass" if l2_step.status == "pass" else "fail",
            evidence=l2_step.evidence,
            message=l2_step.message,
        )
    return results


def _external_l3_live_command_redaction_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 命令脱敏证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有持久化 live command 原文。",
        )
    redaction = payload.get("command_redaction") or {}
    command = payload.get("command") or []
    redacted_args = set(redaction.get("redacted_arguments") or [])
    required_args = {
        "--job-url",
        "--resume",
        "--profile",
        "--confirm-submit-job-id",
        "--confirm-submit-recruiter",
    }
    if (
        redaction.get("raw_live_inputs_persisted") is False
        and required_args.issubset(redacted_args)
        and isinstance(command, list)
        and command.count("<redacted>") >= len(required_args)
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 持久化命令已脱敏，真实 live 输入未写入 command 证据。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 持久化命令缺少脱敏证据或脱敏参数不完整。",
    )


def _external_l3_live_output_redaction_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 输出脱敏证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有持久化 live output 原文。",
        )
    redaction = payload.get("live_output_redaction") or {}
    redacted_fields = set(redaction.get("redacted_fields") or [])
    required_fields = {
        "job_url",
        "resume_pdf_path",
        "profile_path",
        "confirm_submit_job_id",
        "confirm_submit_recruiter",
    }
    if (
        redaction.get("raw_live_inputs_persisted") is False
        and required_fields.issubset(redacted_fields)
        and isinstance(payload.get("stdout_tail", ""), str)
        and isinstance(payload.get("stderr_tail", ""), str)
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 持久化输出尾部已纳入 live 输入脱敏策略。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 持久化输出尾部缺少 live 输入脱敏证据。",
    )


def _external_l3_live_input_artifacts_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 真实输入产物审计证据不可读取: {exc}",
        )
    artifacts = payload.get("live_input_artifacts") or {}
    files = artifacts.get("files") or []
    job_url = artifacts.get("job_url") or {}
    confirmations = artifacts.get("confirmations") or {}
    files_have_audit_fields = all(
        isinstance(item, dict)
        and "sha256" in item
        and item.get("raw_content_persisted") is False
        for item in files
    )
    values_not_persisted = (
        job_url.get("raw_value_persisted") is False
        and confirmations.get("raw_values_persisted") is False
    )
    if files and files_have_audit_fields and values_not_persisted:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 真实输入产物审计已记录，且未持久化原始内容或确认值。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 真实输入产物审计缺失或原始值持久化约束不完整。",
    )


def _external_l3_input_artifact_basenames_redacted_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 输入产物文件名脱敏证据不可读取: {exc}",
        )

    artifacts = payload.get("live_input_artifacts") or {}
    validation_basenames_redacted = _input_artifact_basenames_redacted(artifacts)
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass" if validation_basenames_redacted else "fail",
            evidence=step.evidence,
            message=(
                "External L3 validation record 已脱敏 resume/profile 文件名；未执行真实渠道命令，因此没有 submission log 文件名脱敏要求。"
                if validation_basenames_redacted
                else "External L3 validation record 仍可能持久化 resume/profile 文件名。"
            ),
        )

    traceability = payload.get("submission_traceability") or {}
    if not traceability.get("log_json_exists"):
        return JourneyStepResult(
            status="pass" if validation_basenames_redacted else "fail",
            evidence=step.evidence,
            message=(
                "External L3 validation record 已脱敏 resume/profile 文件名；submission log 缺失由 traceability failed_checks 记录。"
                if validation_basenames_redacted
                else "External L3 validation record 仍可能持久化 resume/profile 文件名。"
            ),
        )
    if (
        validation_basenames_redacted
        and traceability.get("submission_log_input_artifact_basenames_redacted") is True
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 validation record 与 submission log 均未持久化 resume/profile 文件名。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 validation record 或 submission log 仍可能持久化 resume/profile 文件名。",
    )


def _input_artifact_basenames_redacted(artifacts: dict[str, Any]) -> bool:
    files = artifacts.get("files") or []
    if not isinstance(files, list) or not files:
        return False
    for item in files:
        if not isinstance(item, dict):
            return False
        if item.get("basename_persisted") is not False:
            return False
        if item.get("provided") is True and item.get("basename") != "<redacted>":
            return False
    return True


def _external_l3_human_readable_redaction_evidence_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    evidence_path = Path(step.evidence)
    markdown_path = evidence_path.with_suffix(".md")
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=str(markdown_path),
            message=f"External L3 Markdown 脱敏证据不可读取: {exc}",
        )

    required_fragments = [
        "## 真实输入产物审计",
        "文件名是否持久化",
        "原内容是否持久化",
    ]
    if payload.get("external_submission_attempted") is True:
        required_fragments.extend(
            [
                "Submission log 输入产物文件名是否脱敏",
                "Submission log 原始浏览器产物是否脱敏",
            ]
        )
    missing = [fragment for fragment in required_fragments if fragment not in markdown]
    if not missing:
        return JourneyStepResult(
            status="pass",
            evidence=str(markdown_path),
            message="External L3 Markdown 报告已展示输入产物与 submission log 脱敏结论。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=str(markdown_path),
        message=f"External L3 Markdown 报告缺少脱敏证据: {', '.join(missing)}",
    )


def _external_l3_rate_limit_policy_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 频控策略证据不可读取: {exc}",
        )
    policy = payload.get("rate_limit_policy") or {}
    if (
        policy.get("enabled") is True
        and int(policy.get("max_per_batch", 0)) > 0
        and int(policy.get("cooldown_seconds", 0)) > 0
        and int(policy.get("daily_limit", 0)) > 0
        and policy.get("state_path")
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 频控策略已记录，真实 submit 不会绕过 rate limit。",
        )
    if (payload.get("live_blocker") or {}).get("reason") == (
        "invalid_external_l3_rate_limit_policy"
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 已把无效频控策略记录为 pre-submit live blocker。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 频控策略缺失或允许真实 submit 绕过 rate limit。",
    )


def _external_l3_forbidden_inputs_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 禁止输入审计证据不可读取: {exc}",
        )
    audit = payload.get("forbidden_input_audit") or {}
    inputs = audit.get("inputs") or []
    present = audit.get("forbidden_inputs_present") is True
    raw_values_not_persisted = (
        audit.get("raw_values_persisted") is False
        and all(
            isinstance(item, dict) and item.get("raw_value_persisted") is False
            for item in inputs
        )
    )
    blocker_reason = (payload.get("live_blocker") or {}).get("reason", "")
    safety_decision = payload.get("submit_safety_decision") or {}
    if (
        present
        and raw_values_not_persisted
        and blocker_reason == "forbidden_external_l3_sensitive_inputs"
        and payload.get("external_submission_attempted") is False
        and safety_decision.get("forbidden_inputs_present") is True
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 已把密码/验证码/短信码/原始密钥类输入阻断在 submit 命令前。",
        )
    if (
        not present
        and raw_values_not_persisted
        and safety_decision.get("credentials_or_challenge_inputs_accepted") is False
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 禁止输入审计已记录，未接收或持久化 secret/challenge 输入。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 禁止输入审计缺失、持久化原值，或未在 submit 前阻断 forbidden inputs。",
    )


def _external_l3_target_confirmation_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 目标确认审计证据不可读取: {exc}",
        )
    audit = payload.get("target_confirmation_audit") or {}
    raw_values_not_persisted = audit.get("raw_values_persisted") is False
    recruiter_boundary_recorded = (
        isinstance(audit.get("confirm_submit_recruiter_present"), bool)
        and audit.get("recruiter_page_match_requires_target_verify") is True
        and audit.get("raw_recruiter_value_persisted") is False
    )
    blocker_reason = (payload.get("live_blocker") or {}).get("reason", "")
    safety_decision = payload.get("submit_safety_decision") or {}
    safety_audit = safety_decision.get("target_confirmation_audit", {})
    if (
        audit.get("confirm_submit_job_id_present") is False
        and raw_values_not_persisted
        and recruiter_boundary_recorded
        and payload.get("external_submission_attempted") is False
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 目标确认审计已记录；本次缺少确认岗位 ID，已由 readiness blocker 覆盖，recruiter 页面匹配边界由 target_verify 承担。",
        )
    if (
        blocker_reason == "target_confirmation_mismatch"
        and raw_values_not_persisted
        and recruiter_boundary_recorded
        and payload.get("external_submission_attempted") is False
        and safety_audit.get("job_id_matches_confirmation") is False
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 已在 submit 命令前阻断 URL 岗位 ID 与确认岗位 ID 不一致，并记录 recruiter 页面匹配由 target_verify 证明。",
        )
    if (
        audit.get("job_url_has_parseable_job_id") is True
        and audit.get("job_id_matches_confirmation") is True
        and raw_values_not_persisted
        and recruiter_boundary_recorded
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 目标确认审计已证明 URL 岗位 ID 与确认岗位 ID 一致，且未持久化原值；recruiter 页面匹配由 target_verify 证明。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 目标确认审计缺失、持久化原值，未阻断 URL/确认岗位 ID 不一致，或未记录 recruiter 页面匹配边界。",
    )


def _external_l3_submit_safety_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 最终提交安全决策证据不可读取: {exc}",
        )
    decision = payload.get("submit_safety_decision") or {}
    required_flags = (
        decision.get("requires_explicit_user_authorization") is True
        and decision.get("requires_separate_final_submit_confirmation") is True
        and decision.get("credentials_or_challenge_inputs_accepted") is False
    )
    blocker = payload.get("live_blocker") or {}
    blocker_reason = str(blocker.get("reason", ""))
    if blocker_reason and payload.get("external_submission_attempted") is True:
        if decision.get("post_run_blocker_reason") != blocker_reason:
            return JourneyStepResult(
                status="fail",
                evidence=step.evidence,
                message=(
                    "External L3 最终提交安全决策与 live blocker 不一致: "
                    f"post_run_blocker_reason={decision.get('post_run_blocker_reason', '')}, "
                    f"live_blocker={blocker_reason}。"
                ),
            )
    if blocker_reason and payload.get("external_submission_attempted") is not True:
        if decision.get("blocking_reason") != blocker_reason:
            return JourneyStepResult(
                status="fail",
                evidence=step.evidence,
                message=(
                    "External L3 submit 前安全决策与 live blocker 不一致: "
                    f"blocking_reason={decision.get('blocking_reason', '')}, "
                    f"live_blocker={blocker_reason}。"
                ),
            )
    if decision.get("decision") and required_flags:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message=(
                "External L3 最终提交安全决策已记录: "
                f"{decision.get('decision', 'unknown')}。"
            ),
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 最终提交安全决策缺失或安全约束不完整。",
    )


def _external_l3_feedback_trace_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 提交后反馈追溯证据不可读取: {exc}",
        )
    trace = payload.get("post_submit_feedback_traceability") or {}
    blocker = payload.get("live_blocker") or {}
    blocker_reason = str(blocker.get("reason", ""))
    if blocker_reason:
        expected_source_status = (
            "external_submission_attempted_blocked"
            if payload.get("external_submission_attempted") is True
            else "pre_submit_blocked"
        )
        if (
            trace.get("source_type") != "live_blocker"
            or trace.get("source_reason") != blocker_reason
            or trace.get("source_status") != expected_source_status
        ):
            return JourneyStepResult(
                status="fail",
                evidence=step.evidence,
                message=(
                    "External L3 提交后反馈追溯与 live blocker 不一致: "
                    f"source_type={trace.get('source_type', '')}, "
                    f"source_status={trace.get('source_status', '')}, "
                    f"source_reason={trace.get('source_reason', '')}, "
                    f"live_blocker={blocker_reason}。"
                ),
            )
    markdown_fragments = [
        "## 提交后反馈追溯",
        f"- 是否可追溯: `{trace.get('traceable', False)}`",
        f"- 状态: `{trace.get('status', '')}`",
        f"- 来源类型: `{trace.get('source_type', '')}`",
        f"- 来源状态: `{trace.get('source_status', '')}`",
        f"- 来源原因: `{trace.get('source_reason', '')}`",
        f"- 来源产物: `{trace.get('source_artifact_path', '')}`",
        f"- 下一步反馈路径: `{trace.get('feedback_iteration_route', '')}`",
        f"- 下一步: {trace.get('next_action', '')}",
    ]
    missing_markdown = [
        fragment for fragment in markdown_fragments if fragment not in markdown
    ]
    if missing_markdown:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=(
                "External L3 提交后反馈追溯 Markdown 与 JSON 不一致: "
                + ", ".join(missing_markdown)
            ),
        )
    if payload.get("status") == "external_validated":
        if (
            trace.get("source_type") != "submission_log"
            or trace.get("source_status") != "external_validated"
            or trace.get("source_reason", "") != ""
        ):
            return JourneyStepResult(
                status="fail",
                evidence=step.evidence,
                message="External L3 成功结果的反馈追溯来源必须指向 submission log。",
            )
    if trace.get("traceable") is True and trace.get("source_artifact_path"):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message=(
                "External L3 提交后反馈追溯已记录，来源类型: "
                f"{trace.get('source_type', 'unknown')}。"
            ),
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 提交后反馈追溯缺失或不可追溯。",
    )


def _external_l3_post_command_blocker_diagnostics_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 post-command blocker 诊断证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有 post-command blocker 诊断要求。",
        )
    if payload.get("status") != "live_blocker_recorded":
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 真实渠道结果已验证，无 post-command blocker。",
        )

    blocker = payload.get("live_blocker") or {}
    diagnostics = blocker.get("diagnostics") or {}
    failed_checks = blocker.get("failed_checks") or []
    has_command_outcome = (
        diagnostics.get("returncode") is not None
        or diagnostics.get("command_timed_out") is True
        or bool(diagnostics.get("command_error"))
    )
    if (
        isinstance(failed_checks, list)
        and has_command_outcome
        and isinstance(diagnostics.get("submission_traceability_checks"), list)
        and isinstance(diagnostics.get("submission_traceability_failed_checks"), list)
        and isinstance(diagnostics.get("submission_log_required_steps"), dict)
    ):
        summary = diagnostics.get("submission_log_summary") or {}
        expected_business_reason = (
            submission_log_error_blocker_reason(summary)
            if isinstance(summary, dict)
            else ""
        )
        actual_reason = str(blocker.get("reason", ""))
        if expected_business_reason and actual_reason != expected_business_reason:
            return JourneyStepResult(
                status="fail",
                evidence=step.evidence,
                message=(
                    "External L3 post-command blocker 未使用 submission log "
                    f"业务错误的精确归因: expected={expected_business_reason}, "
                    f"actual={actual_reason}。"
                ),
            )
        required_steps = diagnostics.get("submission_log_required_steps") or {}
        markdown_fragments = [
            "## Live Blocker",
            f"- Reason: `{blocker.get('reason', '')}`",
            f"- Failed Checks: `{', '.join(failed_checks)}`",
            f"- Returncode: `{diagnostics.get('returncode', '')}`",
            f"- Log Hint: `{diagnostics.get('log_hint', '')}`",
            f"- YAML: `{diagnostics.get('log_yaml_path', '')}`",
            f"- JSON: `{diagnostics.get('log_json_path', '')}`",
            f"- 诊断成功投递关键步骤是否齐备: `{required_steps.get('passed', False)}`",
            f"- 诊断缺失投递步骤: `{', '.join(required_steps.get('missing_steps', []))}`",
            f"- 诊断失败投递步骤: `{', '.join(required_steps.get('failed_steps', []))}`",
        ]
        markdown_missing = [
            f"markdown:{fragment}"
            for fragment in markdown_fragments
            if fragment not in markdown
        ]
        if markdown_missing:
            return JourneyStepResult(
                status="fail",
                evidence=step.evidence,
                message=(
                    "External L3 post-command blocker 诊断 Markdown 与 JSON "
                    "不一致: "
                    + ", ".join(markdown_missing)
                ),
            )
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message=(
                "External L3 post-command blocker 已记录 traceability 诊断: "
                f"{blocker.get('reason', 'unknown')}。"
            ),
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 post-command blocker 缺少 traceability failed_checks 或诊断字段。",
    )


def _external_l3_submission_log_summary_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 submission log 摘要证据不可读取: {exc}",
        )
    traceability = payload.get("submission_traceability") or {}
    if not traceability:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有 submission log 摘要要求。",
        )
    trace_markdown_missing = _external_l3_submission_traceability_markdown_missing(
        traceability,
        markdown,
    )
    if not traceability.get("log_json_exists"):
        if trace_markdown_missing:
            return JourneyStepResult(
                status="fail",
                evidence=step.evidence,
                message=(
                    "External L3 submission traceability Markdown 与 JSON "
                    "不一致: "
                    + ", ".join(trace_markdown_missing)
                ),
            )
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未产生可解析 submission log，因此由 traceability failed_checks 记录缺失原因。",
        )
    summary = traceability.get("submission_log_summary") or {}
    last_step = summary.get("last_step") or {}
    unsafe_detail_tokens = (
        "url_job_id=",
        "dom_jobid=",
        "params_jobid=",
        "recruiter=",
        "saved html snapshots",
    )
    last_step_detail = (
        str(last_step.get("detail", "")) if isinstance(last_step, dict) else ""
    )
    summary_detail_redacted = not any(
        token in last_step_detail for token in unsafe_detail_tokens
    )
    missing = list(trace_markdown_missing)
    if not summary.get("status"):
        missing.append("status")
    if "error" not in summary:
        missing.append("error")
    if not summary.get("mode"):
        missing.append("mode")
    if not isinstance(last_step, dict):
        missing.append("last_step")
    elif not last_step.get("name") or "status" not in last_step:
        missing.append("last_step.name_or_status")
    if not summary_detail_redacted:
        missing.append("last_step.detail_redacted")
    markdown_fragments = [
        "## Submission Log 追溯",
        f"- Submission Status: `{summary.get('status', '')}`",
        f"- Submission Error: `{summary.get('error', '')}`",
        f"- Submission Mode: `{summary.get('mode', '')}`",
        f"- Last Step: `{last_step.get('name', '')}/{last_step.get('status', '')}`",
    ]
    missing.extend(
        f"markdown:{fragment}"
        for fragment in markdown_fragments
        if fragment not in markdown
    )
    if not missing:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message=(
                "External L3 submission log 摘要已记录: "
                f"{summary.get('status', 'unknown')}/"
                f"{summary.get('error', '')}/{summary.get('mode', '')}。"
            ),
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=(
            "External L3 submission log 摘要缺失、不完整、Markdown 不一致，"
            "或复制了未脱敏的步骤详情: "
            + ", ".join(missing)
        ),
    )


def _external_l3_submission_traceability_markdown_missing(
    traceability: dict[str, Any],
    markdown: str,
) -> list[str]:
    missing = []
    fragments = [
        "## Submission Log 追溯",
        (
            "- Submission log 路径在允许根目录内: "
            f"`{traceability.get('log_path_within_allowed_root', False)}`"
        ),
        (
            "- 允许 submission log 根目录: "
            f"`{traceability.get('allowed_submission_log_root', '')}`"
        ),
        (
            "- 拒绝 submission log 路径原因: "
            f"`{traceability.get('rejected_log_yaml_path_reason', '')}`"
        ),
        (
            "- Failed Checks: "
            f"`{', '.join(traceability.get('failed_checks', []))}`"
        ),
    ]
    missing.extend(
        f"markdown:{fragment}" for fragment in fragments if fragment not in markdown
    )
    checks = traceability.get("checks") or []
    if checks:
        if "| 检查项 | 状态 | 说明 |" not in markdown:
            missing.append("markdown:traceability_checks_table")
        for check in checks:
            if not isinstance(check, dict):
                missing.append("checks.entry")
                continue
            row = _external_l3_submission_traceability_check_markdown_row(check)
            if row not in markdown:
                missing.append(f"{check.get('id', '')}.markdown_check_row")
    return missing


def _external_l3_submission_traceability_check_markdown_row(
    check: dict[str, Any],
) -> str:
    return (
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


def _external_l3_submission_log_path_guard_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 submission log 路径边界证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有 submission log 路径边界要求。",
        )
    traceability = payload.get("submission_traceability") or {}
    if traceability.get("log_path_within_allowed_root") is True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 submission log 路径未越过允许输出根目录。",
        )
    failed_checks = set(traceability.get("failed_checks") or [])
    if "submission_log_path_within_allowed_root" in failed_checks:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 已把越界 submission log 路径记录为 traceability blocker。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 submission log 路径边界缺少审计结果。",
    )


def _external_l3_submission_log_required_steps_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 submission log 关键步骤证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有成功投递步骤链要求。",
        )
    traceability = payload.get("submission_traceability") or {}
    if not traceability.get("log_json_exists"):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未产生可解析 submission log，关键步骤缺失由 traceability failed_checks 记录。",
        )
    required_steps = traceability.get("submission_log_required_steps") or {}
    markdown_fragments = [
        "## Submission Log 追溯",
        f"- 成功投递关键步骤是否齐备: `{required_steps.get('passed', False)}`",
        f"- 成功投递必需步骤: `{', '.join(required_steps.get('required_for_successful_submit', []))}`",
        f"- 已记录投递步骤: `{_submission_required_steps_markdown_summary(required_steps.get('recorded_steps', []))}`",
        f"- 缺失投递步骤: `{', '.join(required_steps.get('missing_steps', []))}`",
        f"- 失败投递步骤: `{', '.join(required_steps.get('failed_steps', []))}`",
        f"- 非成功日志免完整步骤原因: `{required_steps.get('not_required_reason', '')}`",
    ]
    markdown_missing = [
        f"markdown:{fragment}"
        for fragment in markdown_fragments
        if fragment not in markdown
    ]
    if markdown_missing:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=(
                "External L3 submission log 关键步骤 Markdown 与 JSON "
                "不一致: "
                + ", ".join(markdown_missing)
            ),
        )
    if required_steps.get("passed") is True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 submission log 已记录成功投递所需关键步骤或本次非成功投递无需完整步骤链。",
        )
    failed_checks = set(traceability.get("failed_checks") or [])
    if "successful_submission_required_steps_present" in failed_checks:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 已把成功投递关键步骤缺失记录为 traceability blocker。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 submission log 缺少成功投递关键步骤审计。",
    )


def _submission_required_steps_markdown_summary(steps: Any) -> str:
    if not isinstance(steps, list):
        return ""
    rendered = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        rendered.append(f"{step.get('name', '')}:{step.get('status', '')}")
    return ", ".join(rendered)


def _external_l3_submission_log_raw_inputs_redacted_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 submission log 脱敏证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有 submission log 原始 live 输入脱敏要求。",
        )
    traceability = payload.get("submission_traceability") or {}
    if not traceability.get("log_json_exists"):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未产生可解析 submission log，脱敏缺失由 traceability failed_checks 记录。",
        )
    if traceability.get("submission_log_raw_live_inputs_redacted") is True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 submission log 原始 Job URL 与文件路径字段已脱敏。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 submission log 仍可能持久化原始 Job URL 或文件路径。",
    )


def _external_l3_submission_log_step_details_redacted_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 submission log step detail 脱敏证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有 submission log step detail 脱敏要求。",
        )
    traceability = payload.get("submission_traceability") or {}
    if not traceability.get("log_json_exists"):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未产生可解析 submission log，step detail 脱敏缺失由 traceability failed_checks 记录。",
        )
    if traceability.get("submission_log_step_details_redacted") is True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 submission log steps.detail 已脱敏。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 submission log steps.detail 仍可能持久化 Job URL、文件路径或确认值原文。",
    )


def _external_l3_submission_log_browser_artifacts_redacted_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        payload = json.loads(Path(step.evidence).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 submission log 浏览器诊断产物证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未执行真实渠道命令，因此没有原始浏览器诊断产物脱敏要求。",
        )
    traceability = payload.get("submission_traceability") or {}
    if not traceability.get("log_json_exists"):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 未产生可解析 submission log，浏览器诊断产物缺失由 traceability failed_checks 记录。",
        )
    if traceability.get("submission_log_browser_artifacts_redacted") is True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 submission log 未引用原始截图或 HTML snapshot。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 submission log 仍引用原始截图或 HTML snapshot。",
    )


def _external_l3_authorization_packet_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 授权确认包证据不可读取: {exc}",
        )
    handoff = payload.get("operator_handoff") or {}
    packet = handoff.get("authorization_packet") or {}
    runbook = handoff.get("runbook") or {}
    required_statements = packet.get("required_confirmation_statements") or []
    required_evidence = set(packet.get("required_evidence") or [])
    abort_conditions = packet.get("abort_conditions") or []
    prohibited_inputs = set(packet.get("operator_must_not_provide") or [])
    runbook_path = str(runbook.get("path", ""))
    runbook_file = Path(runbook_path)
    runbook_covers = set(runbook.get("covers") or [])
    required_sections = runbook.get("required_sections") or []
    required_sections_present = runbook.get("required_sections_present") or {}
    runbook_sha256_matches = (
        runbook_file.is_file()
        and runbook.get("sha256") == _sha256_path(runbook_file)
    )
    runbook_ok = (
        runbook_path == "docs/runbooks/external-l3-live-run.md"
        and runbook.get("exists") is True
        and runbook_sha256_matches
        and runbook.get("language") == "zh-CN"
        and len(required_sections) >= 8
        and all(
            required_sections_present.get(section) is True
            for section in required_sections
        )
        and runbook.get("operator_review_required") is True
        and runbook.get("copy_paste_requires_live_value_replacement") is True
        and runbook.get("raw_live_inputs_persisted") is False
        and {
            "authorization_boundary",
            "manual_session_preflight",
            "live_input_preflight",
            "blocker_triage",
            "post_run_evidence_review",
        }.issubset(runbook_covers)
        and "### 真实运行 Runbook" in markdown
        and f"- 路径: `{runbook_path}`" in markdown
        and f"- SHA256: `{runbook.get('sha256', '')}`" in markdown
        and "#### Runbook 必需章节" in markdown
    )
    if (
        packet.get("raw_confirmation_values_persisted") is False
        and len(required_statements) >= 3
        and {"live_run_readiness", "submit_safety_decision"}.issubset(
            required_evidence
        )
        and abort_conditions
        and {"password", "captcha_code", "sms_code"}.issubset(prohibited_inputs)
        and runbook_ok
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 授权确认包已记录必需声明、证据清单、中止条件、禁止输入项、中文真实运行 runbook 指纹和章节完整性。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message="External L3 授权确认包缺失或不可证明最终提交前确认边界与中文真实运行 runbook。",
    )


def _external_l3_handoff_command_template_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 授权交接命令模板证据不可读取: {exc}",
        )

    handoff = payload.get("operator_handoff") or {}
    template = str(handoff.get("command_template", ""))
    preflight_template = str(handoff.get("preflight_command_template", ""))
    runtime_options = handoff.get("runtime_options") or {}
    rate_limit_policy = payload.get("rate_limit_policy") or {}
    required_fragments = [
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_CHANNEL",
            runtime_options.get("channel", ""),
        ),
        _expected_env_assignment("PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED", "true"),
        _expected_env_assignment("PIPF_EXTERNAL_L3_JOB_URL", "<https-url>"),
        _expected_env_assignment("PIPF_EXTERNAL_L3_RESUME_PDF", "<resume.pdf>"),
        _expected_env_assignment("PIPF_EXTERNAL_L3_PROFILE", "<profile.yaml>"),
        _expected_env_assignment("PIPF_EXTERNAL_L3_CONFIRM_JOB_ID", "<job-id>"),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER",
            "<recruiter>",
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_SESSION_DIR",
            runtime_options.get("session_dir", ""),
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_OUTPUT_DIR",
            runtime_options.get("output_dir", ""),
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_TIMEOUT_SECONDS",
            runtime_options.get("timeout_seconds", ""),
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_TIMEOUT_MS",
            runtime_options.get("timeout_ms", ""),
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_HEADLESS",
            str(runtime_options.get("headless", "")).lower(),
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_RATE_LIMIT_MAX_PER_BATCH",
            rate_limit_policy.get("max_per_batch", ""),
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_RATE_LIMIT_COOLDOWN_SECONDS",
            rate_limit_policy.get("cooldown_seconds", ""),
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_RATE_LIMIT_DAILY_LIMIT",
            rate_limit_policy.get("daily_limit", ""),
        ),
        "bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3",
    ]
    preflight_fragments = [
        _expected_env_assignment("PIPF_EXTERNAL_L3_AUTHORIZED", "false"),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED",
            "false",
        ),
        _expected_env_assignment(
            "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED",
            "false",
        ),
        _expected_env_assignment("PIPF_EXTERNAL_L3_JOB_URL", "<https-url>"),
        "bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3",
    ]
    markdown_fragments = [
        "### 本地预检命令模板",
        "```bash",
        preflight_template,
        "### 授权真实运行命令模板",
        "```bash",
        template,
    ]
    missing = [fragment for fragment in required_fragments if fragment not in template]
    missing.extend(
        fragment
        for fragment in preflight_fragments
        if fragment not in preflight_template
    )
    if _expected_env_assignment("PIPF_EXTERNAL_L3_AUTHORIZED", "true") in preflight_template:
        missing.append("preflight_template.authorized_must_be_false")
    if (
        _expected_env_assignment("PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED", "true")
        in preflight_template
    ):
        missing.append("preflight_template.final_submit_must_be_false")
    missing.extend(
        fragment for fragment in markdown_fragments if fragment not in markdown
    )
    if not missing:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 授权交接命令模板包含无授权本地预检和授权真实运行两阶段模板，均使用 shell-safe 的 live 输入占位符，并匹配当前运行配置与有效频控策略。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=f"External L3 授权交接命令模板缺少或不匹配: {', '.join(missing)}",
    )


def _expected_env_assignment(name: str, value: object) -> str:
    return f"{name}={shlex.quote(str(value))}"


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _external_l3_handoff_command_template_review_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 命令模板复核证据不可读取: {exc}",
        )

    review = (
        (payload.get("operator_handoff") or {}).get("command_template_review") or {}
    )
    expected_placeholders = {
        "<https-url>",
        "<resume.pdf>",
        "<profile.yaml>",
        "<job-id>",
        "<recruiter>",
    }
    placeholders = set(review.get("placeholders") or [])
    required_fields = {
        "copy_paste_ready": False,
        "requires_placeholder_replacement": True,
        "requires_separate_authorization": True,
        "requires_separate_final_submit_confirmation": True,
        "requires_manual_session_ready_confirmation": True,
        "requires_prepared_session_storage": True,
        "shell_safe_env_assignments": True,
        "live_input_placeholders_present": True,
        "raw_live_inputs_persisted": False,
    }
    missing = [
        key
        for key, expected in required_fields.items()
        if review.get(key) is not expected
    ]
    if not expected_placeholders.issubset(placeholders):
        missing.append("placeholders")
    if not review.get("review_items"):
        missing.append("review_items")

    markdown_fragments = [
        "### 命令模板复核",
        "- 是否可直接复制运行: `False`",
        "- 必须替换占位符: `True`",
        "- 必须独立确认授权: `True`",
        "- 必须独立确认最终提交: `True`",
        "- 必须确认人工会话可用: `True`",
        "- 必须确认 session 存储就绪: `True`",
        "#### 需替换占位符",
        "#### 复核项",
    ]
    missing.extend(
        fragment for fragment in markdown_fragments if fragment not in markdown
    )
    if not missing:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 授权交接命令模板复核已记录：模板不可盲贴执行，必须替换占位符并独立确认授权与最终提交。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=f"External L3 命令模板复核缺失或不完整: {', '.join(missing)}",
    )


def _external_l3_evidence_manifest_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 证据清单不可读取: {exc}",
        )

    manifest = payload.get("evidence_manifest") or {}
    entries = {
        str(item.get("id", "")): item
        for item in manifest.get("entries") or []
        if isinstance(item, dict)
    }
    required_entry_ids = {
        "external_l3_validation_json",
        "external_l3_validation_markdown",
        "live_run_readiness",
        "submit_safety_decision",
        "live_input_artifacts",
        "rate_limit_policy",
        "session_readiness",
        "forbidden_input_audit",
        "target_confirmation_audit",
        "operator_handoff",
        "external_l3_live_run_runbook",
        "post_submit_feedback_traceability",
        "feedback_source_artifact",
    }
    if payload.get("status") == "live_blocker_recorded":
        required_entry_ids.add("live_blocker")
    if payload.get("status") == "external_validated":
        required_entry_ids.update({"submission_log_yaml", "submission_log_json"})

    missing = []
    if manifest.get("status") != "complete":
        missing.append("status")
    if manifest.get("raw_live_inputs_persisted") is not False:
        missing.append("raw_live_inputs_persisted")
    for entry_id in sorted(required_entry_ids):
        entry = entries.get(entry_id)
        if not entry:
            missing.append(entry_id)
            continue
        if entry.get("required") is not True:
            missing.append(f"{entry_id}.required")
        if entry.get("present") is not True:
            missing.append(f"{entry_id}.present")
        if entry.get("raw_live_inputs_persisted") is not False:
            missing.append(f"{entry_id}.raw_live_inputs_persisted")
    runbook = (payload.get("operator_handoff") or {}).get("runbook") or {}
    runbook_entry = entries.get("external_l3_live_run_runbook") or {}
    runbook_path = str(runbook.get("path", ""))
    runbook_file = Path(runbook_path)
    required_sections = runbook.get("required_sections") or []
    required_sections_present = runbook.get("required_sections_present") or {}
    runbook_ready = (
        runbook_entry.get("location") == runbook_path
        and runbook_entry.get("status") == "fingerprinted_and_sections_complete"
        and runbook_file.is_file()
        and runbook.get("sha256") == _sha256_path(runbook_file)
        and bool(required_sections)
        and all(
            required_sections_present.get(section) is True
            for section in required_sections
        )
    )
    if not runbook_ready:
        missing.append("external_l3_live_run_runbook.fingerprint_or_sections")
    markdown_fragments = [
        "## 证据清单",
        f"- 状态: `{manifest.get('status', '')}`",
        (
            "- 原始 live 输入是否持久化: "
            f"`{manifest.get('raw_live_inputs_persisted', True)}`"
        ),
        "| 证据 | 类型 | 必需 | 存在 | 状态 | 位置 |",
    ]
    missing.extend(
        fragment for fragment in markdown_fragments if fragment not in markdown
    )
    for entry_id, entry in sorted(entries.items()):
        row = _external_l3_evidence_manifest_markdown_row(entry)
        if row not in markdown:
            missing.append(f"{entry_id}.markdown_row")
    if not missing:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 证据清单已记录 validation、handoff、live run runbook、feedback source 和真实 submission log 期望状态，且 Markdown 与 JSON 清单一致。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=f"External L3 证据清单缺失或不完整: {', '.join(missing)}",
    )


def _external_l3_evidence_manifest_markdown_row(entry: dict[str, Any]) -> str:
    return (
        "| "
        + " | ".join(
            [
                f"`{entry.get('id', '')}`",
                f"`{entry.get('artifact_type', '')}`",
                f"`{entry.get('required', False)}`",
                f"`{entry.get('present', False)}`",
                f"`{entry.get('status', '')}`",
                f"`{entry.get('location', '')}`",
            ]
        )
        + " |"
    )


def _external_l3_outcome_summary_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 结果分级证据不可读取: {exc}",
        )

    outcome = payload.get("outcome_summary") or {}
    status = payload.get("status")
    expected_outcome = (
        "external_validated"
        if status == "external_validated"
        else (
            "post_command_blocker_recorded"
            if payload.get("external_submission_attempted") is True
            else "pre_submit_blocker_recorded"
        )
    )
    missing = []
    if outcome.get("outcome") != expected_outcome:
        missing.append("outcome")
    if outcome.get("external_submission_attempted") is not payload.get(
        "external_submission_attempted"
    ):
        missing.append("external_submission_attempted")
    if outcome.get("external_l3_success") is not (status == "external_validated"):
        missing.append("external_l3_success")
    if outcome.get("p0_017_complete") is not (status == "external_validated"):
        missing.append("p0_017_complete")
    blocker = payload.get("live_blocker") or {}
    blocker_reason = str(blocker.get("reason", ""))
    if outcome.get("blocker_resolution_required") is not bool(blocker_reason):
        missing.append("blocker_resolution_required")
    if blocker_reason and outcome.get("blocker_reason") != blocker_reason:
        missing.append("blocker_reason")
    if not outcome.get("acceptance_status_meaning"):
        missing.append("acceptance_status_meaning")
    if not outcome.get("next_action"):
        missing.append("next_action")
    if blocker_reason and outcome.get("next_action") != blocker.get("next_action"):
        missing.append("next_action_matches_live_blocker")

    markdown_fragments = [
        "## 结果分级",
        f"- Outcome: `{outcome.get('outcome', '')}`",
        f"- Acceptance pass 含义: `{outcome.get('acceptance_status_meaning', '')}`",
        f"- 是否已真实验证成功: `{outcome.get('external_l3_success', False)}`",
        f"- 是否已尝试外部提交: `{outcome.get('external_submission_attempted', False)}`",
        f"- 是否需要阻断处理: `{outcome.get('blocker_resolution_required', False)}`",
        f"- P0-017 是否完成: `{outcome.get('p0_017_complete', False)}`",
    ]
    missing.extend(
        fragment for fragment in markdown_fragments if fragment not in markdown
    )
    if blocker_reason:
        markdown_blocker_reason = f"- 阻断原因: `{blocker_reason}`"
        if markdown_blocker_reason not in markdown:
            missing.append("markdown_blocker_reason")
        markdown_next_action = f"- 下一步: {blocker.get('next_action', '')}"
        if markdown_next_action not in markdown:
            missing.append("markdown_next_action")
    if not missing:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 结果分级已记录，区分 evidence pass、真实验证成功和仍需处理的 blocker。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=f"External L3 结果分级缺失或不一致: {', '.join(missing)}",
    )


def _external_l3_manual_session_readiness_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 人工会话准备证据不可读取: {exc}",
        )

    session_readiness = payload.get("session_readiness") or {}
    readiness_gates = {
        str(gate.get("id", "")): gate
        for gate in (payload.get("live_run_readiness") or {}).get("gates", [])
        if isinstance(gate, dict)
    }
    handoff_required_env = {
        str(item.get("name", "")): item
        for item in (payload.get("operator_handoff") or {}).get("required_env", [])
        if isinstance(item, dict)
    }
    missing = []
    if not session_readiness:
        missing.append("session_readiness")
    if session_readiness.get("manual_login_required") is not True:
        missing.append("manual_login_required")
    if session_readiness.get("browser_automation_enters_credentials") is not False:
        missing.append("browser_automation_enters_credentials")
    if session_readiness.get("browser_automation_solves_challenge") is not False:
        missing.append("browser_automation_solves_challenge")
    if session_readiness.get("raw_credentials_persisted") is not False:
        missing.append("raw_credentials_persisted")
    for field in (
        "session_dir_exists",
        "channel_session_dir_exists",
        "channel_session_dir_has_state",
        "channel_session_state_markers",
        "session_storage_ready",
    ):
        if field not in session_readiness:
            missing.append(field)
    session_gate = readiness_gates.get("manual_session_ready_confirmed") or {}
    if not session_gate:
        missing.append("manual_session_ready_confirmed")
    storage_gate = readiness_gates.get("manual_session_storage_ready") or {}
    if not storage_gate:
        missing.append("manual_session_storage_ready")
    expected_status = (
        "pass"
        if session_readiness.get("session_ready_confirmed") is True
        else "blocked"
    )
    if session_gate and session_gate.get("status") != expected_status:
        missing.append("manual_session_ready_confirmed.status")
    expected_storage_status = (
        "pass"
        if session_readiness.get("session_storage_ready") is True
        else "blocked"
    )
    if storage_gate and storage_gate.get("status") != expected_storage_status:
        missing.append("manual_session_storage_ready.status")
    required_env = handoff_required_env.get("PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED")
    if not required_env:
        missing.append("PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED")

    if (
        payload.get("external_submission_attempted") is True
        and session_readiness.get("session_ready_confirmed") is not True
    ):
        missing.append("external_submission_started_without_session_ready")
    if (
        payload.get("external_submission_attempted") is True
        and session_readiness.get("session_storage_ready") is not True
    ):
        missing.append("external_submission_started_without_session_storage")

    markdown_fragments = [
        "## 人工会话准备",
        "- 已确认共享登录会话可用:",
        "- 会话根目录是否存在:",
        "- Liepin 持久化会话目录是否存在:",
        "- Liepin 持久化会话目录是否包含状态文件:",
        "- Liepin 持久化会话状态标记:",
        "- 会话存储是否就绪:",
        "- 自动化是否输入凭据: `False`",
        "- 自动化是否处理验证码或短信码: `False`",
        "`manual_session_ready_confirmed`",
        "`manual_session_storage_ready`",
    ]
    missing.extend(
        fragment for fragment in markdown_fragments if fragment not in markdown
    )
    if not missing:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 人工会话准备 gate 已记录；未确认共享登录会话前不会启动真实渠道命令。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=f"External L3 人工会话准备 gate 缺失或不一致: {', '.join(missing)}",
    )


def _external_l3_pre_submit_blocker_diagnostics_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 pre-submit blocker 诊断证据不可读取: {exc}",
        )
    if payload.get("external_submission_attempted") is True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 已执行真实渠道命令，因此没有 pre-submit blocker 诊断要求。",
        )
    blocker = payload.get("live_blocker") or {}
    diagnostics = blocker.get("diagnostics") or {}
    failed_checks = blocker.get("failed_checks") or []
    input_artifacts = diagnostics.get("live_input_artifacts") or {}
    job_url = input_artifacts.get("job_url") or {}
    missing = []
    markdown_fragments = [
        "## Live Blocker",
        f"- Failed Checks: `{', '.join(failed_checks)}`",
        f"- Submit 命令允许启动: `{diagnostics.get('submit_command_allowed', '')}`",
        f"- Missing Gates: `{', '.join(diagnostics.get('missing_gates', []))}`",
        f"- 诊断 Job URL 已提供: `{job_url.get('present', False)}`",
        f"- 诊断 Job URL 原值是否持久化: `{job_url.get('raw_value_persisted', True)}`",
    ]
    missing.extend(
        f"markdown:{fragment}"
        for fragment in markdown_fragments
        if fragment not in markdown
    )
    if (
        payload.get("status") == "live_blocker_recorded"
        and isinstance(failed_checks, list)
        and diagnostics.get("submit_command_allowed") is False
        and isinstance(diagnostics.get("missing_gates"), list)
        and isinstance(diagnostics.get("readiness_gates"), list)
        and isinstance(diagnostics.get("live_input_artifacts"), dict)
        and not missing
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message=(
                "External L3 pre-submit blocker 已记录 readiness 诊断: "
                f"{blocker.get('reason', 'unknown')}。"
            ),
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=(
            "External L3 pre-submit blocker 缺少 missing gates、输入审计诊断，"
            "或 Markdown 与 JSON 不一致: "
            + ", ".join(missing)
        ),
    )


def _external_l3_timeout_blocker_result(step: AcceptanceStep) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 timeout blocker 证据不可读取: {exc}",
        )
    if payload.get("command_timed_out") is not True:
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 本次未发生真实渠道命令超时。",
        )
    blocker = payload.get("live_blocker") or {}
    diagnostics = blocker.get("diagnostics") or {}
    markdown_fragments = [
        "## Live Blocker",
        "- Reason: `external_channel_command_timed_out`",
        "- 是否超时: `True`",
        f"- Timeout 秒数: `{diagnostics.get('timeout_seconds', '')}`",
    ]
    missing = [
        f"markdown:{fragment}"
        for fragment in markdown_fragments
        if fragment not in markdown
    ]
    if (
        payload.get("status") == "live_blocker_recorded"
        and blocker.get("reason") == "external_channel_command_timed_out"
        and diagnostics.get("command_timed_out") is True
        and diagnostics.get("timeout_seconds") is not None
        and not missing
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 真实渠道命令超时已记录为可审计 live blocker。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=(
            "External L3 真实渠道命令超时未记录为精确 live blocker，"
            "或 Markdown 与 JSON 不一致: "
            + ", ".join(missing)
        ),
    )


def _external_l3_command_error_blocker_result(
    step: AcceptanceStep,
) -> JourneyStepResult:
    if step.status != "pass":
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=step.message,
        )
    try:
        evidence_path = Path(step.evidence)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        markdown = evidence_path.with_suffix(".md").read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        return JourneyStepResult(
            status="fail",
            evidence=step.evidence,
            message=f"External L3 command error blocker 证据不可读取: {exc}",
        )
    if not payload.get("command_error"):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 本次未发生真实渠道命令启动错误。",
        )
    blocker = payload.get("live_blocker") or {}
    diagnostics = blocker.get("diagnostics") or {}
    command_error = diagnostics.get("command_error") or {}
    markdown_fragments = [
        "## Live Blocker",
        "- Reason: `external_channel_command_launch_failed`",
        f"- Command Error: `{command_error.get('type', '')}`",
        f"- Command Error Message: `{command_error.get('message', '')}`",
    ]
    missing = [
        f"markdown:{fragment}"
        for fragment in markdown_fragments
        if fragment not in markdown
    ]
    if (
        payload.get("status") == "live_blocker_recorded"
        and blocker.get("reason") == "external_channel_command_launch_failed"
        and command_error.get("type")
        and command_error.get("message") is not None
        and not missing
    ):
        return JourneyStepResult(
            status="pass",
            evidence=step.evidence,
            message="External L3 真实渠道命令启动错误已记录为可审计 live blocker。",
        )
    return JourneyStepResult(
        status="fail",
        evidence=step.evidence,
        message=(
            "External L3 真实渠道命令启动错误未记录为精确 live blocker，"
            "或 Markdown 与 JSON 不一致: "
            + ", ".join(missing)
        ),
    )


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
