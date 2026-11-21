"""质量评测编排。

流程：规则评测 → 语义评审合并（若生成时使用了语义选材）→ LLM 解释层
→ 四层质量报告 → 写 Markdown/JSON 产物。

事实边界：规则分数不可被模型改写；语义结论必须与生成 trace 的输入指纹一致；
质量报告只是分析建议，不参与投递硬门禁。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.engines.evaluation import quality_report, rule_evaluator, tiered_evaluator
from tools.engines.matching.semantic_matching import load_semantic_report
from tools.engines.matching.semantic_review import STATUS_LABELS, resume_assessment
from tools.infra.llm import client as llm
from tools.infra.persistence.review_snapshot import read_generation_trace

DEFAULT_PROMPT_PATH = "tools/prompts/evaluation.md"


@dataclass(frozen=True)
class EvaluationFlowConfig:
    input_path: Path
    output_path: Path
    job_profile_path: Path | None = None
    use_llm: bool = False
    require_llm: bool = False
    prompt_path: str = DEFAULT_PROMPT_PATH
    model: str = ""
    base_url: str = ""
    api_key: str = ""


def _merge_semantic_review(
    *,
    semantic: dict[str, Any],
    trace: dict[str, Any],
    trace_valid: bool,
    job_profile_path: Path | None,
    rule_result: dict[str, Any],
    final_markdown: str,
) -> dict[str, Any]:
    if not trace_valid or not job_profile_path:
        raise ValueError("semantic_inputs_or_trace_changed")
    if (
        hashlib.sha256(job_profile_path.read_bytes()).hexdigest()
        != semantic["inputs"]["job_profile"]["sha256"]
    ):
        raise ValueError("semantic_inputs_or_trace_changed")
    review = resume_assessment(semantic, trace["claims"],
                               occurrence_coverage_known=trace.get("occurrence_lineage_version") == 1)
    review["direction_review"] = semantic.get("direction_review")
    review["assessment_scope"] = semantic.get("assessment_scope")
    review.update(
        reviewed_card_count=len(semantic["reviewed_card_ids"]),
        selected_card_ids=semantic["selected_card_ids"],
        statistics=semantic["statistics"],
        expression_score=rule_result["expression_score"],
    )
    return review


def _render_semantic_markdown(
    *,
    semantic: dict[str, Any],
    review: dict[str, Any],
    rule_result: dict[str, Any],
    final_markdown: str,
) -> str:
    # 关键词缺口不再冒充语义不适配；仍保留表达质量与逐项要求缺口。
    rule_result["gap_tasks"] = [
        task
        for task in rule_result["gap_tasks"]
        if not task.startswith(("核对缺失关键词", "逐项核对"))
    ]
    rule_result["gap_tasks"].extend(
        f"{row['text']}：{STATUS_LABELS[row['resume_status']]}；{row['reason']}"
        for row in review["requirements"]
        if row["resume_status"] != "supported"
    )
    coverage = f"{review['resume_score']}/100" if review["occurrence_coverage_known"] else "未核验，请重新生成"
    semantic_lines = [
        "## 语义匹配（模型判读，原文引用已核验）",
        f"- 证据池岗位适配: {review['fit_score']}/100",
        f"- 简历要求覆盖: {coverage}",
        f"- 表达质量: {rule_result['expression_score']}/100（不含关键词分）",
        f"- 全部证据评审: {len(semantic['reviewed_card_ids'])} 张",
    ]
    for row in review["requirements"]:
        semantic_lines.extend(
            [
                f"\n### {row['text']}",
                f"- 证据池：{STATUS_LABELS[row['status']]}；简历：{STATUS_LABELS[row['resume_status']]}",
                f"- 理由：{row['reason']}",
            ]
        )
        for citation in row["citations"]:
            semantic_lines.append(
                f"- 原文（{citation['source_id']}.{citation['field']}）：{citation['quote']}"
            )
    auxiliary = re.sub(
        r"\n## 硬性条件待核对\n.*?(?=\n## 逐条追溯检查)",
        "",
        final_markdown,
        flags=re.S,
    )
    auxiliary = auxiliary.split("\n## 规则建议\n", 1)[0]
    merged = (
        "\n".join(semantic_lines)
        + "\n\n"
        + auxiliary.replace("# Scorecard", "# 规则辅助指标（不作为语义适配结论）", 1)
    )
    return (
        merged
        + "\n## 当前待处理缺口\n"
        + "\n".join("- " + task for task in rule_result["gap_tasks"])
        + "\n"
    )


def run_evaluation_flow(config: EvaluationFlowConfig) -> int:
    """执行质量评测。返回进程退出码：0 成功、1 语义追溯失效或 LLM 必需失败。"""
    if config.require_llm and not config.use_llm:
        print("--require-llm requires --use-llm")
        return 1

    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    input_path = config.input_path
    output_path = config.output_path
    job_profile_path = config.job_profile_path
    resume_text = rule_evaluator.read_text(input_path)
    trace, trace_valid = read_generation_trace(input_path)
    # trace 校验可能晚于正文读取；只给本次实际消费的正文版本授予追溯信用。
    trace_valid = trace_valid and trace.get("resume_sha256") == hashlib.sha256(resume_text.encode("utf-8")).hexdigest()
    quality_trace = trace if trace_valid else {}
    try:
        cards = quality_report._load_quality_cards(quality_trace)
        career = quality_report._load_quality_career(quality_trace)
        job_context = quality_report._load_job_context(
            str(job_profile_path) if job_profile_path else None, trace=quality_trace)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"[evaluation] 评测输入版本已变化或不可用：{exc}")
        return 1
    must_have = job_context.get("must_have", [])
    keywords = job_context.get("keywords", [])
    rule_result = rule_evaluator.evaluate_rule(
        resume_text=resume_text,
        must_have=must_have,
        keywords=keywords,
        now=now,
        input_name=input_path.name,
        job_profile_name=job_profile_path.name if job_profile_path else None,
        verified_trace=trace if trace_valid else None,
    )

    final_markdown = rule_result["markdown"]
    semantic_review: dict[str, Any] | None = None
    matching_source = trace.get("inputs", {}).get("matching_report", {})
    semantic_expected = (
        trace.get("generation_strategy") == "semantic_selection_locked_evidence_fields"
        or "semantic_matching" in trace.get("inputs", {})
    )
    if semantic_expected and (not trace_valid or not matching_source.get("path")):
        print("[evaluation] 语义生成追溯已失效，请重新生成。")
        return 1
    if matching_source.get("path"):
        try:
            semantic = load_semantic_report(Path(matching_source["path"]))
            if semantic_expected and semantic is None:
                raise ValueError("semantic_report_missing")
            if semantic:
                source = trace["inputs"]["semantic_matching"]
                if Path(source["path"]).resolve() != Path(matching_source["path"]).with_suffix(".semantic.json").resolve():
                    raise ValueError("semantic_report_changed")
                semantic_raw = quality_report._read_quality_input(source)
                if json.loads(semantic_raw) != semantic:
                    raise ValueError("semantic_report_changed")
                semantic_review = _merge_semantic_review(
                    semantic=semantic,
                    trace=trace,
                    trace_valid=trace_valid,
                    job_profile_path=job_profile_path,
                    rule_result=rule_result,
                    final_markdown=final_markdown,
                )
                final_markdown = _render_semantic_markdown(
                    semantic=semantic,
                    review=semantic_review,
                    rule_result=rule_result,
                    final_markdown=final_markdown,
                )
        except (ValueError, OSError, TypeError, KeyError):
            print("[evaluation] 语义结果或输入追溯已变化，请重新生成。")
            return 1

    llm_available = llm.llm_request_available(
        provider=os.getenv("LLM_PROVIDER", ""), api_key=config.api_key, model=config.model, base_url=config.base_url
    )
    if config.use_llm and llm_available and semantic_review is None:
        prompt = rule_evaluator.load_prompt(
            config.prompt_path, resume_text, rule_result["markdown"]
        )
        payload: dict[str, object] = {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是质量评测解释器，只补充解释与改进建议，不要改动规则分数。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }
        client = llm.LLMClient(
            base_url=config.base_url,
            api_key=config.api_key,
            timeout=llm.llm_timeout_from_env(),
        )
        response = client.post_json(client.chat_completions_url, payload)
        llm_content = client.extract_content(response)
        if llm_content:
            final_markdown = (
                final_markdown.rstrip()
                + "\n\n## LLM 解释层\n"
                + llm_content.strip()
                + "\n"
            )
        elif config.require_llm:
            print("LLM mode required but received empty response")
            return 1
    elif config.require_llm and semantic_review is None:
        print("LLM mode required but model/api_key is missing")
        return 1

    # Judge 与四层报告共用本次已核字节解析出的同一批事实。
    quality_judgments, judge_meta, judge_decisions = quality_report._run_quality_judge(
        resume_text=resume_text,
        trace=quality_trace,
        cards=cards,
        semantic_review=semantic_review,
        job_profile_path=str(job_profile_path) if job_profile_path else None,
        use_llm=config.use_llm,
        model=config.model,
        api_key=config.api_key,
        base_url=config.base_url,
    )
    quality = None
    try:
        quality = tiered_evaluator.build_quality_report(
            resume=resume_text,
            trace=quality_trace,
            career_profile=career,
            cards=cards,
            semantic_review=semantic_review,
            job_context=job_context,
            pdf_check=None,
            judgments=quality_judgments,
            decisions=judge_decisions,
            judge_meta=judge_meta,
            resume_version=hashlib.sha256(resume_text.encode("utf-8")).hexdigest(),
            job_profile_id=job_profile_path.stem if job_profile_path else "",
            legacy_scores={
                "rule_total": rule_result["total_score"],
                "llm_expression": rule_result["expression_score"],
            },
        )
        final_markdown = final_markdown.rstrip() + "\n" + quality_report._quality_markdown(quality)
    except (OSError, ValueError, TypeError) as exc:
        judge_meta = {**judge_meta, "report_error": str(exc)[:300]}
        print(f"[evaluation] 四层质量报告生成失败：{exc}")

    if trace_valid:
        current_trace, current_valid = read_generation_trace(input_path)
        if not current_valid or current_trace != trace:
            print("[evaluation] 评测期间正文或来源已变化，未发布报告。")
            return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = output_path.write_text(final_markdown, encoding="utf-8")
    _ = output_path.with_suffix(".json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "evaluation_version": "quality-v1",
                "resume_sha256": hashlib.sha256(resume_text.encode("utf-8")).hexdigest(),
                "total_score": rule_result["total_score"],
                "gap_tasks": rule_result["gap_tasks"],
                "keyword_coverage": rule_result["keyword_coverage"],
                "must_have_review": rule_result["must_have_review"],
                "traceability": rule_result["traceability"],
                "expression_score": rule_result["expression_score"],
                "quantification": rule_result["quantification"],
                "semantic_review": semantic_review,
                "quality_report": quality,
                "quality_judge": judge_meta,
                "legacy_scores": {
                    "rule_total": rule_result["total_score"],
                    "llm_expression": rule_result["expression_score"],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0
