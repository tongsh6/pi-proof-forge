"""核心 pipeline 编排。

两件事：
1. ``LinearPipeline``：Stage 序列组合（通用编排原语）。
2. ``run_pipeline_flow``：单次四阶段 pipeline（证据提炼 → 匹配评分 → 简历生成
   → 质量评测）。阶段之间是进程内纯 Python 调用，不再通过外部命令串联；
   每次运行写统一 Run Record（PIPELINE_START / PIPELINE_STEP_* / PIPELINE_DONE）。

Quick Run 由外层进程执行本模块（CLI ``pipeline`` 命令），进程边界只用于隔离
模型调用环境与超时控制，不是阶段间调用方式。
"""

from __future__ import annotations

import datetime
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.domain.events import RunEvent
from tools.domain.protocols import Stage, StageResult
from tools.domain.result import Err
from tools.domain.value_objects import Candidate
from tools.engines.evidence import llm_extractor, rule_extractor
from tools.infra.llm.client import default_base_url, llm_request_available
from tools.infra.persistence.file_run_store import FileRunStore
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.orchestration.evaluation_flow import (
    EvaluationFlowConfig,
    run_evaluation_flow,
)
from tools.orchestration.generation_flow import (
    GenerationFlowConfig,
    run_generation_flow,
)
from tools.orchestration.matching_flow import MatchingFlowConfig, run_matching_flow
from tools.policy.audit import write_exclusion_audit
from tools.policy.exclusions import (
    PolicyExclusions,
    load_exclusion_list,
    load_legal_entity_exclusion_list,
    match_exclusion,
)
from tools.policy.gate import evaluate_candidate_exclusion

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class LinearPipeline:
    """Linear sequence of Stage objects. Stops on first failure."""

    def __init__(self, stages: Sequence[Stage]) -> None:
        self._stages = tuple(stages)

    def run(self, context: dict[str, object]) -> StageResult:
        for stage in self._stages:
            result = stage.execute(context)
            if not result.success:
                return result
            context[stage.name] = result.data
        return StageResult(success=True, data=context)


@dataclass(frozen=True)
class PipelineFlowConfig:
    raw_path: Path
    job_profile_path: Path
    evidence_dir: Path
    run_id: str
    personal_profile_path: Path = Path("personal_profile.yaml")
    resume_positioning: str = "technical_depth"
    custom_positioning: str = ""
    use_llm: bool = False
    require_llm: bool = False
    skip_evidence_extraction: bool = False


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _append_event(
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


def _finish_run(
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
    _append_event(
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


def _mark_step(
    run_store: FileRunStore,
    run_id: str,
    step: str,
    event_type: str,
    extra: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {"step": step}
    if extra:
        payload.update(extra)
    _append_event(run_store, run_id, event_type, payload)


def has_llm_env() -> bool:
    return llm_request_available(
        provider=os.getenv("LLM_PROVIDER", ""),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", ""),
    )


def _llm_runtime_options() -> dict[str, str]:
    return {
        "model": os.getenv("LLM_MODEL", ""),
        "base_url": os.getenv("LLM_BASE_URL", "")
        or default_base_url(fallback=DEFAULT_BASE_URL),
        "api_key": os.getenv("LLM_API_KEY", ""),
    }


def _policy_exclusion_check(
    run_store: FileRunStore,
    run_id: str,
    job_profile_path: Path,
) -> tuple[int | None, dict[str, object]]:
    """企业例外清单检查；命中时返回退出码与原因。"""
    job_doc = parse_simple_yaml(job_profile_path.read_text(encoding="utf-8"))
    candidate = Candidate(
        candidate_id=f"cand-{job_profile_path.stem}",
        direction=job_doc["scalars"].get("target_role", ""),
        company=job_doc["scalars"].get("company", ""),
        job_url=job_doc["scalars"].get("source_jd", ""),
        confidence=0.5,
        source="job_profiles",
        merged_sources=("job_profiles",),
        legal_entity=job_doc["scalars"].get("legal_entity", ""),
    )
    exclusions = load_exclusion_list()
    legal_entity_exclusions = load_legal_entity_exclusion_list()

    from tools.discovery.filters import filter_candidates_by_policy

    policy = PolicyExclusions(
        company_rules=tuple(exclusions),
        legal_entities=tuple(legal_entity_exclusions),
    )
    kept, excluded = filter_candidates_by_policy(
        [candidate], exclusions, legal_entity_exclusions
    )
    _ = kept
    if excluded:
        reason = match_exclusion(
            candidate.company, candidate.legal_entity, policy
        ) or "excluded_company"
        write_exclusion_audit(
            Path("outputs") / run_id / "run_log.json",
            candidate,
            "discovery_filter",
            reason,
        )
        _append_event(
            run_store,
            run_id,
            "PIPELINE_POLICY_EXCLUDED",
            {
                "candidate_id": candidate.candidate_id,
                "company": candidate.company,
                "legal_entity": candidate.legal_entity,
                "reason": reason,
                "source": "discovery_filter",
            },
        )
        print(f"[pipeline] skipped: job profile company excluded: {candidate.company}")
        return 2, {"reason": reason}

    gate_result = evaluate_candidate_exclusion(
        candidate, exclusions, legal_entity_exclusions
    )
    if isinstance(gate_result, Err):
        write_exclusion_audit(
            Path("outputs") / run_id / "run_log.json",
            candidate,
            "gate_fallback",
            gate_result.error.reason,
        )
        _append_event(
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
        return 2, {"reason": gate_result.error.reason}
    return None, {}


def _run_evidence_stage(
    config: PipelineFlowConfig,
    run_store: FileRunStore,
    evidence_output: Path,
) -> int | None:
    """证据提炼阶段；返回 None 表示成功，否则返回退出码。"""
    run_id = config.run_id
    if config.skip_evidence_extraction:
        existing = sorted(config.evidence_dir.glob("*.yaml"))
        if not existing:
            print("[pipeline] no selected evidence cards found")
            return 1
        _mark_step(
            run_store,
            run_id,
            "evidence-selection",
            "PIPELINE_STEP_SUCCESS",
            {"evidence_dir": str(config.evidence_dir), "evidence_count": len(existing)},
        )
        return None

    if config.use_llm and not has_llm_env():
        if config.require_llm:
            print(
                "[pipeline] LLM required but env is missing (LLM_MODEL; keyless local providers need no LLM_API_KEY)"
            )
            return 1
        # 非严格模式：LLM 不可用时回退规则提炼。

    use_llm_extraction = config.use_llm and has_llm_env()
    step = "evidence-extraction-llm" if use_llm_extraction else "evidence-extraction-rule"
    _mark_step(run_store, run_id, step, "PIPELINE_STEP_START")
    try:
        if use_llm_extraction:
            options = _llm_runtime_options()
            client = _new_llm_client(options)
            prompt = llm_extractor.load_prompt_template(
                "tools/prompts/evidence-extraction.md",
                config.raw_path.read_text(encoding="utf-8"),
            )
            content = llm_extractor.extract_yaml_text(
                client, model=options["model"], prompt=prompt
            )
        else:
            text = config.raw_path.read_text(encoding="utf-8")
            draft = rule_extractor.build_draft(
                text,
                card_id=f"ec-{run_id}",
                raw_source=str(config.raw_path),
            )
            content = rule_extractor.dump_yaml(
                draft, rule_extractor.build_gaps(draft)
            )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[pipeline] failed at step: {step}: {exc}")
        _mark_step(run_store, run_id, step, "PIPELINE_STEP_FAILURE")
        return 1
    evidence_output.parent.mkdir(parents=True, exist_ok=True)
    _ = evidence_output.write_text(content, encoding="utf-8")
    _mark_step(run_store, run_id, step, "PIPELINE_STEP_SUCCESS")
    return None


def _new_llm_client(options: dict[str, str]):
    from tools.infra.llm.client import LLMClient, llm_timeout_from_env

    return LLMClient(
        base_url=options["base_url"],
        api_key=options["api_key"],
        timeout=llm_timeout_from_env(),
        provider=os.getenv("LLM_PROVIDER", ""),
    )


def run_pipeline_flow(config: PipelineFlowConfig) -> int:
    """执行单次四阶段 pipeline。返回进程退出码（0 成功、1 失败、2 策略跳过）。"""
    run_id = config.run_id
    run_store = FileRunStore(base_dir=str(Path("outputs") / "agent_runs"))
    artifacts: dict[str, object] = {
        "raw": str(config.raw_path),
        "job_profile": str(config.job_profile_path),
    }
    _append_event(
        run_store,
        run_id,
        "PIPELINE_START",
        {
            "raw": str(config.raw_path),
            "job_profile": str(config.job_profile_path),
            "use_llm": config.use_llm,
            "require_llm": config.require_llm,
            "skip_evidence_extraction": config.skip_evidence_extraction,
            "mode": "in_process",
        },
    )

    if config.require_llm and not config.use_llm:
        print("[pipeline] --require-llm requires --use-llm")
        return _finish_run(
            run_store,
            run_id,
            "FAILED",
            1,
            artifacts,
            reason="require_llm_requires_use_llm",
        )

    exclusion_code, exclusion_payload = _policy_exclusion_check(
        run_store, run_id, config.job_profile_path
    )
    if exclusion_code is not None:
        return _finish_run(
            run_store,
            run_id,
            "SKIPPED",
            exclusion_code,
            artifacts,
            reason=str(exclusion_payload.get("reason", "excluded_company")),
        )

    evidence_output = config.evidence_dir / f"ec-{run_id}.yaml"
    matching_output = Path("matching_reports") / f"mr-{run_id}.yaml"
    resume_dir = Path("outputs") / run_id
    scorecard_output = Path("outputs/scorecards") / f"scorecard_mr-{run_id}_A.md"
    artifacts.update(
        {
            "evidence": str(
                config.evidence_dir
                if config.skip_evidence_extraction
                else evidence_output
            ),
            "matching": str(matching_output),
            "resume_dir": str(resume_dir),
            "scorecard": str(scorecard_output),
            "scorecard_json": str(scorecard_output.with_suffix(".json")),
            "resume_trace": str(resume_dir / f"resume_mr-{run_id}_A.trace.json"),
            "run_record": str(Path("outputs") / "agent_runs" / run_id / "run_log.json"),
        }
    )
    for directory in (
        evidence_output.parent,
        matching_output.parent,
        resume_dir,
        scorecard_output.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    evidence_code = _run_evidence_stage(config, run_store, evidence_output)
    if evidence_code is not None:
        return _finish_run(
            run_store,
            run_id,
            "FAILED",
            evidence_code,
            artifacts,
            reason="no_selected_evidence_cards"
            if config.skip_evidence_extraction
            else "evidence_extraction_failed",
            failed_step="evidence-selection"
            if config.skip_evidence_extraction
            else "evidence-extraction",
        )

    llm_options = _llm_runtime_options()
    _mark_step(run_store, run_id, "matching-scoring", "PIPELINE_STEP_START")
    matching_code = run_matching_flow(
        MatchingFlowConfig(
            job_profile_path=config.job_profile_path,
            evidence_dir=config.evidence_dir,
            output_path=matching_output,
            personal_profile_path=config.personal_profile_path,
            use_llm=config.use_llm,
            require_llm=config.require_llm,
            model=llm_options["model"],
            base_url=llm_options["base_url"],
            api_key=llm_options["api_key"],
        )
    )
    if matching_code == 2:
        _mark_step(run_store, run_id, "matching-scoring", "PIPELINE_STEP_FAILURE")
        return _finish_run(
            run_store,
            run_id,
            "SKIPPED",
            2,
            artifacts,
            reason="matching_excluded",
            failed_step="matching-scoring",
        )
    if matching_code != 0:
        _mark_step(run_store, run_id, "matching-scoring", "PIPELINE_STEP_FAILURE")
        return _finish_run(
            run_store,
            run_id,
            "FAILED",
            matching_code,
            artifacts,
            failed_step="matching-scoring",
        )
    _mark_step(run_store, run_id, "matching-scoring", "PIPELINE_STEP_SUCCESS")

    _mark_step(run_store, run_id, "generation", "PIPELINE_STEP_START")
    generation_code = run_generation_flow(
        GenerationFlowConfig(
            matching_report_path=matching_output,
            output_dir=resume_dir,
            personal_profile_path=config.personal_profile_path,
            evidence_dir=config.evidence_dir,
            job_profile_path=config.job_profile_path,
            resume_positioning=config.resume_positioning,
            custom_positioning=config.custom_positioning,
            use_llm=config.use_llm,
            require_llm=config.require_llm,
            model=llm_options["model"],
            base_url=llm_options["base_url"],
            api_key=llm_options["api_key"],
        )
    )
    if generation_code != 0:
        _mark_step(run_store, run_id, "generation", "PIPELINE_STEP_FAILURE")
        return _finish_run(
            run_store,
            run_id,
            "FAILED",
            generation_code,
            artifacts,
            failed_step="generation",
        )
    _mark_step(run_store, run_id, "generation", "PIPELINE_STEP_SUCCESS")

    resume_a = resume_dir / f"resume_mr-{run_id}_A.md"
    _mark_step(run_store, run_id, "evaluation", "PIPELINE_STEP_START")
    evaluation_code = run_evaluation_flow(
        EvaluationFlowConfig(
            input_path=resume_a,
            output_path=scorecard_output,
            job_profile_path=config.job_profile_path,
            use_llm=config.use_llm,
            require_llm=config.require_llm,
            model=llm_options["model"],
            base_url=llm_options["base_url"],
            api_key=llm_options["api_key"],
        )
    )
    if evaluation_code != 0:
        _mark_step(run_store, run_id, "evaluation", "PIPELINE_STEP_FAILURE")
        return _finish_run(
            run_store,
            run_id,
            "FAILED",
            evaluation_code,
            artifacts,
            failed_step="evaluation",
        )
    _mark_step(run_store, run_id, "evaluation", "PIPELINE_STEP_SUCCESS")

    print("[pipeline] done")
    print(f"- evidence: {artifacts['evidence']}")
    print(f"- matching: {matching_output}")
    print(f"- resume A/B: {resume_dir}")
    print(f"- scorecard: {scorecard_output}")
    print(f"- run record: {Path('outputs') / 'agent_runs' / run_id / 'run_log.json'}")
    return _finish_run(run_store, run_id, "DONE", 0, artifacts)
