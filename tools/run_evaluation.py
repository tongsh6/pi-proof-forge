#!/usr/bin/env python3
import argparse
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import sys
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.infra.llm.client import LLMClient, llm_timeout_from_env
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.persistence.review_snapshot import read_generation_trace
from tools.engines.evaluation.keyword_coverage import contains_term, keyword_coverage, unique_terms


DEFAULT_BASE_URL = "https://api.openai.com/v1"


class ParsedDoc(TypedDict):
    scalars: dict[str, str]
    lists: dict[str, list[str]]


class RuleResult(TypedDict):
    markdown: str
    total_score: int
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


def inspect_bullet_trace(bullets: list[str], verified_claims: list[dict] | None) -> dict:
    """仅接收已通过正文/输入指纹验证的 claims，完整覆盖 bullet 才计分。"""
    facts = sorted((claim for claim in (verified_claims or [])
                    if claim.get("source_kind") in {"evidence", "personal_profile"} and claim.get("text")),
                   key=lambda claim: len(claim["text"]), reverse=True)
    rows = []
    for number, bullet in enumerate(bullets, 1):
        body = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", bullet)
        remaining = body
        sources = []
        for claim in facts:
            if claim["text"] in remaining:
                remaining = remaining.replace(claim["text"], "")
                sources.append({key: claim.get(key, "") for key in ("source_kind", "field", "evidence_id")})
        covered = bool(sources) and not re.sub(r"[\s:：·、|*]", "", remaining)
        rows.append({"bullet": number, "verified": covered, "sources": sources})
    return {"status": "verified" if verified_claims is not None else "unverified",
            "verified_bullets": sum(row["verified"] for row in rows), "total_bullets": len(rows), "bullets": rows}


def evaluate_rule(
    resume_text: str,
    must_have: list[str],
    keywords: list[str],
    now: str,
    input_name: str,
    job_profile_name: str | None,
    *, verified_claims: list[dict] | None = None,
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

    traceability = inspect_bullet_trace(bullet_lines, verified_claims)
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
        "- 独立追溯: " + ("正文与输入指纹有效" if verified_claims is not None else "未验证（缺失、无效或版本已变化）"),
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
            "expression_score": round((quant_score * .2 + clarity_score * .2 + length_score * .1 + citation_score * .2) / .7),
            "keyword_coverage": coverage, "must_have_review": requirements, "traceability": traceability,
            "quantification": {"quantified_bullets":len(quantified_bullets),"total_bullets":total_bullets,"rule":"metric_or_scope_v2"},
            "gap_tasks": [task for task in gap_tasks if task != "暂无高优先级补证据任务。"]}


def _legacy_main() -> int:
    parser = argparse.ArgumentParser(description="Run evaluation workflow")
    _ = parser.add_argument("--input", required=True, help="Generated resume path")
    _ = parser.add_argument("--output", required=True, help="Scorecard output path")
    _ = parser.add_argument(
        "--job-profile", help="Job profile path for keyword coverage"
    )
    _ = parser.add_argument(
        "--use-llm", action="store_true", help="Use LLM for explanation layer"
    )
    _ = parser.add_argument(
        "--require-llm",
        action="store_true",
        help="Fail if LLM explanation is unavailable",
    )
    _ = parser.add_argument(
        "--prompt", default="tools/prompts/evaluation.md", help="Prompt template path"
    )
    _ = parser.add_argument(
        "--model", default=os.getenv("LLM_MODEL", ""), help="Model name"
    )
    _ = parser.add_argument(
        "--base-url",
        default=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        help="OpenAI-compatible base URL",
    )
    _ = parser.add_argument(
        "--api-key", default=os.getenv("LLM_API_KEY", ""), help="API key"
    )
    args = parser.parse_args()

    now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    input_path = cast(str, args.input)
    output_path = cast(str, args.output)
    job_profile_path = cast(str | None, args.job_profile)
    use_llm = cast(bool, args.use_llm)
    require_llm = cast(bool, args.require_llm)
    prompt_path = cast(str, args.prompt)
    model = cast(str, args.model)
    base_url = cast(str, args.base_url)
    api_key = cast(str, args.api_key)

    if require_llm and not use_llm:
        print("--require-llm requires --use-llm")
        return 1

    resume_text = read_text(input_path)
    must_have, keywords = collect_terms(job_profile_path)
    trace, trace_valid = read_generation_trace(Path(input_path))
    rule_result = evaluate_rule(
        resume_text=resume_text,
        must_have=must_have,
        keywords=keywords,
        now=now,
        input_name=Path(input_path).name,
        job_profile_name=Path(job_profile_path).name if job_profile_path else None,
        verified_claims=trace["claims"] if trace_valid else None,
    )

    final_markdown = rule_result["markdown"]
    semantic_review = None
    matching_source = trace.get('inputs', {}).get('matching_report', {})
    semantic_expected = trace.get('generation_strategy') == 'semantic_selection_locked_evidence_fields' or 'semantic_matching' in trace.get('inputs', {})
    if semantic_expected and (not trace_valid or not matching_source.get('path')):
        print('[evaluation] 语义生成追溯已失效，请重新生成。')
        return 1
    if matching_source.get('path'):
        from tools.infra.semantic_matching import load_semantic_report
        from tools.engines.matching.semantic_review import resume_assessment, STATUS_LABELS
        try:
            semantic = load_semantic_report(Path(matching_source['path']))
            if semantic_expected and semantic is None:
                raise ValueError('semantic_report_missing')
            if semantic:
                if not trace_valid or not job_profile_path or hashlib.sha256(Path(job_profile_path).read_bytes()).hexdigest() != semantic['inputs']['job_profile']['sha256']:
                    raise ValueError('semantic_inputs_or_trace_changed')
                semantic_review = resume_assessment(semantic, trace['claims'])
                semantic_review['direction_review']=semantic.get('direction_review')
                semantic_review['assessment_scope']=semantic.get('assessment_scope')
                semantic_review.update(reviewed_card_count=len(semantic['reviewed_card_ids']), selected_card_ids=semantic['selected_card_ids'],
                                       statistics=semantic['statistics'], expression_score=rule_result['expression_score'])
                # 关键词缺口不再冒充语义不适配；仍保留表达质量与逐项要求缺口。
                rule_result['gap_tasks'] = [task for task in rule_result['gap_tasks'] if not task.startswith(('核对缺失关键词', '逐项核对'))]
                rule_result['gap_tasks'].extend(f"{r['text']}：{STATUS_LABELS[r['resume_status']]}；{r['reason']}"
                                              for r in semantic_review['requirements'] if r['resume_status'] != 'supported')
                semantic_lines = ['## 语义匹配（模型判读，原文引用已核验）',
                                  f"- 证据池岗位适配: {semantic_review['fit_score']}/100",
                                  f"- 简历要求覆盖: {semantic_review['resume_score']}/100",
                                  f"- 表达质量: {rule_result['expression_score']}/100（不含关键词分）",
                                  f"- 全部证据评审: {len(semantic['reviewed_card_ids'])} 张"]
                for row in semantic_review['requirements']:
                    semantic_lines.extend([f"\n### {row['text']}", f"- 证据池：{STATUS_LABELS[row['status']]}；简历：{STATUS_LABELS[row['resume_status']]}", f"- 理由：{row['reason']}"])
                    for c in row['citations']:
                        semantic_lines.append(f"- 原文（{c['source_id']}.{c['field']}）：{c['quote']}")
                auxiliary = re.sub(r'\n## 硬性条件待核对\n.*?(?=\n## 逐条追溯检查)', '', final_markdown, flags=re.S)
                auxiliary = auxiliary.split('\n## 规则建议\n', 1)[0]
                final_markdown = '\n'.join(semantic_lines) + '\n\n' + auxiliary.replace('# Scorecard', '# 规则辅助指标（不作为语义适配结论）', 1)
                final_markdown += '\n## 当前待处理缺口\n' + '\n'.join('- ' + task for task in rule_result['gap_tasks']) + '\n'
        except (ValueError, OSError, TypeError, KeyError):
            print('[evaluation] 语义结果或输入追溯已变化，请重新生成。')
            return 1

    if use_llm and model and api_key and semantic_review is None:
        prompt = load_prompt(prompt_path, resume_text, rule_result["markdown"])
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是质量评测解释器，只补充解释与改进建议，不要改动规则分数。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        client = LLMClient(base_url=base_url, api_key=api_key, timeout=llm_timeout_from_env())
        response = client.post_json(client.chat_completions_url, payload)
        llm_content = client.extract_content(response)
        if llm_content:
            final_markdown = (
                final_markdown.rstrip()
                + "\n\n## LLM 解释层\n"
                + llm_content.strip()
                + "\n"
            )
        elif require_llm:
            print("LLM mode required but received empty response")
            return 1
    elif require_llm and semantic_review is None:
        print("LLM mode required but model/api_key is missing")
        return 1

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _ = output_file.write_text(final_markdown, encoding="utf-8")
    output_file.with_suffix(".json").write_text(json.dumps({
        "schema_version": 1,
        "evaluation_version": "assessment-v3",
        "resume_sha256": hashlib.sha256(resume_text.encode("utf-8")).hexdigest(),
        "total_score": rule_result["total_score"],
        "gap_tasks": rule_result["gap_tasks"],
        "keyword_coverage": rule_result["keyword_coverage"],
        "must_have_review": rule_result["must_have_review"],
        "traceability": rule_result["traceability"],
        "expression_score": rule_result["expression_score"],
        "quantification": rule_result['quantification'],
        "semantic_review": semantic_review,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    if os.getenv("PPF_FORCE_LEGACY_MAIN") == "1":
        return _legacy_main()

    from tools.cli.commands.evaluate import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
