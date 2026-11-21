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
        base_url=config.base_url,
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


def _check_semantic_binding(*, semantic: dict[str, Any],
                            cards: list[resume_renderer.CardView],
                            captured_inputs: dict[str, str]) -> None:
    """匹配支持必须绑定生成实际消费的版本，不能只在第二次读取前检查路径。"""
    inputs = semantic["inputs"]
    if captured_inputs.get("job_profile") != inputs["job_profile"]["sha256"]:
        raise ValueError("semantic_target_changed")
    for local_key, semantic_key in (("personal_profile", "personal_profile"),
                                    ("job_description", "jd_source")):
        expected = inputs.get(semantic_key)
        if expected and captured_inputs.get(local_key) != expected["sha256"]:
            raise ValueError("semantic_personal_profile_changed" if local_key == "personal_profile"
                             else "semantic_target_changed")
    for card in cards:
        if card["source_sha256"] != inputs.get(card["id"], {}).get("sha256"):
            raise ValueError("semantic_evidence_changed")
        for key, (_, digest) in getattr(card.get("material_inputs"), "snapshots", {}).items():
            if digest != inputs.get(key, {}).get("sha256"):
                raise ValueError("semantic_input_changed")


def run_generation_flow(config: GenerationFlowConfig) -> int:
    """执行简历生成。返回进程退出码：0 成功、1 输入缺失/不合格/LLM 必需失败。"""
    if config.require_llm and not config.use_llm:
        print("--require-llm requires --use-llm")
        return 1

    report_path = config.matching_report_path
    report_id = report_path.stem
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        report_raw = report_path.read_bytes()
        report_text = report_raw.decode("utf-8")
        captured_inputs = {"matching_report": hashlib.sha256(report_raw).hexdigest()}
        cards = resume_renderer.load_cards(
            config.evidence_dir,
            resume_renderer.extract_top_card_ids(report_text),
            config.personal_profile_path.parent / "materials",
        )
        semantic = load_semantic_report(report_path)
        if semantic:
            semantic_raw = report_path.with_suffix(".semantic.json").read_bytes()
            if json.loads(semantic_raw) != semantic:
                raise ValueError("semantic_report_changed")
            captured_inputs["semantic_matching"] = hashlib.sha256(semantic_raw).hexdigest()
        profile, target = resume_renderer.load_generation_context(
            config.personal_profile_path, config.job_profile_path, captured_inputs=captured_inputs
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
        # 事实池：语义模式与规则模式都用全量入池卡，选材在事实级完成；
        # `cards`（匹配报告 top_cards）仅保留给显式 LLM 选卡路径。
        # 材料目录优先取 profile 同级；profile 不在仓库根时（--personal-profile
        # 指向别处）回退到证据目录同级，避免整批卡因材料目录不存在而无法校验。
        from tools.infra.material_paths import materials_dir_for
        material_dir = materials_dir_for(
            config.personal_profile_path, fallback=config.evidence_dir.parent / "materials"
        )
        all_cards = resume_renderer.load_all_cards(config.evidence_dir, material_dir)
        base_cards = all_cards if (semantic or not config.use_llm) else cards
        if semantic:
            _check_semantic_binding(semantic=semantic, cards=base_cards, captured_inputs=captured_inputs)
        if not base_cards:
            print("[generation] 没有可用的已入池证据卡，无法生成。")
            return 1
        for version in ["A", "B"]:
            selected_cards = base_cards
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
                version, selected_cards, personal_profile=profile, job_context=target,
                claims=claims, semantic_report=semantic, positioning=config.resume_positioning,
                custom_positioning=config.custom_positioning,
            )
            used_card_ids = {claim["evidence_id"] for claim in claims
                             if claim.get("source_kind") == "evidence"}
            selected_cards = [card for card in selected_cards if card["id"] in used_card_ids]
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
            trace = resume_renderer.build_generation_trace(
                version=version,
                content=content,
                strategy=strategy,
                semantic=semantic,
                profile=profile,
                target=target,
                selected_cards=selected_cards,
                claims=claims,
                paths=paths,
                captured_inputs=captured_inputs,
                missing_profile=missing_profile,
                missing_target=missing_target,
            )
            artifacts.append((output_dir / f"resume_{report_id}_{version}.md", content, trace))
        # 两版都通过校验后才发布产物，避免 LLM 中途失败留下看似完整的单版结果。
        from tools.infra.persistence.review_snapshot import validate_generation_trace
        if semantic:
            from tools.engines.matching.semantic_matching import validate_inputs
            validate_inputs(semantic["inputs"])
        if not all(validate_generation_trace(content, trace) for _, content, trace in artifacts):
            raise ValueError("generation_input_changed")
        for output_path, content, trace in artifacts:
            _ = output_path.write_text(content, encoding="utf-8")
            _ = output_path.with_suffix(".trace.json").write_text(
                json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except (ValueError, OSError) as exc:
        # 失败必须可诊断：只打一句笼统提示会让"哪份资料不合格"无从查起。
        print(f"[generation] 生成输入缺失、不合格或包含内部追溯信息：{exc}")
        return 1
    return 0