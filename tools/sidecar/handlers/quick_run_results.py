"""Quick Run 结果：材料/证据选择、路径解析、结果详情与 PDF 导出。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from tools.infra.export.pdf_exporter import markdown_to_pdf, pdf_page_count
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.sidecar.handlers.resume import read_generation_trace

from ._shared.agent_runtime import _validate_run_resource_id


def _facade():
    """门面模块：路径常量、Popen 与运行态由 handlers/agent.py 持有（可被测试 patch）。"""
    from tools.sidecar.handlers import agent

    return agent

def _quick_run_material_sources() -> list[dict[str, Any]]:
    materials_dir = _facade()._PROJECT_ROOT / "materials"
    if not materials_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for meta_path in sorted(materials_dir.glob("*.meta.yaml")):
        try:
            values = dict(parse_simple_yaml(meta_path.read_text(encoding="utf-8"))["scalars"])
        except OSError:
            continue
        filename = values.get("filename", "")
        file_path = meta_path.parent / filename if filename else Path("")
        items.append(
            {
                "material_id": values.get("material_id", meta_path.stem.removesuffix(".meta")),
                "resource_id": values.get("resource_id", ""),
                "label": values.get("label", ""),
                "kind": values.get("kind", "raw_work_material"),
                "filename": filename,
                "extension": values.get("extension", Path(filename).suffix.lower()),
                "uploaded_at": values.get("uploaded_at", ""),
                "preview": values.get("preview", ""),
                "path": str(file_path),
            }
        )
    return sorted(items, key=lambda item: str(item.get("uploaded_at", "")), reverse=True)


def _select_quick_run_material(options: dict[str, Any]) -> dict[str, Any] | None:
    requested_id = str(options.get("material_id") or "").strip()
    sources = _quick_run_material_sources()
    if requested_id:
        for source in sources:
            if source.get("material_id") == requested_id:
                return source
        raise ValueError(f"material_id does not exist: {requested_id}")
    return sources[0] if sources else None


def _quick_run_paths(
    job_profile_id: str, options: dict[str, Any]
) -> tuple[Path, Path, dict[str, Any] | None]:
    material_context = None
    if options.get("raw_path"):
        raw_path = _resolve_project_path(str(options.get("raw_path")))
    else:
        material_context = _select_quick_run_material(options)
        raw_path = (
            Path(str(material_context["path"]))
            if material_context is not None
            else _resolve_project_path("tools/sample_raw.txt")
        )
    job_profile_path = _resolve_project_path(
        str(options.get("job_profile_path") or f"job_profiles/{job_profile_id}.yaml")
    )
    if not raw_path.exists():
        raise ValueError(f"raw_path does not exist: {raw_path}")
    if not job_profile_path.exists():
        raise ValueError(f"job_profile_path does not exist: {job_profile_path}")
    return raw_path, job_profile_path, material_context


def _load_quick_run_summary(run_id: str) -> dict[str, Any]:
    summary_path = _facade()._PROJECT_ROOT / "outputs" / "agent_runs" / run_id / "summary.json"
    if not summary_path.exists():
        return {}
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_matching_scores(matching_path: Path) -> tuple[int | None, dict[str, dict[str, Any]]]:
    if not matching_path.exists():
        return None, {}
    text = matching_path.read_text(encoding="utf-8")
    total_match = re.search(r"(?m)^score_total:\s*([0-9]+(?:\.[0-9]+)?)\s*$", text)
    score_total = int(float(total_match.group(1))) if total_match else None
    breakdown: dict[str, dict[str, Any]] = {}
    for key, score, reason in re.findall(
        r'(?m)^\s+([KDSQER]):\s*\{\s*score:\s*([0-9]+(?:\.[0-9]+)?),\s*reason:\s*"([^"]*)"',
        text,
    ):
        breakdown[key] = {
            "score": int(float(score)),
            "reason": reason,
        }
    return score_total, breakdown


def _parse_matching_evidence_ids(matching_path: Path) -> list[str]:
    if not matching_path.exists():
        return []
    try:
        doc = parse_simple_yaml(matching_path.read_text(encoding="utf-8"))
    except OSError:
        return []
    return [str(item) for item in doc["lists"].get("evidence_card_ids", [])]


def _load_evidence_trace(evidence_path: Path) -> dict[str, Any]:
    if not evidence_path.exists():
        return {}
    try:
        doc = parse_simple_yaml(evidence_path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return {
        "evidence_id": doc["scalars"].get("id", evidence_path.stem),
        "raw_source": doc["scalars"].get("raw_source", ""),
        "artifacts": [str(item) for item in doc["lists"].get("artifacts", [])],
        "results_count": len(doc["lists"].get("results", [])),
    }


def _load_evidence_traces(evidence_artifact: str) -> list[dict[str, Any]]:
    if not evidence_artifact:
        return []
    evidence_path = _resolve_project_path(evidence_artifact)
    if evidence_path.is_dir():
        return [
            trace
            for trace in (
                _load_evidence_trace(path) for path in sorted(evidence_path.glob("*.yaml"))
            )
            if trace
        ]
    trace = _load_evidence_trace(evidence_path)
    return [trace] if trace else []


def _parse_matching_lists(matching_path: Path) -> dict[str, list[str]]:
    # 匹配阶段失败时报告文件不存在；结果解析必须仍能给出失败原因，而不是 KeyError。
    if not matching_path.exists():
        return {"gaps": [], "gap_tasks": []}
    try:
        doc = parse_simple_yaml(matching_path.read_text(encoding="utf-8"))
    except OSError:
        return {"gaps": [], "gap_tasks": []}
    return {
        "gaps": [str(item) for item in doc["lists"].get("gaps", [])],
        "gap_tasks": [str(item) for item in doc["lists"].get("gap_tasks", [])],
    }


def _load_job_profile_context(job_profile_id: str, job_profile_path: Path) -> dict[str, Any]:
    try:
        doc = parse_simple_yaml(job_profile_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"job_profile_path cannot be read: {job_profile_path}") from exc
    status = doc["scalars"].get("status", "").strip()
    complete = status == "active"
    if not complete:
        raise ValueError(f"job_profile_not_complete: {job_profile_id}")
    return {
        "job_profile_id": job_profile_id,
        "status": status,
        "active_target_eligible": True,
        "title": doc["scalars"].get("target_role", job_profile_id),
        "company": doc["scalars"].get("company", ""),
    }


def _is_saved_eligible_evidence(doc: dict[str, dict[str, Any]]) -> bool:
    scalars = doc["scalars"]
    lists = doc["lists"]
    return (
        scalars.get("status", "") == "saved_eligible"
        and scalars.get("candidate_pool_eligible", "") == "true"
        and bool(lists.get("results", []))
        and bool(lists.get("artifacts", []))
    )


def _load_eligible_evidence_card(path: Path) -> dict[str, Any]:
    try:
        doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"evidence_card_unreadable: {path.stem}") from exc
    if not _is_saved_eligible_evidence(doc):
        raise ValueError(f"evidence_card_not_eligible: {path.stem}")
    from tools.infra.evidence_sources import validated_source_inputs
    validated_source_inputs(doc,path.parent.parent/'materials')
    return {
        "evidence_id": doc["scalars"].get("id", path.stem),
        "path": path,
        "raw_source": doc["scalars"].get("raw_source", ""),
        "source_material_ids": [str(item) for item in doc["lists"].get("source_material_ids", [])],
    }


def _selected_evidence_cards(
    evidence_id: str | None, options: dict[str, Any]
) -> list[dict[str, Any]]:
    requested: list[str] = []
    evidence_ids = options.get("evidence_ids")
    if isinstance(evidence_ids, list):
        requested.extend(str(item).strip() for item in evidence_ids if str(item).strip())
    if evidence_id:
        requested.append(str(evidence_id).strip())
    requested = list(dict.fromkeys(requested))

    if requested:
        cards = []
        for card_id in requested:
            _validate_run_resource_id("evidence_id", card_id)
            path = _evidence_card_dir() / f"{card_id}.yaml"
            if not path.exists():
                raise ValueError(f"evidence_card_not_found: {card_id}")
            cards.append(_load_eligible_evidence_card(path))
        return cards

    evidence_card_dir = _evidence_card_dir()
    if not evidence_card_dir.exists():
        raise ValueError("no_eligible_evidence_cards")
    cards = []
    for path in sorted(evidence_card_dir.glob("*.yaml")):
        try:
            cards.append(_load_eligible_evidence_card(path))
        except ValueError:
            continue
    if not cards:
        raise ValueError("no_eligible_evidence_cards")
    return cards


def _stage_selected_evidence(cards: list[dict[str, Any]], evidence_dir: Path) -> None:
    target_dir = _facade()._PROJECT_ROOT / evidence_dir
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for card in cards:
        shutil.copy2(card["path"], target_dir / card["path"].name)


def _quick_run_positioning(options: dict[str, Any]) -> dict[str, str]:
    mode = str(options.get("resume_positioning") or "technical_depth").strip()
    custom = str(options.get("custom_positioning") or "").strip()
    allowed = {
        "technical_depth": "Technical depth",
        "delivery_owner": "Delivery owner",
        "custom": custom or "Custom positioning",
    }
    if mode not in allowed:
        mode = "technical_depth"
    return {
        "mode": mode,
        "label": allowed[mode],
        "custom": custom if mode == "custom" else "",
    }


def _export_resume_pdf(run_id: str, artifacts: dict[str, object]) -> str:
    resume_dir_artifact = artifacts.get("resume_dir")
    if not isinstance(resume_dir_artifact, str) or not resume_dir_artifact:
        return ""
    resume_md = _resolve_project_path(resume_dir_artifact) / f"resume_mr-{run_id}_A.md"
    if not resume_md.exists():
        return ""
    from tools.infra.export.resume_filename import pdf_filename_for_resume
    pdf_path = _facade()._PROJECT_ROOT / "outputs" / "quick_runs" / run_id / "exports" / pdf_filename_for_resume(resume_md, _facade()._PROJECT_ROOT / 'outputs', readable=True)
    trace_path=resume_md.with_suffix('.trace.json')
    source_hash=hashlib.sha256(resume_md.read_bytes()).hexdigest()
    trace_hash=hashlib.sha256(trace_path.read_bytes()).hexdigest() if trace_path.is_file() else ''
    _facade().markdown_to_pdf(resume_md, pdf_path)
    if (hashlib.sha256(resume_md.read_bytes()).hexdigest()!=source_hash
            or (hashlib.sha256(trace_path.read_bytes()).hexdigest() if trace_path.is_file() else '')!=trace_hash):
        raise RuntimeError('resume_pdf_source_changed')
    artifacts['resume_pdf_source_sha256']=source_hash
    artifacts['resume_pdf_trace_sha256']=trace_hash
    return str(pdf_path.relative_to(_facade()._PROJECT_ROOT))


def _quick_run_result_details(
    run_id: str,
    stdout: str,
    stderr: str,
    *,
    selected_evidence_card_ids: list[str] | None = None,
    resume_positioning: dict[str, str] | None = None,
) -> dict[str, Any]:
    summary_payload = _load_quick_run_summary(run_id)
    artifacts = summary_payload.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
    failed_step = summary_payload.get("failed_step", "")
    reason = summary_payload.get("reason", "")
    matching_artifact = artifacts.get("matching")
    evidence_artifact = artifacts.get("evidence")
    resume_dir_artifact = artifacts.get("resume_dir")
    scorecard_artifact = artifacts.get("scorecard")
    score_total: int | None = None
    score_breakdown: dict[str, dict[str, Any]] = {}
    career_direction=None
    evidence_card_ids: list[str] = []
    if isinstance(matching_artifact, str) and matching_artifact:
        matching_path = _resolve_project_path(matching_artifact)
        score_total, score_breakdown = _parse_matching_scores(matching_path)
        evidence_card_ids = _parse_matching_evidence_ids(matching_path)
        matching_lists = _parse_matching_lists(matching_path)
        direction_path=matching_path.with_suffix('.direction.json')
        if direction_path.is_file():
            try:
                from tools.engines.matching.semantic_matching import load_direction_report
                career_direction=load_direction_report(direction_path)
            except (ValueError,OSError,KeyError,TypeError):pass
    else:
        matching_lists = {"gaps": [], "gap_tasks": []}
    evidence_traces = (
        _load_evidence_traces(evidence_artifact)
        if isinstance(evidence_artifact, str)
        else []
    )
    evidence_trace = evidence_traces[0] if evidence_traces else {}
    resume_a: Path | None = (
        _resolve_project_path(resume_dir_artifact) / f"resume_mr-{run_id}_A.md"
        if isinstance(resume_dir_artifact, str) and resume_dir_artifact
        else None
    )
    pdf_artifact = ""
    pdf_export_error = ""
    if resume_a is not None and resume_a.exists():
        try:
            pdf_artifact = _export_resume_pdf(run_id, artifacts)
            if pdf_artifact:
                artifacts["resume_pdf"] = pdf_artifact
                artifacts["resume_pdf_sha256"] = hashlib.sha256(_resolve_project_path(pdf_artifact).read_bytes()).hexdigest()
                artifacts["resume_html"] = str(_resolve_project_path(pdf_artifact).with_suffix('.html'))
        except (RuntimeError, OSError) as exc:
            pdf_export_error = str(exc)
    resume_traceable = False
    generation_trace: dict[str, Any] = {}
    if resume_a is not None and resume_a.exists():
        generation_trace, trace_valid = read_generation_trace(resume_a)
        resume_traceable = trace_valid and set(generation_trace.get("evidence_card_ids", [])).issubset(
            set(evidence_card_ids)
        )
        if generation_trace:
            artifacts["resume_trace"] = str(resume_a.with_suffix(".trace.json"))
    selected_ids = selected_evidence_card_ids or []
    matching_uses_selected_evidence = bool(evidence_card_ids) and set(evidence_card_ids).issubset(
        set(selected_ids)
    )
    readiness = dict(generation_trace.get("readiness") or {})
    readiness["status"] = (
        "NEEDS_EVIDENCE" if readiness.get("missing_profile_fields") or readiness.get("missing_target_fields") or readiness.get("missing_evidence_fields") or readiness.get("missing_career_fields")
        else "NEEDS_REVIEW"
    )
    reasons = list(readiness.get("reasons") or ["需人工审核简历事实与岗位适用性"])
    evaluation_score = None
    semantic_review = None
    quality_report: dict[str, Any] | None = None
    evaluation_gaps: list[str] = []
    if resume_a is not None and isinstance(scorecard_artifact, str) and scorecard_artifact:
        try:
            score = json.loads(_resolve_project_path(scorecard_artifact).with_suffix(".json").read_text(encoding="utf-8"))
            value = score.get("total_score")
            if (
                score.get("resume_sha256") == hashlib.sha256(resume_a.read_bytes()).hexdigest()
                and type(value) in (int, float) and 0 <= value <= 100
            ):
                evaluation_score = value
                evaluation_gaps = [str(task) for task in score.get("gap_tasks", [])]
                semantic_value = score.get('semantic_review')
                if isinstance(semantic_value, dict) and semantic_value.get('mode') == 'semantic':
                    semantic_review = semantic_value
                    expression = score.get('expression_score')
                    evaluation_score = expression if type(expression) in (int, float) and 0 <= expression <= 100 else None
                report_value = score.get('quality_report')
                if isinstance(report_value, dict):
                    quality_report = report_value
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    if quality_report is not None and pdf_artifact:
        from tools.engines.evaluation import tiered_evaluator

        pdf_path = _resolve_project_path(pdf_artifact)
        quality_report = tiered_evaluator.apply_pdf_check(
            quality_report,
            {
                "pages": _facade().pdf_page_count(pdf_path),
                "clipped": None,
                "clip_check": "not_available",
                "path": pdf_artifact,
            },
        )
    advisory_messages = {"保持当前证据完整度，按新 JD 微调关键词", "暂无高优先级补证据任务。"}
    pending_gaps = list(dict.fromkeys(
        task for task in [*matching_lists.get("gap_tasks", []), *evaluation_gaps]
        if task not in advisory_messages
    ))
    quality_failures: list[str] = []
    if isinstance(quality_report, dict):
        tiers = quality_report.get("tiers") if isinstance(quality_report.get("tiers"), dict) else {}
        for tier_name in ("eligible", "fit", "strong", "distinct"):
            tier = tiers.get(tier_name) if isinstance(tiers, dict) else None
            tier = tier if isinstance(tier, dict) else {}
            for failure in tier.get("failures", []) or []:
                if not isinstance(failure, dict):
                    continue
                quality_failures.append(
                    f"{failure.get('rule', '')} {failure.get('target', '')}：{failure.get('reason', '')}".strip()
                )
        pending_rules = quality_report.get("llm_pending") or []
        if pending_rules:
            quality_failures.append(
                "LLM 判项未完成或覆盖不足：" + "、".join(str(item) for item in pending_rules)
            )
    auto_pass = bool(quality_report.get("auto_pass")) if isinstance(quality_report, dict) else False
    if not resume_traceable:
        reasons.append("独立追溯缺失或正文/输入已变化，请重新生成并审核")
    if quality_report is None:
        reasons.append("缺少四层质量报告（旧版评测结果），请重新生成并评测")
    elif not auto_pass:
        if quality_failures:
            reasons.extend(quality_failures[:8])
        else:
            reasons.append("四层质量报告未全部通过")
    if semantic_review and not semantic_review.get('all_requirements_supported'):
        reasons.append('岗位要求仍有证据不足、部分支持、冲突或简历未呈现的项目')
    if pending_gaps:
        reasons.append("仍有待处理的证据或岗位匹配缺口")
    if pdf_export_error:
        reasons.append("PDF 导出失败：" + pdf_export_error)
    reasons = list(dict.fromkeys(reasons))
    quality_passed = bool(
        quality_report is not None
        and auto_pass
        and resume_traceable
        and matching_uses_selected_evidence
        and bool(pdf_artifact)
        and readiness["status"] != "NEEDS_EVIDENCE"
        and (semantic_review is None or semantic_review.get('all_requirements_supported') is True)
    )
    readiness.update({
        "deliverable": False,
        # 质量报告是建议与护栏，不是用户投递权的开关；前端据此展示“仍可继续”。
        "manual_override_allowed": True,
        "quality_gate_blocking": False,
        "evaluation_score": evaluation_score,
        "auto_pass": auto_pass,
        "quality_report": quality_report,
        "quality_failures": quality_failures[:20],
        "gap_tasks": pending_gaps,
        "reasons": reasons,
        "quality_passed": quality_passed,
    })
    if resume_a is None or not resume_a.is_file():
        readiness.update(status="NOT_GENERATED", content_ready=False, quality_passed=False,
                         reasons=["本次未生成简历"])
    return {
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
        "artifacts": artifacts,
        "failed_step": failed_step if isinstance(failed_step, str) else "",
        "reason": reason if isinstance(reason, str) else "",
        "score_total": score_total,
        "score_breakdown": score_breakdown,
        "semantic_review": semantic_review,
        "quality_report": quality_report,
        "career_direction":career_direction,
        "gaps": matching_lists.get("gaps", []),
        "gap_tasks": matching_lists.get("gap_tasks", []),
        "resume_positioning": resume_positioning or {},
        "resume_pdf": pdf_artifact,
        "pdf_export_error": pdf_export_error,
        "resume_readiness": readiness,
        "traceability": {
            "evidence_card_ids": evidence_card_ids,
            "selected_evidence_card_ids": selected_ids,
            "evidence": evidence_trace,
            "evidence_cards": evidence_traces,
            "resume_a": str(resume_a) if resume_a is not None else "",
            "resume_pdf": pdf_artifact,
            "resume_traceable": resume_traceable,
            "scorecard": scorecard_artifact if isinstance(scorecard_artifact, str) else "",
            "matching_uses_selected_evidence": matching_uses_selected_evidence,
            "fact_preserving_traceability": (
                matching_uses_selected_evidence and resume_traceable and bool(pdf_artifact)
            ),
        },
    }


def _persisted_llm_runtime_context() -> tuple[dict[str, Any], dict[str, str]]:
    from tools.sidecar.handlers.settings import _load_llm_config

    config = _load_llm_config()

    def clean_str(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    summary = {
        "provider": clean_str(config.get("provider")),
        "model": clean_str(config.get("model")),
        "base_url": clean_str(config.get("base_url")),
        "api_key": {
            "configured": bool(config.get("api_key_configured")),
            "masked": True,
            "updated_at": clean_str(config.get("api_key_updated_at")),
            "source": clean_str(config.get("api_key_source")),
        },
        "configured_providers": list(config.get("configured_providers") or []),
        "thinking_enabled": bool(config.get("thinking_enabled")),
        "thinking_effort": clean_str(config.get("thinking_effort")) or "high",
        "timeout": int(config.get("timeout") or 60),
        "temperature": float(config.get("temperature") or 0.2),
    }
    env: dict[str, str] = {}
    if summary["provider"]:
        env["LLM_PROVIDER"] = str(summary["provider"])
    if summary["model"]:
        env["LLM_MODEL"] = str(summary["model"])
    if summary["base_url"]:
        env["LLM_BASE_URL"] = str(summary["base_url"])
    api_key_for_request = clean_str(config.get("api_key_for_request"))
    if api_key_for_request:
        env["LLM_API_KEY"] = api_key_for_request
    env["LLM_THINKING"] = "on" if summary["thinking_enabled"] else "off"
    env["LLM_THINKING_EFFORT"] = str(summary["thinking_effort"])
    # 系统设置里的超时同样作用于管线各 LLM 阶段；本地大模型通常需要远大于 120 秒。
    env["LLM_TIMEOUT"] = str(summary["timeout"])
    return summary, env


def _direction_precheck_cache_dir() -> Path:
    """方向预检与管线 matching 阶段共用的判定缓存目录，避免重复模型调用。"""
    return _facade()._PROJECT_ROOT / "matching_reports" / ".semantic-cache"


def _evidence_card_dir() -> Path:
    return _facade()._PROJECT_ROOT / "evidence_cards"


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return _facade()._PROJECT_ROOT / path
