#!/usr/bin/env python3
import argparse
import datetime
import os
import subprocess
from pathlib import Path
from typing import cast


def has_llm_env() -> bool:
    return bool(os.getenv("LLM_API_KEY")) and bool(os.getenv("LLM_MODEL"))


def run_step(cmd: list[str], name: str) -> int:
    print(f"[pipeline] {name}: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"[pipeline] failed at step: {name}")
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run end-to-end PiProofForge pipeline")
    _ = parser.add_argument("--raw", required=True, help="Raw material input path")
    _ = parser.add_argument("--job-profile", required=True, help="Job profile yaml path")
    _ = parser.add_argument("--run-id", help="Run id, default timestamp")
    _ = parser.add_argument("--use-llm", action="store_true", help="Enable LLM for extraction/matching/generation/evaluation")
    _ = parser.add_argument("--require-llm", action="store_true", help="Fail if any LLM step is unavailable")
    args = parser.parse_args()

    raw_path = cast(str, args.raw)
    job_profile = cast(str, args.job_profile)
    run_id = cast(str | None, args.run_id) or datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    use_llm = cast(bool, args.use_llm)
    require_llm = cast(bool, args.require_llm)

    if require_llm and not use_llm:
        print("[pipeline] --require-llm requires --use-llm")
        return 1

    evidence_output = Path("evidence_cards") / f"ec-{run_id}.yaml"
    matching_output = Path("matching_reports") / f"mr-{run_id}.yaml"
    resume_dir = Path("outputs") / run_id
    scorecard_output = Path("outputs/scorecards") / f"scorecard_mr-{run_id}_A.md"

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
            code = run_step(extract_cmd, "evidence-extraction-llm")
            if code != 0:
                return code
        elif require_llm:
            print("[pipeline] LLM required but env is missing (LLM_API_KEY/LLM_MODEL)")
            return 1
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
            code = run_step(extract_cmd, "evidence-extraction-rule")
            if code != 0:
                return code
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
        code = run_step(extract_cmd, "evidence-extraction-rule")
        if code != 0:
            return code

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
    code = run_step(match_cmd, "matching-scoring")
    if code != 0:
        return code

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
    code = run_step(gen_cmd, "generation")
    if code != 0:
        return code

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
    code = run_step(eval_cmd, "evaluation")
    if code != 0:
        return code

    print("[pipeline] done")
    print(f"- evidence: {evidence_output}")
    print(f"- matching: {matching_output}")
    print(f"- resume A/B: {resume_dir}")
    print(f"- scorecard: {scorecard_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
