"""Pure extraction of internally previewable, currently cited work facts."""
from __future__ import annotations

from tools.engines.generation.fact_index import Fact, FactIndex
from tools.engines.generation.fact_quality import judge_fact_text
from tools.engines.generation.resume_plan import ResumePlan, ProjectBlock
from tools.engines.generation.plan_renderer import render_plan
from tools.domain.assessment_support import positive_citations
from tools.domain.value_objects import FIRST_SCREEN_MARKER


def build_targeted_excerpt(*, assessments, requirements, audit_facts, current_facts, target,
                           personal_claim_exclusions=frozenset(), result_reviews=None):
    result_reviews = result_reviews or {}
    requirements_by_id = {r["id"]:r for r in requirements}
    claims, selected, usage = [], {}, {}
    assessed_ids = {row.get("requirement_id") for row in assessments}
    assessments = list(assessments) + [{"requirement_id":r["id"], "status":"unassessed",
        "reason":"当前评估未完成该要求", "citations":[]} for r in requirements if r["id"] not in assessed_ids]
    limitations = [{"requirement_id":r.get("requirement_id", ""),
                    "text":requirements_by_id.get(r.get("requirement_id"), {}).get("text", ""),
                    "status":r.get("status", "unassessed"), "reason":str(r.get("reason") or "")}
                   for r in assessments if r.get("status") != "supported"]
    for row in assessments:
        if row.get("status") not in {"supported", "partial"}:
            continue
        requirement_id = row.get("requirement_id")
        if requirement_id not in requirements_by_id:
            raise ValueError("preview_fact_changed")
        for citation, support_status in positive_citations(row):
            fact_id = citation.get("fact_id")
            old, fact = audit_facts.get(fact_id), current_facts.get(fact_id)
            if not isinstance(old, dict) or not isinstance(fact, dict):
                raise ValueError("preview_fact_changed")
            quote = citation.get("quote")
            if quote is not None and (not isinstance(quote, str) or not quote or quote not in fact.get("text", "")):
                raise ValueError("preview_fact_changed")
            qualifiers = fact.get("source_qualifiers", [])
            if not isinstance(qualifiers, list) or any(not isinstance(q, str) or not q.strip() for q in qualifiers):
                raise ValueError("preview_fact_changed")
            if any(old.get(k) != fact.get(k) for k in ("source_id", "field", "text", "source_role", "source_qualifiers")):
                raise ValueError("preview_fact_changed")
            source_id, field = fact.get("source_id"), fact.get("field")
            if not isinstance(fact_id, str) or not fact_id.startswith(str(source_id) + ":"):
                raise ValueError("preview_fact_changed")
            if (source_id == "personal_profile" or field not in {"actions", "results"}
                    or fact_id in personal_claim_exclusions):
                continue
            role = str(fact.get("source_role") or "").strip()
            if not role or role.casefold() in {"none", "null", "{}", "[]"}:
                continue
            reviewed = result_reviews.get(fact_id, {})
            if field == "results" and (
                reviewed.get("field") != field or fact_id != f"{source_id}:results:{reviewed.get('index')}"
                or reviewed.get("value") != fact.get("text")
                or reviewed.get("result_review", {}).get("outcome") != "established"
            ):
                continue
            if not judge_fact_text(fact.get("text", ""), field=field, strict=field != "results").presentable:
                continue
            selected[fact_id] = fact
            usage.setdefault(fact_id, []).append((requirement_id, support_status))
    if not selected:
        raise ValueError("no_presentable_supported_work")
    blocks, facts_for_index = [], []
    source_ids = list(dict.fromkeys(f["source_id"] for f in selected.values()))
    for source_id in source_ids:
        chosen = [(fid, fact) for fid, fact in selected.items() if fact["source_id"] == source_id]
        for context_field in ("title", "role_scope", "time_range"):
            context_id = f"{source_id}:{context_field}:0"
            context_fact = current_facts.get(context_id)
            if context_fact is not None:
                old_context = audit_facts.get(context_id)
                if (not isinstance(context_fact, dict) or not isinstance(old_context, dict)
                        or context_fact.get("source_id") != source_id or context_fact.get("field") != context_field
                        or any(old_context.get(k) != context_fact.get(k) for k in
                               ("source_id", "field", "text", "source_role", "source_qualifiers"))):
                    raise ValueError("preview_fact_changed")
        title_fact = current_facts.get(f"{source_id}:title:0")
        if not title_fact or not str(title_fact.get("text") or "").strip():
            continue
        role_fact_id = f"{source_id}:role_scope:0"
        role_fact = current_facts.get(role_fact_id)
        if not role_fact or not str(role_fact.get("text") or "").strip():
            continue
        role = str(role_fact["text"])
        if any(str(f.get("source_role") or "").strip() != role.strip() for _, f in chosen):
            raise ValueError("preview_fact_changed")
        period_fact = current_facts.get(f"{source_id}:time_range:0")
        period = str(period_fact.get("text") or "") if period_fact else ""
        context = [("title", title_fact["text"]), ("role_scope", role)]
        if period:
            context.append(("time_range", period))
        qualifiers = list(dict.fromkeys(q for _, fact in chosen for q in fact.get("source_qualifiers", [])))
        for field, text in context:
            claims.append({"fact_id":f"{source_id}:{field}:0", "source_id":source_id,
                           "field":field, "quote":text, "usage":"context",
                           "requirement_ids":[], "support_statuses":[]})
        for qualifier in qualifiers:
            qualifier_fact_id = next(fid for fid, fact in chosen if qualifier in fact.get("source_qualifiers", []))
            claims.append({"fact_id":qualifier_fact_id, "source_id":source_id, "field":"source_qualifiers",
                           "quote":qualifier, "usage":"context", "requirement_ids":[], "support_statuses":[]})
        role_item = Fact(fact_id=role_fact_id, source_id=source_id, field=role_fact["field"],
                         text=role, kind="evidence")
        facts_for_index.append(role_item)
        rendered_facts = []
        for fact_id, fact in chosen:
            item = Fact(fact_id=fact_id, source_id=source_id, field=fact["field"], text=fact["text"], kind="evidence",
                        has_quant=fact["field"] == "results" and bool(result_reviews[fact_id]["result_review"].get("measurement_quote")))
            facts_for_index.append(item)
            rendered_facts.append(item)
            claims.append({"fact_id":fact_id, "source_id":source_id, "field":fact["field"], "quote":fact["text"],
                           "usage":"supported_excerpt", "requirement_ids":list(dict.fromkeys(x[0] for x in usage[fact_id])),
                           "support_statuses":list(dict.fromkeys(x[1] for x in usage[fact_id]))})
        blocks.append(ProjectBlock(card_id=source_id, title=title_fact["text"], period=period, role=role,
            background=("责任范围原文：" + "；".join(qualifiers)) if qualifiers else "",
            key_work=tuple(f for f in rendered_facts if f.field == "actions"),
            outcomes=tuple(f for f in rendered_facts if f.field == "results"),
            fact_ids=(role_item.fact_id, *(fid for fid, _ in chosen))))
    if not blocks:
        raise ValueError("no_presentable_supported_work")
    index = FactIndex(tuple(facts_for_index))
    plan = ResumePlan(projects=tuple(blocks), fact_ids=tuple(f.fact_id for f in facts_for_index))
    rendered = render_plan(plan, index, profile={}, job_context=target)
    rendered = rendered.replace("# 个人简历", "# 内部定向事实预览（片段，非投递版）", 1).replace(FIRST_SCREEN_MARKER, "")
    notice = "> 仅呈现当前已核引用的原事实，不是完整简历或全岗位匹配结论；部分支撑与未完成要求仍须保留。\n\n"
    for field in ("company", "target_role"):
        if target.get(field):
            claims.append({"fact_id":f"job_profile:{field}", "source_id":"job_profile", "field":field,
                           "quote":target[field], "usage":"context", "requirement_ids":[], "support_statuses":[]})
    return {"markdown":notice + rendered, "claims":claims, "limitations":limitations,
            "preview_fact_count":sum(claim["usage"] == "supported_excerpt" for claim in claims)}
