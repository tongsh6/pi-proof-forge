#!/usr/bin/env python3
import argparse
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import sys
from typing import Any, NotRequired, TypedDict, cast

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.engines.generation import template_assembler
from tools.infra import evidence_provenance as provenance
from tools.infra.llm.client import (
    LLMClient,
    default_base_url,
    llm_request_available,
    llm_timeout_from_env,
)
from tools.infra.persistence.yaml_io import parse_simple_yaml


DEFAULT_BASE_URL = "https://api.openai.com/v1"


class ParsedDoc(TypedDict):
    scalars: dict[str, str]
    lists: dict[str, list[str]]


class CardView(TypedDict):
    id: str
    title: str
    raw_source: str
    time_range: str
    context: str
    role_scope: str
    actions: list[str]
    results: list[str]
    stack: list[str]
    artifacts: list[str]
    source_sha256: str
    time_range_provenance: NotRequired[dict[str, Any] | None]
    role_scope_provenance: NotRequired[dict[str, Any] | None]
    time_range_level: NotRequired[str]
    role_scope_level: NotRequired[str]


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_prompt(
    template_path: str, report_text: str, evidence_text: str, version: str
) -> str:
    template = read_text(template_path)
    content = template.replace("<MATCHING_REPORT>", report_text)
    content = content.replace("<EVIDENCE_CARDS>", evidence_text)
    return content.replace("{{A|B}}", version)


def extract_score_total(report_text: str) -> int:
    match = re.search(r"^score_total:\s*(\d+)", report_text, re.MULTILINE)
    if match:
        return int(match.group(1))
    return 0


def extract_top_card_ids(report_text: str) -> list[str]:
    top_ids = cast(
        list[str],
        re.findall(r"^\s*-\s*id:\s*\"?([^\"\n]+)\"?\s*$", report_text, re.MULTILINE),
    )
    if top_ids:
        return top_ids[:3]
    fallback_ids = cast(
        list[str],
        re.findall(r"^\s*-\s*\"?(ec-[^\"\n]+)\"?\s*$", report_text, re.MULTILINE),
    )
    unique: list[str] = []
    for card_id in fallback_ids:
        if card_id not in unique:
            unique.append(card_id)
    return unique[:3]


def load_cards(evidence_dir: Path, card_ids: list[str], material_dir: Path | None = None) -> list[CardView]:
    from tools.infra.evidence_sources import validated_source_inputs
    card_map: dict[str, CardView] = {}
    if not card_ids or any(not re.fullmatch(r"[A-Za-z0-9_-]+", card_id) for card_id in card_ids):
        raise ValueError("selected_evidence_missing_or_invalid")
    for card_id in card_ids:
        file_path = evidence_dir / f"{card_id}.yaml"
        if not file_path.is_file():
            raise ValueError("selected_evidence_missing_or_invalid")
        doc = parse_simple_yaml(read_text(str(file_path)))
        if not doc["lists"].get("results") or not doc["lists"].get("artifacts") or not doc["scalars"].get("title"):
            raise ValueError("selected_evidence_ineligible")
        role_scope = doc["scalars"].get("role_scope", "").strip()
        if role_scope.casefold() in {"[]", "{}", "null", "none"}:
            role_scope = ""
        card_map[card_id] = {
            "material_inputs": validated_source_inputs(doc, material_dir if material_dir is not None else evidence_dir.parent/'materials'),
            "id": card_id,
            "source_sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
            "title": doc["scalars"].get("title", card_id),
            "raw_source": doc["scalars"].get("raw_source", ""),
            "time_range": doc["scalars"].get("time_range", ""),
            "context": doc["scalars"].get("context", ""),
            "role_scope": role_scope,
            "actions": doc["lists"].get("actions", []),
            "results": doc["lists"].get("results", []),
            "stack": doc["lists"].get("stack", []),
            "artifacts": doc["lists"].get("artifacts", []),
            "time_range_provenance": provenance.field_provenance(doc["scalars"], "time_range"),
            "role_scope_provenance": provenance.field_provenance(doc["scalars"], "role_scope"),
            "time_range_level": provenance.field_level(doc["scalars"], "time_range"),
            "role_scope_level": provenance.field_level(doc["scalars"], "role_scope"),
        }

    cards: list[CardView] = []
    for card_id in card_ids:
        if card_id in card_map:
            cards.append(card_map[card_id])
    return cards


def unique_stack(cards: list[CardView], limit: int = 8) -> list[str]:
    values: list[str] = []
    for card in cards:
        for item in card["stack"]:
            if item not in values:
                values.append(item)
            if len(values) >= limit:
                return values
    return values


def pick_action(card: CardView, version: str) -> str:
    if not card["actions"]:
        return ""
    if version == "A":
        preferred = ["架构", "重构", "链路", "一致性", "性能", "稳定性", "扩展"]
    else:
        preferred = ["推进", "治理", "协作", "交付", "灰度", "回滚", "owner", "负责人"]
    for action in card["actions"]:
        lower = action.lower()
        if any(token.lower() in lower for token in preferred):
            return action
    return card["actions"][0]


def semantic_preferred_facts(review: dict[str, Any]) -> list[dict[str, Any]]:
    """保留子项支持及父要求归属，供正文取舍使用，不改变评估结论。"""
    result = []
    for parent in review['assessments']:
        for row in parent.get('checks', [parent]):
            weight = {'supported': 2, 'partial': 1}.get(row['status'], 0)
            if weight:
                result.extend({**review['facts'][c['fact_id']], 'requirement_id': parent['requirement_id'],
                               'support_weight': weight} for c in row['citations'])
    return result


def prioritize_project_facts(values: list[str], card_id: str, field: str,
                             preferred_facts: list[dict[str, Any]],
                             covered_requirements: dict[str, int] | None = None) -> list[str]:
    """在既有稳定顺序上优先增加要求覆盖，同一父项的重复引用只计一次。"""
    coverage: dict[str, dict[str, int]] = {}
    for ref in preferred_facts:
        if ref['source_id'] != card_id or ref['field'] != field:
            continue
        weights = coverage.setdefault(ref['text'], {})
        parent = ref.get('requirement_id', '')
        weights[parent] = max(weights.get(parent, 0), ref.get('support_weight', 1))
    remaining = list(dict.fromkeys(values))
    ranked: list[str] = []
    covered: dict[str, int] = dict(covered_requirements or {})
    while remaining:
        def priority(value):
            weights = coverage.get(value, {})
            return (sum(max(0, weight - covered.get(parent, 0)) for parent, weight in weights.items()
                        if parent in {'d1', 'd2', 'd3'}),
                    int(field == 'results' and bool(re.search(r'\d', value))
                        and bool(re.search(r'→|降低|降至|提升|缩短|减少|从.+(?:到|至)|由.+(?:到|至)', value))),
                    sum(max(0, weight - covered.get(parent, 0)) for parent, weight in weights.items()),
                    sum(weights.values()))
        value = max(remaining, key=priority)
        ranked.append(value)
        remaining.remove(value)
        for parent, weight in coverage.get(value, {}).items():
            covered[parent] = max(covered.get(parent, 0), weight)
    return ranked


def build_template_resume(
    version: str, report_id: str, score_total: int, now: str, cards: list[CardView],
    *, personal_profile: dict[str, Any] | None = None,
    job_context: dict[str, Any] | None = None,
    positioning: str = "technical_depth", custom_positioning: str = "",
    claims: list[dict[str, Any]] | None = None,
    preferred_facts: list[dict[str, Any]] | None = None,
    semantic_report: dict[str, Any] | None = None,
) -> str:
    profile = personal_profile or {}
    target = job_context or {}
    claims = claims if claims is not None else []
    targeted=preferred_facts is not None
    preferred_profile={f['field'] for f in (preferred_facts or []) if f['source_id']=='personal_profile'}

    def fact(text: str, kind: str, field: str, evidence_id: str = "", field_provenance: dict[str, Any] | None = None) -> str:
        text = " ".join(str(text).split())
        if re.search(r"Evidence trace|Source report|(?:/Users/|/private/|/tmp/)|\bec[-_][\w-]+", text, re.I):
            raise ValueError("internal_metadata_in_resume_fact")
        if text:
            claim: dict[str, Any] = {"text": text, "source_kind": kind, "field": field, "evidence_id": evidence_id}
            if field_provenance:
                claim["provenance"] = field_provenance
            claims.append(claim)
        return text

    name = fact(profile.get("name", ""), "personal_profile", "name")
    lines = [f"# {name or '个人简历'}"]
    contact = [fact(profile.get(key, ""), "personal_profile", key) for key in ("phone", "email", "city")]
    lines.append(" | ".join(value for value in contact if value))
    if profile.get("current_position"):
        lines.append("当前定位：" + fact(profile["current_position"], "personal_profile", "current_position"))
    role = custom_positioning if positioning == "custom" and custom_positioning else target.get("target_role", "")
    if role:
        company = fact(target.get("company", ""), "job_profile", "company")
        lines.append("求职意向：" + " · ".join(value for value in (
            company, fact(role, "positioning" if positioning == "custom" else "job_profile", "target_role")
        ) if value))
    career = profile.get('career') or {}
    work = sorted(career.get('work', []), key=lambda item: item.get('start',''), reverse=True)
    def personal(value, field):return fact(value,'personal_profile',field)
    def career_period(item, group):
        first=personal(item.get('start',''),f"career.{group}.{item['id']}.start")
        last='至今' if item.get('current') else personal(item.get('end',''),f"career.{group}.{item['id']}.end")
        return ' ~ '.join(v for v in (first,last) if v)
    summary=career.get('summary','')
    if targeted and work and work[0].get('scope'):
        current=work[0];base=f"career.work.{current['id']}"
        lines.extend(['','## 职业概述',personal(current['scope'],base+'.scope')])
        if current.get('contributions'):
            value=current['contributions'][0]
            lines.append(personal(value,base+'.contributions'))
    elif summary:
        lines.extend(['','## 职业概述',personal(summary,'career.summary')])
    elif work and work[0].get('scope'):
        lines.extend(['','## 职业概述',personal(profile.get('current_position',''),'current_position')+'。'+personal(work[0]['scope'],f"career.work.{work[0]['id']}.scope")])
    groups=[item for item in career.get('skills',[]) if item.get('category') and item.get('description')]
    skills_start = len(lines)
    if targeted:
        selected_ids={c['id'] for c in cards}
        groups.sort(key=lambda g:(not any(field.startswith(f"career.skills.{g['id']}.") for field in preferred_profile),not bool(selected_ids.intersection(g.get('evidence_ids',[])))))
        groups=groups[:3]
    if groups:
        lines.extend(['','## 核心能力'])
        for item in groups:
            lines.append('- '+personal(item['category'],f"career.skills.{item['id']}.category")+'：'+personal(item['description'],f"career.skills.{item['id']}.description"))
    # 首屏切分标记：优先放在第一条经历之后，使 JD 前三条职责对应的经历 bullet 进入首屏；
    # 没有可用经历时退回摘要/能力区结尾。渲染层忽略该注释行。
    first_screen_fallback = len(lines)
    visible_cards = [card for card in cards if template_assembler.visible_in_resume(card)]
    render_cards = template_assembler.first_screen_priority(
        template_assembler.order_cards_for_resume(visible_cards, semantic_report)
    )
    stacks = unique_stack(visible_cards,limit=sum(len(c['stack']) for c in visible_cards)) if targeted else unique_stack(visible_cards)
    keywords = [str(term).casefold() for term in target.get("keywords", [])]
    stacks.sort(key=lambda value: value.casefold() not in keywords)
    if targeted:
        cited_stack={f['text'] for f in preferred_facts if f['field']=='stack' and f['source_id'] in {c['id'] for c in cards}}
        stacks.sort(key=lambda value:value not in cited_stack)
        stacks=stacks[:max(8,len(cited_stack))]
    if stacks and (targeted or not groups):
        lines.extend(["", "## 核心技能", "、".join(stacks)])
        for skill in stacks:
            sources=[card for card in cards if skill in card['stack']]
            for source in (sources if targeted else sources[:1]):fact(skill, "evidence", "stack", source["id"])
    deferred_skills = lines[skills_start:] if targeted else []
    if targeted:
        del lines[skills_start:]
        first_screen_fallback = len(lines)
    visible_work=[item for item in work if item.get('company') and item.get('title')]
    work_start=len(lines)
    if visible_work:
        lines.extend(['','## 工作经历'])
        for item in visible_work:
            base=f"career.work.{item['id']}"
            if targeted:
                lines.append('### '+personal(item['company'],base+'.company')+' · '+personal(item['title'],base+'.title')+'（'+career_period(item,'work')+'）')
                for contribution in item.get('contributions',[]):
                    if any(f['source_id']=='personal_profile' and f['field']==base+'.contributions' and f['text']==contribution for f in (preferred_facts or [])) and not any(c['text']==contribution for c in claims):
                        # 工作经历没有可核验的成果段，职责以非 bullet 行呈现，避免把职责伪装成成果。
                        lines.append('职责：'+personal(contribution,base+'.contributions'))
                continue
            lines.append('### '+personal(item['company'],base+'.company')+'（'+career_period(item,'work')+'）')
            lines.append('角色：'+' · '.join(v for v in (personal(item.get('department',''),base+'.department'),personal(item['title'],base+'.title')) if v))
            if item.get('scope'):lines.append('场景：'+personal(item['scope'],base+'.scope'))
            for contribution in item.get('contributions',[]):lines.append('职责：'+personal(contribution,base+'.contributions'))
    deferred_work=lines[work_start:] if targeted else []
    if targeted:del lines[work_start:]
    lines.extend(["", "## 项目经历"])
    marker_done = False
    for card in render_cards:
        time_level = template_assembler.level_of(card, "time_range")
        role_level = template_assembler.level_of(card, "role_scope")
        title = fact(card["title"], "evidence", "title", card["id"])
        period_text = template_assembler.format_time(
            card["time_range"], time_level, template_assembler.precision_of(card)
        )
        period = fact(period_text, "evidence", "time_range", card["id"],
                      card.get("time_range_provenance")) if period_text else ""
        lines.append(f"### {title}" + (f"（{period}）" if period else ""))
        role_value = template_assembler.role_text(card["role_scope"], role_level)
        if role_value:
            lines.append("角色：" + fact(role_value, "evidence", "role_scope", card["id"],
                                         card.get("role_scope_provenance")))
        if card["context"]:
            lines.append("场景：" + fact(card["context"], "evidence", "context", card["id"]))
        linked=[item for item in work if card['id'] in item.get('evidence_ids',[]) and item.get('company')]
        if linked:lines.append('所属工作：'+'、'.join(personal(item['company'],f"career.work.{item['id']}.company") for item in linked))
        action_version = "B" if version == "B" or positioning == "delivery_owner" else "A"
        actions = list(dict.fromkeys(card["actions"]))
        preferred = pick_action(card, action_version)
        actions.sort(key=lambda value: (-sum(term in value.casefold() for term in keywords if term), value != preferred))
        if targeted:
            actions = prioritize_project_facts(actions, card['id'], 'actions', preferred_facts)
        results = list(card['results'])
        if targeted:
            results = prioritize_project_facts(results, card['id'], 'results', preferred_facts)
        pairs, unpaired_actions, unpaired_results = template_assembler.pair_actions_results(
            actions, results, max_bullets=3, max_results_per_bullet=2,
        )
        if pairs:
            def clean_fact_value(value: str) -> str:
                return re.sub(r"[。；;，,\s]+$", "", " ".join(str(value).split()))
            for action, result_values in pairs:
                action_text = fact(
                    clean_fact_value(template_assembler.downgrade_wording(action, role_level)),
                    "evidence", "actions", card["id"],
                )
                result_texts = [
                    fact(clean_fact_value(template_assembler.downgrade_wording(value, role_level)),
                         "evidence", "results", card["id"])
                    for value in result_values
                ]
                combined = template_assembler.paired_bullet_text(action_text, result_texts)
                if targeted and combined in ' '.join(card['context'].split()):
                    continue
                lines.append("- " + combined)
        else:
            # 无可核对关联时不把行动/成果硬拼成成就 bullet；以非 bullet 事实行保留原文，
            # 避免 R3.1 被无结果支撑的成就条目拉低，同时让关联缺口继续显式暴露。
            for action in list(unpaired_actions)[:3]:
                lines.append("职责：" + fact(template_assembler.downgrade_wording(action, role_level),
                                             "evidence", "actions", card["id"]))
            for result in list(unpaired_results)[:2]:
                rendered = fact(template_assembler.downgrade_wording(result, role_level),
                                "evidence", "results", card["id"])
                if targeted and rendered in ' '.join(card['context'].split()):
                    continue
                lines.append("结果：" + rendered)
        lines.append("")
        if not marker_done:
            lines.extend(["", FIRST_SCREEN_MARKER, ""])
            marker_done = True
    if not marker_done:
        lines[first_screen_fallback:first_screen_fallback] = ["", FIRST_SCREEN_MARKER, ""]
    project_end = len(lines)
    lines.extend(deferred_work)
    lines.extend(deferred_skills)
    education=[item for item in career.get('education',[]) if item.get('school') and item.get('degree')]
    if career.get('education_visibility')=='show' and education:
        lines.extend(['','## 教育经历'])
        for item in education:
            base=f"career.education.{item['id']}"
            if targeted:
                lines.append(' · '.join(personal(item[key],base+'.'+key) for key in ('school','major','degree') if item.get(key))+'（'+career_period(item,'education')+'）')
                continue
            lines.append('### '+personal(item['school'],base+'.school')+'（'+career_period(item,'education')+'）')
            lines.append(' · '.join(v for v in (personal(item.get('major',''),base+'.major'),personal(item['degree'],base+'.degree')) if v))
    extras=[item for item in career.get('extras',[]) if item.get('title') and item.get('description')]
    if targeted:
        extras = [item for item in extras if any(field.startswith(f"career.extras.{item['id']}.") for field in preferred_profile)]
        extra_refs = [{**ref, 'field': 'extras', 'text': item['id']}
                      for item in extras for ref in preferred_facts
                      if ref['source_id'] == 'personal_profile' and ref['field'].startswith(f"career.extras.{item['id']}.")]
        body_coverage: dict[str, int] = {}
        def _same_fact_text(left: str, right: str) -> bool:
            normalize = lambda value: re.sub(r"[。；;，,\s]+$", "", " ".join(str(value).split()))
            return normalize(left) == normalize(right)
        for ref in preferred_facts:
            if any(_same_fact_text(claim['text'], ref['text']) and claim['field'] == ref['field']
                   and (claim.get('evidence_id') or 'personal_profile') == ref['source_id'] for claim in claims):
                parent = ref.get('requirement_id', '')
                body_coverage[parent] = max(body_coverage.get(parent, 0), ref.get('support_weight', 1))
        order = prioritize_project_facts([item['id'] for item in extras], 'personal_profile', 'extras',
                                        extra_refs, covered_requirements=body_coverage)
        extras.sort(key=lambda item: order.index(item['id']))
        extras = extras[:2]
    extras_start=len(lines)
    if extras:
        lines.extend(['','## 补充成果'])
        for item in extras:
            base=f"career.extras.{item['id']}"
            lines.append('- '+personal(item['title'],base+'.title')+'：'+personal(item['description'],base+'.description'))
            if item.get('url'):lines.append(personal(item['url'],base+'.url'))
    if targeted and extras:
        extras_lines = lines[extras_start:]
        del lines[extras_start:]
        lines[project_end:project_end] = extras_lines
    return "\n".join(lines).rstrip() + "\n"


def load_generation_context(profile_path: Path, job_path: Path | None) -> tuple[dict[str, str], dict[str, Any]]:
    from tools.infra.career_profile import load_career_profile
    profile = load_career_profile(profile_path)
    profile["current_position"] = profile.get("current_position") or profile.get("current_title", "")
    doc = parse_simple_yaml(job_path.read_text(encoding="utf-8")) if job_path and job_path.is_file() else {"scalars": {}, "lists": {}}
    target: dict[str, Any] = {**doc["scalars"], **doc["lists"]}
    target["target_role"] = target.get("target_role") or target.get("title", "")
    from tools.infra.job_context import load_jd_source
    target["jd_text"], jd_path = load_jd_source(str(target.get("source_jd", "")), job_path)
    if jd_path:
        target["jd_source_path"] = str(jd_path.resolve())
    return profile, target


from tools.infra.career_profile import career_generation_issues


def _legacy_main() -> int:
    parser = argparse.ArgumentParser(description="Run resume generation workflow")
    _ = parser.add_argument(
        "--matching-report", required=True, help="Matching report path"
    )
    _ = parser.add_argument("--output-dir", required=True, help="Output directory")
    _ = parser.add_argument("--personal-profile", default="personal_profile.yaml", help="个人资料 YAML")
    _ = parser.add_argument("--job-profile", default="", help="目标岗位 YAML")
    _ = parser.add_argument("--resume-positioning", default="technical_depth", choices=("technical_depth", "delivery_owner", "custom"))
    _ = parser.add_argument("--custom-positioning", default="", help="自定义求职方向")
    _ = parser.add_argument(
        "--use-llm", action="store_true", help="Use LLM for generation"
    )
    _ = parser.add_argument(
        "--require-llm", action="store_true", help="Fail if LLM path is unavailable"
    )
    _ = parser.add_argument(
        "--prompt", default="tools/prompts/generation.md", help="Prompt template path"
    )
    _ = parser.add_argument(
        "--evidence-dir", default="evidence_cards", help="Evidence cards directory"
    )
    _ = parser.add_argument(
        "--model", default=os.getenv("LLM_MODEL", ""), help="Model name"
    )
    _ = parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", "") or default_base_url(fallback=DEFAULT_BASE_URL),
        help="OpenAI-compatible base URL",
    )
    _ = parser.add_argument(
        "--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key"
    )
    args = parser.parse_args()

    report_path = cast(str, args.matching_report)
    output_dir_arg = cast(str, args.output_dir)
    prompt_path = cast(str, args.prompt)
    evidence_dir_arg = cast(str, args.evidence_dir)
    model = cast(str, args.model)
    base_url = cast(str, args.base_url)
    api_key = cast(str, args.api_key)
    use_llm = cast(bool, args.use_llm)
    require_llm = cast(bool, args.require_llm)

    if require_llm and not use_llm:
        print("--require-llm requires --use-llm")
        return 1

    report_id = Path(report_path).stem
    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    output_dir = Path(output_dir_arg)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        report_text = read_text(report_path)
        score_total = extract_score_total(report_text)
        evidence_dir = Path(evidence_dir_arg)
        profile_path = Path(args.personal_profile)
        cards = load_cards(evidence_dir, extract_top_card_ids(report_text), profile_path.parent/'materials')
        from tools.infra.semantic_matching import load_semantic_report
        semantic = load_semantic_report(Path(report_path))
        job_path = Path(args.job_profile) if args.job_profile else None
        if semantic and (not job_path or hashlib.sha256(job_path.read_bytes()).hexdigest() != semantic['inputs']['job_profile']['sha256']):
            raise ValueError('semantic_target_changed')
        if semantic:
            if any(card['source_sha256'] != semantic['inputs'][card['id']]['sha256'] for card in cards):
                raise ValueError('semantic_evidence_changed')
            expected_profile = semantic['inputs'].get('personal_profile')
            if expected_profile and (not profile_path.is_file() or hashlib.sha256(profile_path.read_bytes()).hexdigest() != expected_profile['sha256']):
                raise ValueError('semantic_personal_profile_changed')
        profile, target = load_generation_context(profile_path, job_path)
        missing_profile = [key for key in ("name", "phone", "email", "city", "current_position") if not profile.get(key, "").strip()]
        missing_target = [key for key in ("target_role", "company", "jd_text") if not target.get(key)]
        artifacts: list[tuple[Path, str, dict[str, Any]]] = []
        for version in ["A", "B"]:
            selected_cards = cards
            strategy = "semantic_selection_locked_evidence_fields" if semantic else "locked_evidence_fields"
            if use_llm and not semantic:
                try:
                    if not llm_request_available(
                        provider=os.getenv("LLM_PROVIDER", ""),
                        api_key=api_key,
                        model=model,
                    ):
                        raise ValueError("llm_configuration_missing")
                    evidence_text = json.dumps([
                        {key: card[key] for key in ("id", "title", "context", "actions", "results", "stack")}
                        for card in cards
                    ], ensure_ascii=False)
                    prompt = load_prompt(prompt_path, report_text, evidence_text, version)
                    prompt = prompt.replace("<PERSONAL_PROFILE>", json.dumps({
                        key: profile.get(key, "") for key in ("current_position", "city")
                    }, ensure_ascii=False))
                    prompt = prompt.replace("<JOB_CONTEXT>", json.dumps({
                        key: target.get(key, "") for key in (
                            "company", "target_role", "jd_text", "must_have", "keywords", "seniority_signal"
                        )
                    }, ensure_ascii=False))
                    prompt = prompt.replace("<POSITIONING>", str(args.custom_positioning or args.resume_positioning))
                    client = LLMClient(base_url=base_url, api_key=api_key, timeout=llm_timeout_from_env())
                    response = client.post_json(client.chat_completions_url, {
                        "model": model, "temperature": 0,
                        "messages": [{"role": "user", "content": prompt}],
                    })
                    selection = json.loads(client.extract_content(response))
                    ids = selection.get("evidence_ids") if isinstance(selection, dict) else None
                    by_id = {card["id"]: card for card in cards}
                    if (
                        not isinstance(ids, list) or not ids or set(selection) != {"evidence_ids"}
                        or not all(isinstance(item, str) and item in by_id for item in ids)
                        or len(set(ids)) != len(ids)
                    ):
                        raise ValueError("llm_selection_invalid")
                    selected_cards = [by_id[item] for item in ids]
                    strategy = "llm_selection_locked_evidence_fields"
                except (ValueError, OSError, RuntimeError):
                    if require_llm:
                        print("[generation] LLM 未返回可验证的证据选择，已阻断生成。")
                        return 1
                    strategy = "rule_fallback_locked_evidence_fields"
            claims: list[dict[str, Any]] = []
            content = build_template_resume(
                version, report_id, score_total, now, selected_cards,
                personal_profile=profile, job_context=target,
                positioning=args.resume_positioning, custom_positioning=args.custom_positioning,
                claims=claims,
                preferred_facts=semantic_preferred_facts(semantic) if semantic else None,
                semantic_report=semantic,
            )
            paths = {"personal_profile": profile_path, "matching_report": Path(report_path)}
            if semantic:
                paths['semantic_matching'] = Path(report_path).with_suffix('.semantic.json')
            if job_path:
                paths["job_profile"] = job_path
            if target.get("jd_source_path"):
                paths["job_description"] = Path(target["jd_source_path"])
            paths.update({card["id"]: evidence_dir / f"{card['id']}.yaml" for card in selected_cards})
            for card in selected_cards:paths.update(card.get('material_inputs',{}))
            missing_evidence = [f"{card['id']}.{field}" for card in selected_cards
                                for field in ("context", "role_scope", "time_range", "actions") if not card[field]]
            if not unique_stack(selected_cards):
                missing_evidence.append("skills")
            field_labels = {"context":"项目场景", "role_scope":"本人职责", "time_range":"经历时间", "actions":"具体行动"}
            evidence_reasons = [f"{card['title']}：待补" + "、".join(field_labels[f] for f in field_labels if not card[f])
                                for card in selected_cards if any(not card[f] for f in field_labels)]
            if not unique_stack(selected_cards):evidence_reasons.append("缺少已审核的技能依据")
            career_reasons=career_generation_issues(profile,selected_cards)
            for ref in profile.get('evidence_hashes',{}):paths['career_evidence:'+ref]=profile_path.parent/'evidence_cards'/f'{ref}.yaml'
            trace = {
                "schema_version": 1, "version": version,
                "content_schema_version": 1, "career_revision": profile.get("revision",""),
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
                "inputs": {key: {
                    "path": str(path.resolve()), "exists": path.is_file(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "",
                } for key, path in paths.items()},
                "target": target,
                "readiness": {
                    "status": "NEEDS_EVIDENCE" if missing_profile or missing_target or missing_evidence or career_reasons else "NEEDS_REVIEW",
                    "deliverable": False,
                    "missing_profile_fields": missing_profile,
                    "missing_target_fields": missing_target,
                    "missing_evidence_fields": missing_evidence,
                    "missing_career_fields": career_reasons,
                    "content_ready": not (missing_profile or missing_target or missing_evidence or career_reasons),
                    "reasons": (["个人资料或目标岗位信息不完整"] if missing_profile or missing_target else []) + evidence_reasons + career_reasons + ["需人工审核简历事实与岗位适用性"],
                },
            }
            artifacts.append((output_dir / f"resume_{report_id}_{version}.md", content, trace))
        # 两版都通过校验后才发布产物，避免 LLM 中途失败留下看似完整的单版结果。
        for output_path, content, trace in artifacts:
            output_path.write_text(content, encoding="utf-8")
            output_path.with_suffix(".trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    except (ValueError, OSError):
        print("[generation] 生成输入缺失、不合格或包含内部追溯信息，请检查选定资料。")
        return 1
    return 0


def main() -> int:
    if os.getenv("PPF_FORCE_LEGACY_MAIN") == "1":
        return _legacy_main()

    from tools.cli.commands.generate import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
