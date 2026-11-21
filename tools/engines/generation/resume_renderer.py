"""已核定来源加载与唯一事实计划生成；正文与 occurrence trace 同源。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.infra import evidence_provenance as provenance
from tools.infra.evidence_fact_scope import personal_claim_exclusions
from tools.infra.evidence_pool import pool_eligible_scalars
from tools.infra.evidence_sources import assert_captured_source, validated_source_inputs
from tools.infra.persistence.yaml_io import parse_simple_yaml

CardView = dict[str, Any]


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_prompt(template_path: str, report_text: str, evidence_text: str, version: str) -> str:
    template = read_text(template_path)
    return template.replace("<MATCHING_REPORT>", report_text).replace("<EVIDENCE_CARDS>", evidence_text).replace("{{A|B}}", version)


def extract_top_card_ids(report_text: str) -> list[str]:
    top_ids = re.findall(r'^\s*-\s*id:\s*"?([^"\n]+)"?\s*$', report_text, re.MULTILINE)
    if top_ids:
        return top_ids[:3]
    return list(dict.fromkeys(re.findall(r'^\s*-\s*"?(ec-[^"\n]+)"?\s*$', report_text, re.MULTILINE)))[:3]


def _card_view(file_path: Path, raw: bytes, doc: dict, material_root: Path) -> CardView:
    scalars, values = doc["scalars"], doc["lists"]
    material_inputs = validated_source_inputs(doc, material_root)
    exclusions = personal_claim_exclusions(doc, material_root, card_id=file_path.stem, validated_sources=material_inputs)
    if scalars.get("id") and scalars["id"] != file_path.stem:
        raise ValueError("selected_evidence_identity_mismatch")
    role_scope = scalars.get("role_scope", "").strip()
    if role_scope.casefold() in {"[]", "{}", "null", "none"}:
        role_scope = ""
    return {
        "id": file_path.stem,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "material_inputs": material_inputs,
        "personal_claim_exclusions": exclusions,
        "title": scalars.get("title", file_path.stem),
        "raw_source": scalars.get("raw_source", ""),
        "time_range": scalars.get("time_range", ""),
        "context": scalars.get("context", ""),
        "role_scope": role_scope,
        **{field: values.get(field, []) for field in ("actions", "results", "stack", "artifacts")},
        **{field + "_provenance": provenance.field_provenance(scalars, field) for field in ("time_range", "role_scope")},
        **{field + "_level": provenance.field_level(scalars, field) for field in ("time_range", "role_scope")},
        "project_key": str(scalars.get("project_key") or ""),
        "card_category": str(scalars.get("card_category") or "project"),
    }


def load_cards(evidence_dir: Path, card_ids: list[str], material_dir: Path | None = None,
               *, require_saved_eligible: bool = False) -> list[CardView]:
    from tools.infra.evidence_pool import is_saved_eligible_evidence

    material_root = material_dir if material_dir is not None else evidence_dir.parent / "materials"
    if (not card_ids or len(set(card_ids)) != len(card_ids)
            or any(not isinstance(card_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", card_id) for card_id in card_ids)):
        raise ValueError("selected_evidence_missing_or_invalid")
    cards = []
    for card_id in card_ids:
        path = evidence_dir / f"{card_id}.yaml"
        if not path.is_file() or path.is_symlink():
            raise ValueError("selected_evidence_missing_or_invalid")
        raw = path.read_bytes()
        doc = parse_simple_yaml(raw.decode("utf-8"))
        if (not pool_eligible_scalars(doc["scalars"], card_id=card_id)
                or (require_saved_eligible and not is_saved_eligible_evidence(doc))
                or not doc["lists"].get("results") or not doc["lists"].get("artifacts")
                or not doc["scalars"].get("title")):
            raise ValueError("selected_evidence_ineligible")
        cards.append(_card_view(path, raw, doc, material_root))
    return cards


def load_all_cards(evidence_dir: Path, material_dir: Path | None = None) -> list[CardView]:
    """加载现行入池卡；来源无效必须失败，不能降级为未核定正文。"""
    material_root = material_dir if material_dir is not None else evidence_dir.parent / "materials"
    cards = []
    for path in sorted(evidence_dir.glob("*.yaml")):
        try:
            raw = path.read_bytes()
            doc = parse_simple_yaml(raw.decode("utf-8"))
        except (ValueError, OSError):
            continue
        if (not pool_eligible_scalars(doc["scalars"], card_id=path.stem)
                or not doc["lists"].get("results") or not doc["lists"].get("artifacts")
                or not doc["scalars"].get("title")):
            continue
        if path.is_symlink():
            raise ValueError("generation_input_changed")
        try:
            cards.append(_card_view(path, raw, doc, material_root))
        except ValueError as exc:
            raise ValueError(f"{path.stem}:{exc}") from exc
    return cards


def unique_stack(cards: list[CardView], limit: int = 8) -> list[str]:
    return list(dict.fromkeys(value for card in cards for value in card.get("stack", [])))[:limit]


def build_template_resume(version: str, cards: list[CardView], *,
                          personal_profile: dict[str, Any] | None = None,
                          job_context: dict[str, Any] | None = None,
                          positioning: str = "technical_depth", custom_positioning: str = "",
                          claims: list[dict[str, Any]] | None = None,
                          semantic_report: dict[str, Any] | None = None) -> str:
    """唯一选材/计划/排版组合；不改写字段，也不把卡级引用伪装为事实引用。"""
    from dataclasses import replace
    from tools.engines.generation.fact_index import build_fact_index
    from tools.engines.generation.fact_selector import VARIANTS, SelectionBudget, select_facts
    from tools.engines.generation.resume_plan import build_resume_plan
    from tools.engines.generation.plan_renderer import render_plan

    profile, target = personal_profile or {}, job_context or {}
    career = dict(profile.get("career") or {})
    plan_cards, periods = [], {}
    for card in cards:
        if str(card.get("card_category") or "project") == "activity":
            continue
        raw_period = str(card.get("time_range") or "").strip()
        time_source = card.get("time_range_provenance") or {}
        time_level = card.get("time_range_level") or time_source.get("level") or ("L1" if raw_period else "L5")
        if (time_level == "L5" or provenance.period_bounds(raw_period)[0] is None
                or (time_level in {"L2", "L3"} and
                    (time_source.get("confirmed_by_user") is not True or not time_source.get("evidence")))):
            continue
        periods[card["id"]] = provenance.format_presented_period(
            raw_period, level=time_level, precision=str(time_source.get("precision") or "month"))
        role_source = card.get("role_scope_provenance") or {}
        role_level = card.get("role_scope_level") or role_source.get("level") or ("L1" if card.get("role_scope") else "L5")
        hidden_role = role_level in {"L2", "L5"} or (
            role_level == "L3" and (role_source.get("confirmed_by_user") is not True or not role_source.get("evidence")))
        plan_cards.append({**card, "role_scope": ""} if hidden_role else card)
    groups = {str(card["id"]): str(card["project_key"]) for card in plan_cards if card.get("project_key")}
    index = build_fact_index(plan_cards, career, semantic_report,
                             preferred_card_ids=(semantic_report or {}).get("selected_card_ids") or ())
    # Fact.text keeps original source values. Only the existing display-period context changes.
    facts = tuple(replace(fact, time_range=periods[fact.source_id])
                  if fact.kind == "evidence" else fact for fact in index.facts)
    index = replace(index, facts=facts, by_id={fact.fact_id: fact for fact in facts})
    selection = select_facts(index, weights=VARIANTS.get(version, VARIANTS["A"]),
                             budget=SelectionBudget(), project_groups=groups)
    plan = build_resume_plan(index, selection, career, job_context=target,
                             variant=version, project_groups=groups)
    if not plan.projects and not plan.work:
        raise ValueError("no_presentable_resume_facts")
    return render_plan(plan, index, profile=profile, job_context=target, claims=claims,
                       version=version, positioning=positioning, custom_positioning=custom_positioning)


def load_generation_context(profile_path: Path, job_path: Path | None, *,
                            captured_inputs: dict[str, str] | None = None) -> tuple[dict, dict]:
    """解析实际消费的字节并捕获版本；发布时不得给旧正文补上新版本指纹。"""
    from tools.infra.career_profile import inspect_career
    from tools.infra.job_context import load_jd_source

    captures = captured_inputs if captured_inputs is not None else {}
    raw_profile = profile_path.read_bytes()
    fields = dict(parse_simple_yaml(raw_profile.decode("utf-8"))["scalars"])
    captures["personal_profile"] = hashlib.sha256(raw_profile).hexdigest()
    evidence_dir = profile_path.parent / "evidence_cards"
    if not evidence_dir.is_dir():
        evidence_dir = Path("evidence_cards")
    profile = {**fields, **inspect_career(fields, evidence_dir)}
    profile["current_position"] = profile.get("current_position") or profile.get("current_title", "")
    target = {}
    if job_path is not None:
        raw_job = job_path.read_bytes()
        doc = parse_simple_yaml(raw_job.decode("utf-8"))
        target = {**doc["scalars"], **doc["lists"]}
        captures["job_profile"] = hashlib.sha256(raw_job).hexdigest()
    target["target_role"] = target.get("target_role") or target.get("title", "")
    target["jd_text"], jd_path = load_jd_source(str(target.get("source_jd", "")), job_path)
    if jd_path:
        raw_jd = jd_path.read_bytes()
        target["jd_text"] = raw_jd.decode("utf-8")
        target["jd_source_path"] = str(jd_path.resolve())
        captures["job_description"] = hashlib.sha256(raw_jd).hexdigest()
    return profile, target


def build_generation_trace(
    *,
    version: str,
    content: str,
    strategy: str,
    semantic: dict[str, Any] | None,
    profile: dict[str, Any],
    target: dict[str, Any],
    selected_cards: list[CardView],
    claims: list[dict[str, Any]],
    paths: dict[str, Path],
    captured_inputs: dict[str, str],
    missing_profile: list[str],
    missing_target: list[str],
) -> dict[str, Any]:
    paths = dict(paths)
    expected = dict(captured_inputs)
    missing_evidence = [
        f"{card['id']}.{field}"
        for card in selected_cards
        for field in ("context", "time_range", "actions")
        if not card[field]
    ]
    # 本人职责属于表达完整性问题：批量提炼卡从技术文档抽取，常没有角色措辞。
    # 缺失时记录提示，但不作为内容完整性硬阻断（事实仍在卡内，正文只是不显示角色行）。
    missing_soft_evidence = [
        f"{card['id']}.role_scope" for card in selected_cards if not card["role_scope"]
    ]
    if not unique_stack(selected_cards):
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
    if not unique_stack(selected_cards):
        evidence_reasons.append("缺少已审核的技能依据")
    from tools.infra.career_profile import career_generation_issues

    career_reasons = career_generation_issues(profile, selected_cards)
    # 职业档案引用的证据卡目录同样不能只看 profile 同级：profile 可能在临时
    # 目录，此时应回退到工作区 evidence_cards，否则 trace 的 inputs 全部不存在。
    profile_evidence_dir = Path(str(paths["personal_profile"])).parent / "evidence_cards"
    if not profile_evidence_dir.is_dir():
        profile_evidence_dir = Path("evidence_cards")
    for ref in profile.get("evidence_hashes", {}):
        paths["career_evidence:" + ref] = profile_evidence_dir / f"{ref}.yaml"
        expected["career_evidence:" + ref] = profile["evidence_hashes"][ref]
    for card in selected_cards:
        expected[card["id"]] = card["source_sha256"]
        for key, (source, digest) in getattr(card.get("material_inputs"), "snapshots", {}).items():
            if paths.get(key) != source:
                raise ValueError("material_source_changed")
            expected[key] = digest
    trace_inputs = {}
    for key, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError("generation_input_changed")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if not expected.get(key) or digest != expected[key]:
            raise ValueError("generation_input_changed")
        trace_inputs[key] = {"path": str(path.resolve()), "exists": True, "sha256": digest}
    for card in selected_cards:
        for key, source in card.get("material_inputs", {}).items():
            if trace_inputs[key]["path"] != str(source.resolve()):
                raise ValueError("material_source_changed")
            assert_captured_source(card["material_inputs"], key, trace_inputs[key]["sha256"])
    return {
        "schema_version": 1,
        "version": version,
        "content_schema_version": 1,
        "occurrence_lineage_version": 1,
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
        "inputs": trace_inputs,
        "target": target,
        "readiness": {
            "status": "NEEDS_EVIDENCE"
            if missing_profile or missing_target or missing_evidence or career_reasons
            else "NEEDS_REVIEW",
            "deliverable": False,
            "missing_profile_fields": missing_profile,
            "missing_target_fields": missing_target,
            "missing_evidence_fields": missing_evidence,
            "missing_soft_fields": missing_soft_evidence,
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