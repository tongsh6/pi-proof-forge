#!/usr/bin/env python3
import argparse
import datetime
import os
import re
from pathlib import Path
import sys
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.infra.llm.client import LLMClient
from tools.infra.persistence.yaml_io import parse_simple_yaml


DEFAULT_BASE_URL = "https://api.openai.com/v1"


class ParsedDoc(TypedDict):
    scalars: dict[str, str]
    lists: dict[str, list[str]]


class RuleResult(TypedDict):
    markdown: str
    total_score: int


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
) -> RuleResult:
    lines: list[str] = [line for line in resume_text.splitlines() if line.strip()]
    bullet_lines: list[str] = [
        line.strip() for line in lines if re.match(r"^\s*([-*]|\d+\.)\s+", line)
    ]
    total_bullets = len(bullet_lines)

    term_pool: list[str] = []
    for term in must_have + keywords:
        term_norm = term.strip()
        if term_norm and term_norm not in term_pool:
            term_pool.append(term_norm)

    resume_lower = resume_text.lower()
    matched_terms: list[str] = [
        term for term in term_pool if term.lower() in resume_lower
    ]
    missing_terms: list[str] = [
        term for term in term_pool if term.lower() not in resume_lower
    ]

    coverage_ratio = (len(matched_terms) / len(term_pool)) if term_pool else 0.0
    coverage_score = int(round(coverage_ratio * 100)) if term_pool else 50

    quantified_bullets: list[str] = [
        line for line in bullet_lines if re.search(r"\d", line)
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

    citation_terms = term_pool if term_pool else keywords
    evidence_cited = 0
    for line in bullet_lines:
        lower = line.lower()
        has_metric = bool(re.search(r"\d", line))
        has_term = (
            any(term.lower() in lower for term in citation_terms)
            if citation_terms
            else False
        )
        if has_metric or has_term:
            evidence_cited += 1
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

    if coverage_score < 80:
        suggestions.append("补齐 must-have / keywords 在核心经历中的覆盖。")
        if missing_terms:
            gap_tasks.append(
                "补充或改写经历，覆盖缺失词：" + ", ".join(missing_terms[:5])
            )
    if quant_score < 50:
        suggestions.append("提高量化 bullets 占比，优先加入时延、成功率、成本等指标。")
        gap_tasks.append("为至少 2 条关键经历补充可量化结果。")
    if clarity_score < 70:
        suggestions.append("减少空话与重复表达，保留动作-约束-结果结构。")
    if length_score < 80:
        suggestions.append("控制篇幅到 1 页，合并冗余表述。")
    if citation_score < 70:
        suggestions.append("增加可追溯证据表达（指标/关键词/工件关联）。")
        gap_tasks.append("为关键结论补充对应 evidence card 的结果与证据引用。")

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
        f"- must-have 关键词覆盖率: {int(round(coverage_ratio * 100))}% ({len(matched_terms)}/{len(term_pool) if term_pool else 0})",
        f"- 量化占比: {int(round(quant_ratio * 100))}% ({len(quantified_bullets)}/{total_bullets})",
        f"- 空话率/重复度: {int(round(fluff_ratio * 100))}% / {int(round(duplicate_ratio * 100))}% (score={clarity_score})",
        f"- 篇幅控制: lines={line_count}, chars={char_count} (score={length_score})",
        f"- 证据引用检查: {int(round(citation_ratio * 100))}% ({evidence_cited}/{total_bullets})",
        "",
        "## 规则建议",
    ]
    for idx, item in enumerate(suggestions, start=1):
        markdown_lines.append(f"{idx}. {item}")

    markdown_lines.append("")
    markdown_lines.append("## 补证据任务")
    for item in gap_tasks:
        markdown_lines.append(f"- {item}")

    markdown = "\n".join(markdown_lines) + "\n"
    return {"markdown": markdown, "total_score": total_score}


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
    rule_result = evaluate_rule(
        resume_text=resume_text,
        must_have=must_have,
        keywords=keywords,
        now=now,
        input_name=Path(input_path).name,
        job_profile_name=Path(job_profile_path).name if job_profile_path else None,
    )

    final_markdown = rule_result["markdown"]

    if use_llm and model and api_key:
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
        client = LLMClient(base_url=base_url, api_key=api_key, timeout=120)
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
    elif require_llm:
        print("LLM mode required but model/api_key is missing")
        return 1

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _ = output_file.write_text(final_markdown, encoding="utf-8")
    return 0


def main() -> int:
    if os.getenv("PPF_FORCE_LEGACY_MAIN") == "1":
        return _legacy_main()

    from tools.cli.commands.evaluate import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
