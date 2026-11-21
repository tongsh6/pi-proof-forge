"""匹配与评分编排。

把「读输入 → 策略门禁 → 语义评审或规则报告 → 写产物」的流程集中在这里，
CLI 只解析参数并调用本模块，不得在入口层重复实现流程。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError

from tools.domain.result import Err
from tools.domain.value_objects import Candidate
from tools.engines.matching import rule_scorer
from tools.engines.matching import semantic_matching
from tools.infra.llm import client as llm
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.policy.audit import write_exclusion_audit
from tools.policy.exclusions import (
    load_exclusion_list,
    load_legal_entity_exclusion_list,
)
from tools.policy.gate import evaluate_candidate_exclusion

_SEMANTIC_ERROR_MESSAGES = {
    "career_direction_jd_body_missing": "请先补齐并审核完整 JD，再评估求职方向",
    "career_direction_empty_content": "求职方向评估未返回正文，一次纠错后仍为空；请检查模型结构化输出与推理设置",
    "career_direction_invalid_json": "求职方向评估未返回有效 JSON，一次纠错后仍无效；请检查模型结构化输出设置",
    "job_preferences_source_changed": "求职偏好的来源材料已变化，请到简历中心重新提炼并确认",
}


@dataclass(frozen=True)
class MatchingFlowConfig:
    job_profile_path: Path
    evidence_dir: Path
    output_path: Path
    personal_profile_path: Path
    use_llm: bool = False
    require_llm: bool = False
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    llm_max_cards: int = rule_scorer.DEFAULT_LLM_MAX_CARDS


def _candidate_from_profile(job_profile_path: Path) -> Candidate:
    job_doc = parse_simple_yaml(job_profile_path.read_text(encoding="utf-8"))
    return Candidate(
        candidate_id=f"cand-{job_profile_path.stem}",
        direction=job_doc["scalars"].get("target_role", ""),
        company=job_doc["scalars"].get("company", ""),
        job_url=job_doc["scalars"].get("source_jd", ""),
        confidence=0.5,
        source="job_profiles",
        merged_sources=("job_profiles",),
        legal_entity=job_doc["scalars"].get("legal_entity", ""),
    )


def _check_policy(config: MatchingFlowConfig) -> int | None:
    candidate = _candidate_from_profile(config.job_profile_path)
    exclusions = load_exclusion_list()
    legal_entity_exclusions = load_legal_entity_exclusion_list()
    gate_result = evaluate_candidate_exclusion(
        candidate,
        exclusions,
        legal_entity_exclusions,
    )
    if isinstance(gate_result, Err):
        run_log = config.output_path.parent / "run_log.json"
        write_exclusion_audit(
            run_log,
            candidate,
            "gate_fallback",
            gate_result.error.reason,
        )
        print(f"[matching] skipped: {gate_result.error.details}")
        return 2
    return None


def _run_semantic(config: MatchingFlowConfig, evidence_files: list[Path]) -> int | None:
    """语义评审；返回 None 表示已成功写出报告，返回 1 表示需终止失败。"""
    model = config.model
    api_key = config.api_key
    provider = os.getenv("LLM_PROVIDER", "")
    if not llm.llm_request_available(
        provider=provider, api_key=api_key, model=model, base_url=config.base_url
    ):
        if config.require_llm:
            print("LLM mode required but model/api_key is missing")
            return 1
        return None

    try:
        client = llm.LLMClient(
            base_url=config.base_url,
            api_key=api_key,
            timeout=llm.llm_timeout_from_env(),
            provider=provider,
        )
        result = semantic_matching.run_semantic_matching(
            job_path=config.job_profile_path,
            evidence_files=evidence_files,
            personal_profile=config.personal_profile_path,
            client=client,
            model=model,
            cache_dir=config.output_path.parent / ".semantic-cache",
            batch_size=max(1, config.llm_max_cards),
        )
        semantic_matching.write_semantic_report(config.output_path, result)
        if result.get("direction_review"):
            config.output_path.with_suffix(".direction.json").write_text(
                json.dumps(result["direction_review"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        statistics = result.get("statistics", {})
        print(
            f"[matching] semantic: {len(result['reviewed_card_ids'])}/"
            f"{len(evidence_files)} cards; {statistics}"
        )
        return 0
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        detail = _semantic_error_detail(exc)
        print(f"[matching] 语义评审失败：{detail}")
        if config.require_llm:
            return 1
        print("[matching] 已显式回退规则模式；本次没有有效语义结果。")
        return None


def _semantic_error_detail(exc: BaseException) -> str:
    code = str(exc)
    detail = _SEMANTIC_ERROR_MESSAGES.get(
        code,
        code
        if code.startswith(("semantic_", "career_direction_", "job_preferences_"))
        else type(exc).__name__,
    )
    if isinstance(exc, HTTPError):
        detail = (
            f"推理后台暂时不可用（HTTP {exc.code} {exc.reason}），已做有限重试仍失败；"
            "请稍后重试或减少同时运行的推理任务"
        )
    return detail


def _pool_evidence_files(evidence_dir: Path) -> list[Path]:
    """只把已入池卡送入匹配；样例卡与草稿不得参与评分。"""
    from tools.infra.evidence_pool import pool_eligible_scalars
    from tools.infra.persistence.yaml_io import parse_simple_yaml

    files: list[Path] = []
    for path in sorted(evidence_dir.glob("*.yaml")):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        candidate_id = str(doc["scalars"].get("id") or path.stem)
        if pool_eligible_scalars(doc["scalars"], card_id=candidate_id):
            files.append(path)
    return files


def run_matching_flow(config: MatchingFlowConfig) -> int:
    """执行匹配与评分。返回进程退出码（0 成功、1 LLM 必需但失败、2 企业排除）。"""
    if config.require_llm and not config.use_llm:
        print("--require-llm requires --use-llm")
        return 1

    evidence_files = _pool_evidence_files(config.evidence_dir)
    if not evidence_files:
        print("[matching] 警告：没有可用的已入池证据卡，本次匹配结果为空。")
    config.output_path.parent.mkdir(parents=True, exist_ok=True)

    policy_exit = _check_policy(config)
    if policy_exit is not None:
        return policy_exit

    if config.use_llm:
        semantic_exit = _run_semantic(config, evidence_files)
        if semantic_exit == 0:
            return 0
        if semantic_exit == 1:
            return 1

    report = rule_scorer.build_rule_report(
        config.job_profile_path,
        evidence_files,
        version_id=config.output_path.stem,
    )
    _ = config.output_path.write_text(report, encoding="utf-8")
    return 0
