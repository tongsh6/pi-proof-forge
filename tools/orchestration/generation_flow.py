"""简历生成编排。

把「读匹配报告 → 校验语义绑定 → 选取证据 → 渲染 A/B 版 → 写产物与 trace」
的流程集中在这里。CLI 只解析参数并调用本模块。

事实边界：生成阶段只使用匹配报告选出的已审核证据卡与已确认职业档案；
LLM 只在未锁定语义结果时选择证据卡，不得改写证据字段，不得引入新事实。
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.engines.generation import resume_renderer
from tools.engines.matching.semantic_matching import load_semantic_report
from tools.infra.llm import client as llm

DEFAULT_PROMPT_PATH = "tools/prompts/generation.md"


@dataclass(frozen=True)
class GenerationFlowConfig:
    matching_report_path: Path
    output_dir: Path
    personal_profile_path: Path
    evidence_dir: Path = Path("evidence_cards")
    job_profile_path: Path | None = None
    resume_positioning: str = "technical_depth"
    custom_positioning: str = ""
    use_llm: bool = False
    require_llm: bool = False
    prompt_path: str = DEFAULT_PROMPT_PATH
    model: str = ""
    base_url: str = ""
    api_key: str = ""


def _read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _llm_select_cards(
    config: GenerationFlowConfig,
    *,
    report_text: str,
    cards: list[resume_renderer.CardView],
    profile: dict[str, Any],
    target: dict[str, Any],
    version: str,
) -> list[resume_renderer.CardView] | None:
    """用模型按 JD 选择证据卡；返回 None 表示不可用（调用方决定回退或阻断）。"""
    if not llm.llm_request_available(
        provider=os.getenv("LLM_PROVIDER", ""),
        api_key=config.api_key,
        model=config.model,
    ):
        raise ValueError("llm_configuration_missing")

    evidence_text = json.dumps(
        [
            {
                key: card[key]
                for key in ("id", "title", "context", "actions", "results", "stack")
            }
            for card in cards
        ],
        ensure_ascii=False,
    )
    prompt = resume_renderer.load_prompt(
        config.prompt_path, report_text, evidence_text, version
    )
    prompt = prompt.replace(
        "<PERSONAL_PROFILE>",
        json.dumps(
            {key: profile.get(key, "") for key in ("current_position", "city")},
            ensure_ascii=False,
        ),
    )
    prompt = prompt.replace(
        "<JOB_CONTEXT>",
        json.dumps(
            {
                key: target.get(key, "")
                for key in (
                    "company",
                    "target_role",
                    "jd_text",
                    "must_have",
                    "keywords",
                    "seniority_signal",
                )
            },
            ensure_ascii=False,
        ),
    )
    prompt = prompt.replace(
        "<POSITIONING>",
        str(config.custom_positioning or config.resume_positioning),
    )
    client = llm.LLMClient(
        base_url=config.base_url,
        api_key=config.api_key,
        timeout=llm.llm_timeout_from_env(),
    )
    response = client.post_json(
        client.chat_completions_url,
        {
            "model": config.model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    selection = json.loads(client.extract_content(response))
    ids = selection.get("evidence_ids") if isinstance(selection, dict) else None
    by_id = {card["id"]: card for card in cards}
    if (
        not isinstance(ids, list)
        or not ids
        or set(selection) != {"evidence_ids"}
        or not all(isinstance(item, str) and item in by_id for item in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("llm_selection_invalid")
    return [by_id[item] for item in ids]


def _check_semantic_binding(
    *,
    semantic: dict[str, Any],
    job_path: Path | None,
    cards: list[resume_renderer.CardView],
    profile_path: Path,
) -> None:
    if job_path and (
        hashlib.sha256(job_path.read_bytes()).hexdigest()
        != semantic["inputs"]["job_profile"]["sha256"]
    ):
        raise ValueError("semantic_target_changed")
    if not job_path:
        raise ValueError("semantic_target_changed")
    if any(
        card["source_sha256"] != semantic["inputs"][card["id"]]["sha256"]
        for card in cards
    ):
        raise ValueError("semantic_evidence_changed")
    expected_profile = semantic["inputs"].get("personal_profile")
    if expected_profile and (
        not profile_path.is_file()
        or hashlib.sha256(profile_path.read_bytes()).hexdigest()
        != expected_profile["sha256"]
    ):
        raise ValueError("semantic_personal_profile_changed")


def _build_trace(
    *,
    version: str,
    content: str,
    strategy: str,
    semantic: dict[str, Any] | None,
    profile: dict[str, Any],
    target: dict[str, Any],
    selected_cards: list[resume_renderer.CardView],
    claims: list[dict[str, Any]],
    paths: dict[str, Path],
    missing_profile: list[str],
    missing_target: list[str],
) -> dict[str, Any]:
    missing_evidence = [
        f"{card['id']}.{field}"
        for card in selected_cards
        for field in ("context", "role_scope", "time_range", "actions")
        if not card[field]
    ]
    if not resume_renderer.unique_stack(selected_cards):
        missing_evidence.append("skills")
    field_labels = {
        "context": "项目场景",
        "role_scope": "本人职责",
        "time_range": "经历时间",
        "actions": "具体行动",
    }
    evidence_reasons = [
        f"{card['title']}：待补"
        + "、".join(field_labels[f] for f in field_labels if not card[f])
        for card in selected_cards
        if any(not card[f] for f in field_labels)
    ]
    if not resume_renderer.unique_stack(selected_cards):
        evidence_reasons.append("缺少已审核的技能依据")
    from tools.infra.career_profile import career_generation_issues

    career_reasons = career_generation_issues(profile, selected_cards)
    for ref in profile.get("evidence_hashes", {}):
        paths["career_evidence:" + ref] = (
            Path(str(paths["personal_profile"])).parent / "evidence_cards" / f"{ref}.yaml"
        )
    return {
        "schema_version": 1,
        "version": version,
        "content_schema_version": 1,
        "career_revision": profile.get("revision", ""),
        "display_policy": "targeted_v1" if semantic else "complete_v1",
        "generation_strategy": strategy,
        "resume_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "evidence_card_ids": [card["id"] for card in selected_cards],
        "claims": claims,
        "field_provenance": {
            card["id"]: {
                "time_range": card.get("time_range_provenance"),
                "role_scope": card.get("role_scope_provenance"),
                "time_range_level": card.get("time_range_level", "L1"),
                "role_scope_level": card.get("role_scope_level", "L1"),
            }
            for card in selected_cards
        },
        "inputs": {
            key: {
                "path": str(path.resolve()),
                "exists": path.is_file(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
                if path.is_file()
                else "",
            }
            for key, path in paths.items()
        },
        "target": target,
        "readiness": {
            "status": "NEEDS_EVIDENCE"
            if missing_profile or missing_target or missing_evidence or career_reasons
            else "NEEDS_REVIEW",
            "deliverable": False,
            "missing_profile_fields": missing_profile,
            "missing_target_fields": missing_target,
            "missing_evidence_fields": missing_evidence,
            "missing_career_fields": career_reasons,
            "content_ready": not (
                missing_profile or missing_target or missing_evidence or career_reasons
            ),
            "reasons": (
                ["个人资料或目标岗位信息不完整"]
                if missing_profile or missing_target
                else []
            )
            + evidence_reasons
            + career_reasons
            + ["需人工审核简历事实与岗位适用性"],
        },
    }


def run_generation_flow(config: GenerationFlowConfig) -> int:
    """执行简历生成。返回进程退出码：0 成功、1 输入缺失/不合格/LLM 必需失败。"""
    if config.require_llm and not config.use_llm:
        print("--require-llm requires --use-llm")
        return 1

    report_path = config.matching_report_path
    report_id = report_path.stem
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        report_text = _read_text(report_path)
        score_total = resume_renderer.extract_score_total(report_text)
        cards = resume_renderer.load_cards(
            config.evidence_dir,
            resume_renderer.extract_top_card_ids(report_text),
            config.personal_profile_path.parent / "materials",
        )
        semantic = load_semantic_report(report_path)
        if semantic:
            _check_semantic_binding(
                semantic=semantic,
                job_path=config.job_profile_path,
                cards=cards,
                profile_path=config.personal_profile_path,
            )
        profile, target = resume_renderer.load_generation_context(
            config.personal_profile_path, config.job_profile_path
        )
        missing_profile = [
            key
            for key in ("name", "phone", "email", "city", "current_position")
            if not profile.get(key, "").strip()
        ]
        missing_target = [
            key for key in ("target_role", "company", "jd_text") if not target.get(key)
        ]
        artifacts: list[tuple[Path, str, dict[str, Any]]] = []
        for version in ["A", "B"]:
            selected_cards = cards
            strategy = (
                "semantic_selection_locked_evidence_fields"
                if semantic
                else "locked_evidence_fields"
            )
            if config.use_llm and not semantic:
                try:
                    chosen = _llm_select_cards(
                        config,
                        report_text=report_text,
                        cards=cards,
                        profile=profile,
                        target=target,
                        version=version,
                    )
                    if chosen is None:
                        raise ValueError("llm_selection_invalid")
                    selected_cards = chosen
                    strategy = "llm_selection_locked_evidence_fields"
                except (ValueError, OSError, RuntimeError):
                    if config.require_llm:
                        print("[generation] LLM 未返回可验证的证据选择，已阻断生成。")
                        return 1
                    strategy = "rule_fallback_locked_evidence_fields"
            claims: list[dict[str, Any]] = []
            content = resume_renderer.build_template_resume(
                version,
                report_id,
                score_total,
                now,
                selected_cards,
                personal_profile=profile,
                job_context=target,
                positioning=config.resume_positioning,
                custom_positioning=config.custom_positioning,
                claims=claims,
                preferred_facts=resume_renderer.semantic_preferred_facts(semantic)
                if semantic
                else None,
                semantic_report=semantic,
            )
            paths: dict[str, Path] = {
                "personal_profile": config.personal_profile_path,
                "matching_report": report_path,
            }
            if semantic:
                paths["semantic_matching"] = report_path.with_suffix(".semantic.json")
            if config.job_profile_path:
                paths["job_profile"] = config.job_profile_path
            if target.get("jd_source_path"):
                paths["job_description"] = Path(str(target["jd_source_path"]))
            paths.update(
                {card["id"]: config.evidence_dir / f"{card['id']}.yaml"
                 for card in selected_cards}
            )
            for card in selected_cards:
                paths.update(card.get("material_inputs", {}))
            trace = _build_trace(
                version=version,
                content=content,
                strategy=strategy,
                semantic=semantic,
                profile=profile,
                target=target,
                selected_cards=selected_cards,
                claims=claims,
                paths=paths,
                missing_profile=missing_profile,
                missing_target=missing_target,
            )
            artifacts.append((output_dir / f"resume_{report_id}_{version}.md", content, trace))
        # 两版都通过校验后才发布产物，避免 LLM 中途失败留下看似完整的单版结果。
        for output_path, content, trace in artifacts:
            _ = output_path.write_text(content, encoding="utf-8")
            _ = output_path.with_suffix(".trace.json").write_text(
                json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except (ValueError, OSError):
        print("[generation] 生成输入缺失、不合格或包含内部追溯信息，请检查选定资料。")
        return 1
    return 0
