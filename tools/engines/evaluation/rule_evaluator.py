"""质量评测引擎（规则实现 + 四层质量报告入口）。

主链路（Quick Run evaluation 阶段）的规则评测唯一实现：关键词覆盖、量化占比、
空话/重复、篇幅与逐条追溯检查。``RuleEvaluationEngine`` 是 domain 模型适配的
引擎实现，供 Agent 编排的策略注册表使用。
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import TypedDict

from tools.domain.models import JobProfile, ResumeOutput, Scorecard
from tools.infra.persistence.yaml_io import parse_simple_yaml

from .keyword_coverage import contains_term, keyword_coverage, unique_terms
from .tiers.common import inspect_bullet_trace


class RuleResult(TypedDict):
    markdown: str
    total_score: int
    dimension_scores: dict[str, float]
    gap_tasks: list[str]
    keyword_coverage: dict
    must_have_review: list[dict]
    traceability: dict
    expression_score: int

def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_prompt(template_path: str, resume_text: str, rule_scorecard: str) -> str:
    template = read_text(template_path)
    content = template.replace("<RESUME_CONTENT>", resume_text)
    return content.replace("<RULE_SCORECARD>", rule_scorecard)

def collect_terms(job_profile_path: str | None) -> tuple[list[str], list[str]]:
    if not job_profile_path:
        return [], []
    doc = parse_simple_yaml(read_text(job_profile_path))
    must_have = doc["lists"].get("must_have", [])
    keywords = doc["lists"].get("keywords", [])
    return must_have, keywords


def normalize_line(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def evaluate_rule(
    resume_text: str,
    must_have: list[str],
    keywords: list[str],
    now: str,
    input_name: str,
    job_profile_name: str | None,
    *, verified_trace: dict | None = None,
) -> RuleResult:
    lines: list[str] = [line for line in resume_text.splitlines() if line.strip()]
    bullet_lines: list[str] = [
        line.strip() for line in lines if re.match(r"^\s*([-*]|\d+\.)\s+", line)
    ]
    total_bullets = len(bullet_lines)

    coverage = keyword_coverage(resume_text, keywords)
    term_pool = unique_terms(keywords)
    matched_terms, missing_terms = coverage["matched"], coverage["missing"]
    coverage_ratio = coverage["ratio"]
    coverage_score = int(round(coverage_ratio * 100)) if coverage_ratio is not None else 50
    requirements = [{"requirement": requirement, "status": "needs_review",
                     "matched_keywords": [term for term in matched_terms if contains_term(requirement, term)],
                     "missing_keywords": [term for term in missing_terms if contains_term(requirement, term)]}
                    for requirement in unique_terms(must_have)]

    quantified_bullets: list[str] = [
        line for line in bullet_lines if re.search(r'\d[\d,.]*\s*(?:%|ms\b|毫秒|秒|分钟|小时|万条|条|次|个(?:品牌|模块|系统|服务)|QPS\b|TPS\b|GB\b|TB\b)',line,re.I)
        and re.search(r'降低|降至|下降|提升|提高|减少|缩短|节省|从|由|不超过|覆盖|处理|构造|验证|耗时|延迟|成功率|吞吐|规模',line)
    ]
    quant_ratio = (len(quantified_bullets) / total_bullets) if total_bullets else 0.0
    quant_score = int(round(quant_ratio * 100))

    fluff_words = ["负责", "参与", "协同", "支持", "推进", "优化", "提升", "相关"]
    tech_words = [
        "java",
        "go",
        "python",
        "redis",
        "kafka",
        "mysql",
        "kubernetes",
        "slo",
        "sla",
    ]
    fluff_bullets = 0
    for line in bullet_lines:
        lower = line.lower()
        has_fluff = any(word in line for word in fluff_words)
        has_concrete = bool(re.search(r"\d", line)) or any(
            word in lower for word in tech_words
        )
        if has_fluff and not has_concrete:
            fluff_bullets += 1

    fluff_ratio = (fluff_bullets / total_bullets) if total_bullets else 0.0

    normalized_bullets: list[str] = [normalize_line(line) for line in bullet_lines]
    unique_bullets = len(set(normalized_bullets))
    duplicate_count = total_bullets - unique_bullets
    duplicate_ratio = (duplicate_count / total_bullets) if total_bullets else 0.0
    clarity_score = max(0, 100 - int(round(fluff_ratio * 70 + duplicate_ratio * 30)))

    char_count = len(resume_text)
    line_count = len(lines)
    length_penalty = 0
    if char_count > 5000:
        length_penalty += min(40, int((char_count - 5000) / 100))
    if line_count > 120:
        length_penalty += min(40, (line_count - 120))
    length_score = max(0, 100 - length_penalty)

    traceability = inspect_bullet_trace(resume_text, verified_trace)
    traceability["bullets"] = [
        {"bullet": row["number"], "verified": row["verified"], "sources": row["sources"]}
        for row in traceability["bullets"]
    ]
    evidence_cited = traceability["verified_bullets"]
    citation_ratio = (evidence_cited / total_bullets) if total_bullets else 0.0
    citation_score = int(round(citation_ratio * 100))

    total_score = int(
        round(
            coverage_score * 0.30
            + quant_score * 0.20
            + clarity_score * 0.20
            + length_score * 0.10
            + citation_score * 0.20
        )
    )

    suggestions: list[str] = []
    gap_tasks: list[str] = []

    if coverage_ratio is not None and coverage_score < 80:
        suggestions.append("核对缺失岗位关键词是否有真实经历支撑，有依据后再调整选材。")
        if missing_terms:
            gap_tasks.append(
                "核对缺失关键词的已有证据（无依据则保留缺口）：" + ", ".join(missing_terms)
            )
    if requirements:
        gap_tasks.append(f"逐项核对 {len(requirements)} 项岗位硬性条件的证据，词面命中不代表条件满足。")
    if quant_score < 50:
        suggestions.append("核对关键经历是否已有可验证的时延、规模或成本结果；未知指标保持未知。")
        gap_tasks.append("核对关键经历的已有量化依据；不要为评分补写未知指标。")
    if clarity_score < 70:
        suggestions.append("减少空话与重复表达，保留动作-约束-结果结构。")
    if length_score < 80:
        suggestions.append("按阅读目的检查 PDF 分页和信息密度，合并冗余表述。")
    if citation_score < 70:
        suggestions.append("核对独立追溯记录及其输入版本，补齐未验证条目的来源。")
        gap_tasks.append("重新生成有效追溯，或为未验证简历条目补充真实来源。")

    if not suggestions:
        suggestions.append("整体质量较好，按目标 JD 微调关键词与语气即可。")
    if not gap_tasks:
        gap_tasks.append("暂无高优先级补证据任务。")

    profile_line = (
        f"Job Profile: {job_profile_name}" if job_profile_name else "Job Profile: n/a"
    )
    markdown_lines: list[str] = [
        "# Scorecard",
        f"Generated at: {now}",
        f"Input: {input_name}",
        profile_line,
        "",
        f"- 总分: {total_score}/100",
        (f"- 岗位关键词覆盖率: {int(round(coverage_ratio * 100))}% ({len(matched_terms)}/{len(term_pool)})"
         if coverage_ratio is not None else "- 岗位关键词覆盖率: 未配置（中性分 50）"),
        "- 覆盖口径: 仅词面出现，不代表岗位匹配度或硬性条件满足；求职意向不计入。",
        "- 命中关键词: " + ("、".join(matched_terms) or "无"),
        "- 缺失关键词: " + ("、".join(missing_terms) or "无"),
        f"- 量化占比: {int(round(quant_ratio * 100))}% ({len(quantified_bullets)}/{total_bullets})",
        f"- 空话率/重复度: {int(round(fluff_ratio * 100))}% / {int(round(duplicate_ratio * 100))}% (score={clarity_score})",
        f"- 篇幅控制: lines={line_count}, chars={char_count} (score={length_score})",
        f"- 证据引用检查: {int(round(citation_ratio * 100))}% ({evidence_cited}/{total_bullets})",
        "- 独立追溯: " + ("正文与输入指纹有效" if verified_trace is not None else "未验证（缺失、无效或版本已变化）"),
        "",
        "## 硬性条件待核对",
    ]
    for item in requirements:
        markdown_lines.extend([f"- {item['requirement']}（待核对）",
                               "  - 词面线索: " + ("、".join(item["matched_keywords"]) or "无"),
                               "  - 未出现的关键词: " + ("、".join(item["missing_keywords"]) or "无")])
    if not requirements:
        markdown_lines.append("未配置硬性条件。")
    markdown_lines.extend(["", "## 逐条追溯检查"])
    for row in traceability["bullets"]:
        sources = "、".join(f"{ref['evidence_id'] or ref['source_kind']}.{ref['field']}" for ref in row["sources"])
        markdown_lines.append(f"- 第 {row['bullet']} 条：{'已验证' if row['verified'] else '未验证'}" + (f"；来源 {sources}" if sources else ""))
    markdown_lines.extend(["", "## 规则建议"])
    for idx, item in enumerate(suggestions, start=1):
        markdown_lines.append(f"{idx}. {item}")

    markdown_lines.append("")
    markdown_lines.append("## 补证据任务")
    for item in gap_tasks:
        markdown_lines.append(f"- {item}")

    markdown = "\n".join(markdown_lines) + "\n"
    return {"markdown": markdown, "total_score": total_score,
            "dimension_scores": {
                "coverage": round(coverage_score / 100, 4),
                "quant": round(quant_score / 100, 4),
                "clarity": round(clarity_score / 100, 4),
                "length": round(length_score / 100, 4),
                "citation": round(citation_score / 100, 4),
            },
            "expression_score": round((quant_score * .2 + clarity_score * .2 + length_score * .1 + citation_score * .2) / .7),
            "keyword_coverage": coverage, "must_have_review": requirements, "traceability": traceability,
            "quantification": {"quantified_bullets":len(quantified_bullets),"total_bullets":total_bullets,"rule":"metric_or_scope_v2"},
            "gap_tasks": [task for task in gap_tasks if task != "暂无高优先级补证据任务。"]}


class RuleEvaluationEngine:
    """domain 模型适配：使用真实规则评测（覆盖/量化/空话/篇幅/追溯）。"""

    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard:
        from tools.infra.persistence.review_snapshot import validate_generation_trace

        verified_trace = None
        if resume.generation_trace is not None:
            if not validate_generation_trace(resume.content, resume.generation_trace):
                raise ValueError('generation_trace_invalid')
            verified_trace = resume.generation_trace
        result = evaluate_rule(
            resume_text=resume.content,
            must_have=list(profile.must_have),
            keywords=list(profile.keywords),
            now=datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            input_name=f"{resume.version}.md",
            job_profile_name=profile.id,
            verified_trace=verified_trace,
        )
        return Scorecard(
            resume_version=resume.version,
            job_profile_id=profile.id,
            total_score=round(result["total_score"] / 100, 4),
            dimension_scores=dict(result["dimension_scores"]),
        )
