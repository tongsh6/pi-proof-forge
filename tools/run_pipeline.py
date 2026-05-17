#!/usr/bin/env python3
import argparse
import datetime
import os
import subprocess
from pathlib import Path
import sys
from typing import cast

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.discovery.filters import filter_candidates_by_policy

from tools.domain.events import RunEvent
from tools.domain.result import Err
from tools.domain.value_objects import Candidate
from tools.infra.persistence.file_run_store import FileRunStore
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.policy.audit import write_exclusion_audit
from tools.policy.exclusions import (
    load_exclusion_list,
    load_legal_entity_exclusion_list,
    match_exclusion,
    PolicyExclusions,
)
from tools.policy.gate import evaluate_candidate_exclusion


def has_llm_env() -> bool:
    return bool(os.getenv("LLM_API_KEY")) and bool(os.getenv("LLM_MODEL"))


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _append_pipeline_event(
    run_store: FileRunStore,
    run_id: str,
    event_type: str,
    payload: dict[str, object],
) -> None:
    run_store.append_event(
        RunEvent(
            run_id=run_id,
            event_type=event_type,
            round_index=0,
            payload=payload,
            timestamp=_now_utc(),
        )
    )


def _finish_pipeline_run(
    run_store: FileRunStore,
    run_id: str,
    status: str,
    exit_code: int,
    artifacts: dict[str, object],
    *,
    reason: str = "",
    failed_step: str = "",
) -> int:
    payload: dict[str, object] = {
        "status": status,
        "exit_code": exit_code,
        "artifacts": artifacts,
    }
    if reason:
        payload["reason"] = reason
    if failed_step:
        payload["failed_step"] = failed_step
    _append_pipeline_event(
        run_store,
        run_id,
        "PIPELINE_DONE" if exit_code == 0 else "PIPELINE_FAILED",
        payload,
    )
    run_store.finalize(
        run_id,
        {
            "run_id": run_id,
            "status": status,
            "exit_code": exit_code,
            "reason": reason,
            "failed_step": failed_step,
            "artifacts": artifacts,
            "finished_at": _now_utc(),
        },
    )
    return exit_code


def run_step(
    cmd: list[str],
    name: str,
    *,
    run_store: FileRunStore | None = None,
    run_id: str | None = None,
) -> int:
    if run_store is not None and run_id is not None:
        _append_pipeline_event(
            run_store,
            run_id,
            "PIPELINE_STEP_START",
            {"step": name, "command": cmd},
        )
    print(f"[pipeline] {name}: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"[pipeline] failed at step: {name}")
        if run_store is not None and run_id is not None:
            _append_pipeline_event(
                run_store,
                run_id,
                "PIPELINE_STEP_FAILURE",
                {"step": name, "command": cmd, "returncode": result.returncode},
            )
    elif run_store is not None and run_id is not None:
        _append_pipeline_event(
            run_store,
            run_id,
            "PIPELINE_STEP_SUCCESS",
            {"step": name, "command": cmd, "returncode": result.returncode},
        )
    return result.returncode


def _legacy_main() -> int:
    parser = argparse.ArgumentParser(description="Run end-to-end PiProofForge pipeline")
    _ = parser.add_argument("--raw", required=True, help="Raw material input path")
    _ = parser.add_argument(
        "--job-profile", required=True, help="Job profile yaml path"
    )
    _ = parser.add_argument("--run-id", help="Run id, default timestamp")
    _ = parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Enable LLM for extraction/matching/generation/evaluation",
    )
    _ = parser.add_argument(
        "--require-llm", action="store_true", help="Fail if any LLM step is unavailable"
    )
    args = parser.parse_args()

    raw_path = cast(str, args.raw)
    job_profile = cast(str, args.job_profile)
    run_id = cast(str | None, args.run_id) or datetime.datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )
    use_llm = cast(bool, args.use_llm)
    require_llm = cast(bool, args.require_llm)
    run_store = FileRunStore(base_dir=str(Path("outputs") / "agent_runs"))
    artifacts: dict[str, object] = {
        "raw": raw_path,
        "job_profile": job_profile,
    }
    _append_pipeline_event(
        run_store,
        run_id,
        "PIPELINE_START",
        {
            "raw": raw_path,
            "job_profile": job_profile,
            "use_llm": use_llm,
            "require_llm": require_llm,
            "mode": "legacy_subprocess",
        },
    )

    if require_llm and not use_llm:
        print("[pipeline] --require-llm requires --use-llm")
        return _finish_pipeline_run(
            run_store,
            run_id,
            "FAILED",
            1,
            artifacts,
            reason="require_llm_requires_use_llm",
        )

    job_doc = parse_simple_yaml(Path(job_profile).read_text(encoding="utf-8"))
    company = job_doc["scalars"].get("company", "")
    candidate = Candidate(
        candidate_id=f"cand-{Path(job_profile).stem}",
        direction=job_doc["scalars"].get("target_role", ""),
        company=company,
        job_url=job_doc["scalars"].get("source_jd", ""),
        confidence=0.5,
        source="job_profiles",
        merged_sources=("job_profiles",),
        legal_entity=job_doc["scalars"].get("legal_entity", ""),
    )
    exclusions = load_exclusion_list()
    legal_entity_exclusions = load_legal_entity_exclusion_list()
    policy = PolicyExclusions(
        company_rules=tuple(exclusions),
        legal_entities=tuple(legal_entity_exclusions),
    )
    _kept, excluded = filter_candidates_by_policy(
        [candidate],
        exclusions,
        legal_entity_exclusions,
    )
    if excluded:
        run_log = Path("outputs") / run_id / "run_log.json"
        exclusion_reason = match_exclusion(
            candidate.company, candidate.legal_entity, policy
        )
        write_exclusion_audit(
            run_log,
            candidate,
            "discovery_filter",
            exclusion_reason or "excluded_company",
        )
        _append_pipeline_event(
            run_store,
            run_id,
            "PIPELINE_POLICY_EXCLUDED",
            {
                "candidate_id": candidate.candidate_id,
                "company": candidate.company,
                "legal_entity": candidate.legal_entity,
                "reason": exclusion_reason or "excluded_company",
                "source": "discovery_filter",
            },
        )
        print(f"[pipeline] skipped: job profile company excluded: {company}")
        return _finish_pipeline_run(
            run_store,
            run_id,
            "SKIPPED",
            2,
            artifacts,
            reason=exclusion_reason or "excluded_company",
        )
    gate_result = evaluate_candidate_exclusion(
        candidate,
        exclusions,
        legal_entity_exclusions,
    )
    if isinstance(gate_result, Err):
        run_log = Path("outputs") / run_id / "run_log.json"
        write_exclusion_audit(
            run_log,
            candidate,
            "gate_fallback",
            gate_result.error.reason,
        )
        _append_pipeline_event(
            run_store,
            run_id,
            "PIPELINE_POLICY_EXCLUDED",
            {
                "candidate_id": candidate.candidate_id,
                "company": candidate.company,
                "legal_entity": candidate.legal_entity,
                "reason": gate_result.error.reason,
                "source": "gate_fallback",
            },
        )
        print(f"[pipeline] skipped: {gate_result.error.details}")
        return _finish_pipeline_run(
            run_store,
            run_id,
            "SKIPPED",
            2,
            artifacts,
            reason=gate_result.error.reason,
        )

    evidence_output = Path("evidence_cards") / f"ec-{run_id}.yaml"
    matching_output = Path("matching_reports") / f"mr-{run_id}.yaml"
    resume_dir = Path("outputs") / run_id
    scorecard_output = Path("outputs/scorecards") / f"scorecard_mr-{run_id}_A.md"
    artifacts.update(
        {
            "evidence": str(evidence_output),
            "matching": str(matching_output),
            "resume_dir": str(resume_dir),
            "scorecard": str(scorecard_output),
            "run_record": str(Path("outputs") / "agent_runs" / run_id / "run_log.json"),
        }
    )

    evidence_output.parent.mkdir(parents=True, exist_ok=True)
    matching_output.parent.mkdir(parents=True, exist_ok=True)
    resume_dir.mkdir(parents=True, exist_ok=True)
    scorecard_output.parent.mkdir(parents=True, exist_ok=True)

    if use_llm:
        if has_llm_env():
            extract_cmd = [
                "python3",
                "tools/extract_evidence_llm.py",
                "--input",
                raw_path,
                "--output",
                str(evidence_output),
            ]
            code = run_step(
                extract_cmd,
                "evidence-extraction-llm",
                run_store=run_store,
                run_id=run_id,
            )
            if code != 0:
                return _finish_pipeline_run(
                    run_store,
                    run_id,
                    "FAILED",
                    code,
                    artifacts,
                    failed_step="evidence-extraction-llm",
                )
        elif require_llm:
            print("[pipeline] LLM required but env is missing (LLM_API_KEY/LLM_MODEL)")
            return _finish_pipeline_run(
                run_store,
                run_id,
                "FAILED",
                1,
                artifacts,
                reason="missing_llm_env",
                failed_step="evidence-extraction-llm",
            )
        else:
            extract_cmd = [
                "python3",
                "tools/run_evidence_extraction.py",
                "--input",
                raw_path,
                "--output",
                str(evidence_output),
                "--id",
                f"ec-{run_id}",
            ]
            code = run_step(
                extract_cmd,
                "evidence-extraction-rule",
                run_store=run_store,
                run_id=run_id,
            )
            if code != 0:
                return _finish_pipeline_run(
                    run_store,
                    run_id,
                    "FAILED",
                    code,
                    artifacts,
                    failed_step="evidence-extraction-rule",
                )
    else:
        extract_cmd = [
            "python3",
            "tools/run_evidence_extraction.py",
            "--input",
            raw_path,
            "--output",
            str(evidence_output),
            "--id",
            f"ec-{run_id}",
        ]
        code = run_step(
            extract_cmd,
            "evidence-extraction-rule",
            run_store=run_store,
            run_id=run_id,
        )
        if code != 0:
            return _finish_pipeline_run(
                run_store,
                run_id,
                "FAILED",
                code,
                artifacts,
                failed_step="evidence-extraction-rule",
            )

    match_cmd = [
        "python3",
        "tools/run_matching_scoring.py",
        "--job-profile",
        job_profile,
        "--evidence-dir",
        "evidence_cards",
        "--output",
        str(matching_output),
    ]
    if use_llm:
        match_cmd.append("--use-llm")
    if require_llm:
        match_cmd.append("--require-llm")
    code = run_step(match_cmd, "matching-scoring", run_store=run_store, run_id=run_id)
    if code != 0:
        return _finish_pipeline_run(
            run_store,
            run_id,
            "FAILED",
            code,
            artifacts,
            failed_step="matching-scoring",
        )

    gen_cmd = [
        "python3",
        "tools/run_generation.py",
        "--matching-report",
        str(matching_output),
        "--output-dir",
        str(resume_dir),
    ]
    if use_llm:
        gen_cmd.append("--use-llm")
    if require_llm:
        gen_cmd.append("--require-llm")
    code = run_step(gen_cmd, "generation", run_store=run_store, run_id=run_id)
    if code != 0:
        return _finish_pipeline_run(
            run_store,
            run_id,
            "FAILED",
            code,
            artifacts,
            failed_step="generation",
        )

    resume_a = resume_dir / f"resume_mr-{run_id}_A.md"
    eval_cmd = [
        "python3",
        "tools/run_evaluation.py",
        "--input",
        str(resume_a),
        "--output",
        str(scorecard_output),
        "--job-profile",
        job_profile,
    ]
    if use_llm:
        eval_cmd.append("--use-llm")
    if require_llm:
        eval_cmd.append("--require-llm")
    code = run_step(eval_cmd, "evaluation", run_store=run_store, run_id=run_id)
    if code != 0:
        return _finish_pipeline_run(
            run_store,
            run_id,
            "FAILED",
            code,
            artifacts,
            failed_step="evaluation",
        )

    print("[pipeline] done")
    print(f"- evidence: {evidence_output}")
    print(f"- matching: {matching_output}")
    print(f"- resume A/B: {resume_dir}")
    print(f"- scorecard: {scorecard_output}")
    print(f"- run record: {Path('outputs') / 'agent_runs' / run_id / 'run_log.json'}")
    return _finish_pipeline_run(run_store, run_id, "DONE", 0, artifacts)


def main() -> int:
    if os.getenv("PPF_FORCE_LEGACY_MAIN") == "1":
        return _legacy_main()

    from tools.cli.commands.pipeline import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
