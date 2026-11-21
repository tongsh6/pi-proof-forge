"""简历计划渲染：把 ResumePlan 排版为候选人可读的 Markdown，并记录逐条 claim。

渲染层不做选材、不做截断、不改写事实；它只决定段落顺序与排版。
每条正文都来自 FactIndex 中的原始文本，因此 trace 与正文天然一致。
"""
from __future__ import annotations

import re

from tools.domain.quality_text import render_fact_text
from tools.domain.value_objects import FIRST_SCREEN_MARKER
from tools.engines.generation.fact_index import Fact, FactIndex
from tools.engines.generation.resume_plan import ResumePlan, WorkBlock

_INTERNAL_RE = re.compile(
    r"Evidence trace|Source report|(?:/Users/|/private/|/tmp/)|\bec[-_][\w-]+", re.I
)


def _checked_fact_text(text: str) -> str:
    value = render_fact_text(text)
    if _INTERNAL_RE.search(value):
        raise ValueError("internal_metadata_in_resume_fact")
    return value


def _project_bindings(plan: ResumePlan, index: FactIndex) -> tuple[dict[str, Fact], ...]:
    """Resolve project structure before either background review or rendering."""
    bindings: list[dict[str, Fact]] = []
    for block in plan.projects:
        registered = [index.get(fact_id) for fact_id in block.fact_ids]
        if any(item is None for item in registered):
            raise ValueError("unbound_resume_fact")
        current: dict[str, Fact] = {}
        for field, text in (("context", block.background), ("role_scope", block.role)):
            value = _checked_fact_text(text)
            bound = [item for item in registered if item is not None and item.field == field]
            if len(bound) > 1:
                raise ValueError("unbound_resume_fact")
            if not bound:
                if field == "role_scope" and value:
                    raise ValueError("unbound_resume_fact")
                continue
            item = bound[0]
            if item.kind != "evidence" or not value or render_fact_text(item.text) != value:
                raise ValueError("unbound_resume_fact")
            current[field] = item
        bindings.append(current)
    registered = [index.get(fact_id) for fact_id in plan.fact_ids]
    if any(item is None for item in registered):
        raise ValueError("unbound_resume_fact")
    for field in ("context", "role_scope"):
        plan_ids = {item.fact_id for item in registered if item is not None and item.field == field}
        block_ids = {current[field].fact_id for current in bindings if field in current}
        if plan_ids != block_ids:
            raise ValueError("unbound_resume_fact")
    return tuple(bindings)


def render_plan(
    plan: ResumePlan,
    index: FactIndex,
    *,
    profile: dict,
    job_context: dict,
    claims: list[dict] | None = None,
    version: str = "A",
    positioning: str = "technical_depth",
    custom_positioning: str = "",
) -> str:
    """排版 Markdown，并在真实行位置记录已选择 Fact 的精确身份。"""
    claims = claims if claims is not None else []

    def fact(text: str, kind: str, field: str, evidence_id: str = "", *, occurrence: Fact | None = None) -> str:
        value = _checked_fact_text(text)
        if value:
            claims.append(
                {"text": value, "source_kind": kind, "field": field, "evidence_id": evidence_id,
                 **({"fact_id": occurrence.fact_id, "render_line": len(lines) + 1} if occurrence else {})}
            )
        return value

    def from_fact(item: Fact) -> str:
        if index.get(item.fact_id) != item:
            raise ValueError("unbound_resume_fact")
        return fact(item.text, "personal_profile" if item.kind == "profile" else "evidence",
                    item.field, item.source_id if item.kind == "evidence" else "", occurrence=item)

    def from_fact_id(fact_id: str) -> str:
        item = index.get(fact_id)
        return from_fact(item) if item is not None else ""

    def profile_field(field: str, text: str) -> str:
        item = index.get("personal_profile:" + field + ":0")
        return from_fact(item) if item else fact(text, "personal_profile", field)

    def work_context(block: WorkBlock) -> str:
        heading = " · ".join(
            value
            for value in (
                profile_field(f"career.work.{block.work_id}.company", block.company),
                profile_field(f"career.work.{block.work_id}.title", block.title),
            )
            if value
        )
        # The period is composed from the bound career row; only displayed dates
        # have text occurrences. "至今" remains that row's existing current flag.
        for field in ("start", "end"):
            date_fact = index.get(f"personal_profile:career.work.{block.work_id}.{field}:0")
            if date_fact is not None and date_fact.text in block.period:
                from_fact(date_fact)
        return f"{heading}（{block.period}）" if block.period else heading

    def by_suffix(fact_ids: tuple[str, ...]) -> dict[str, Fact]:
        return {item.field.rsplit(".", 1)[-1]: item for fid in fact_ids
                if (item := index.get(fid)) is not None}

    lines: list[str] = []
    name = fact(profile.get("name", ""), "personal_profile", "name")
    lines.append(f"# {name or '个人简历'}")
    contact = [fact(profile.get(key, ""), "personal_profile", key) for key in ("phone", "email", "city")]
    joined = " | ".join(value for value in contact if value)
    if joined:
        lines.append(joined)
    if profile.get("current_position"):
        lines.append("当前定位：" + fact(profile["current_position"], "personal_profile", "current_position"))
    custom = str(custom_positioning or "")
    targeted_custom = positioning == "custom" and bool(custom)
    target_role = custom if targeted_custom else str(job_context.get("target_role") or "")
    company = str(job_context.get("company") or "")
    role_kind = "positioning" if targeted_custom else "job_profile"
    if target_role:
        intent = " · ".join(
            value
            for value in (
                fact(company, "job_profile", "company") if company else "",
                fact(target_role, role_kind, "target_role"),
            )
            if value
        )
        lines.append("求职意向：" + intent)

    if plan.summary_fact_ids:
        lines.extend(["", "## 职业概述"])
        work_by_id = {block.work_id: block for block in plan.work}
        contextualized_work: set[str] = set()
        for fact_id in plan.summary_fact_ids:
            item = index.get(fact_id)
            if item is None:
                raise ValueError("unbound_resume_fact")
            context = ""
            if item.work_id and item.work_id not in contextualized_work:
                block = work_by_id.get(item.work_id)
                if block is None:
                    raise ValueError("unbound_summary_work")
                context = work_context(block)
                contextualized_work.add(item.work_id)
            text = from_fact(item)
            lines.append(f"{context}：{text}" if context else text)

    if plan.capabilities:
        lines.extend(["", "## 核心能力"])
        for block in plan.capabilities:
            by_field = by_suffix(block.fact_ids)
            category = from_fact(by_field["category"]) if "category" in by_field else fact(block.category, "personal_profile", "career.skills.category")
            description = from_fact(by_field["description"]) if "description" in by_field else fact(block.description, "personal_profile", "career.skills.description")
            lines.append(f"- {category}：{description}")

    if plan.work:
        lines.extend(["", "## 工作经历"])
        for block in plan.work:
            lines.append("### " + work_context(block))
            if block.scope:
                lines.append("场景：" + profile_field(f"career.work.{block.work_id}.scope", block.scope))
            for duty in block.duties:
                lines.append("职责：" + from_fact(duty))
            for achievement in block.achievements:
                lines.append("- " + from_fact(achievement))

    if plan.projects:
        project_bindings = _project_bindings(plan, index)

        lines.extend(["", "## 项目经历"])
        for position, (block, bindings) in enumerate(zip(plan.projects, project_bindings)):
            context_fact = bindings.get("context")
            role_fact = bindings.get("role_scope")
            # Group headings and derived scope backgrounds retain their presentation responsibility.
            title = fact(block.title, "presentation", "title")
            lines.append(f"### {title}" + (f"（{block.period}）" if block.period else ""))
            if role_fact is not None:
                lines.append("角色：" + from_fact(role_fact))
            if block.background:
                lines.append("背景：" + (from_fact(context_fact) if context_fact is not None
                                        else fact(block.background, "presentation", "context")))
            if block.work_company:
                lines.append("所属工作：" + fact(block.work_company, "personal_profile", "career.work.company"))
            for item in block.key_work:
                lines.append("- " + from_fact(item))
            for item in block.outcomes:
                lines.append("- " + from_fact(item))
            if position == 0:
                lines.extend(["", FIRST_SCREEN_MARKER, ""])
            lines.append("")

    if plan.stack:
        lines.extend(["", "## 核心技能"])
        rendered_skills = [from_fact_id(fact_id) for fact_id in plan.stack_fact_ids]
        lines.append("、".join(filter(None, rendered_skills)))

    if plan.education:
        lines.extend(["", "## 教育经历"])
        for block in plan.education:
            fs = by_suffix(block.fact_ids)
            school = from_fact(fs["school"]) if "school" in fs else fact(block.school, "personal_profile", "career.education.school")
            lines.append(f"### {school}（{block.period}）" if block.period else f"### {school}")
            parts = [
                from_fact(fs[field]) if field in fs else fact(value, "personal_profile", f"career.education.{field}")
                for field, value in (("major", block.major), ("degree", block.degree)) if value
            ]
            if parts:
                lines.append(" · ".join(parts))

    if plan.extras:
        lines.extend(["", "## 补充成果"])
        for block in plan.extras:
            fs = by_suffix(block.fact_ids)
            title = from_fact(fs["title"]) if "title" in fs else fact(block.title, "personal_profile", "career.extras.title")
            description = from_fact(fs["description"]) if "description" in fs else fact(block.description, "personal_profile", "career.extras.description")
            lines.append("- " + title + "：" + description)
            if block.url:
                lines.append(from_fact(fs["url"]) if "url" in fs else fact(block.url, "personal_profile", "career.extras.url"))

    if FIRST_SCREEN_MARKER not in lines:
        fallback = next(
            (i for i, line in enumerate(lines) if line.startswith("## 职业概述")),
            len(lines) - 1,
        )
        lines[fallback + 1:fallback + 1] = ["", FIRST_SCREEN_MARKER, ""]
        for claim in claims:
            if claim.get("render_line", 0) > fallback + 1:
                claim["render_line"] += 3

    return "\n".join(lines).rstrip() + "\n"
