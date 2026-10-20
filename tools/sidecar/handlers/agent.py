"""Agent run / REVIEW RPC handlers with real implementation."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from tools.infra.export.pdf_exporter import markdown_to_pdf, pdf_page_count
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.sidecar.handlers.resume import read_generation_trace


def _find_project_root(start: Path) -> Path:
    for parent in start.parents:
        if (parent / "tools" / "run_pipeline.py").exists():
            return parent
    return start.parents[3] if len(start.parents) > 3 else start.parent


_PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
_AGENT_RUN_DIR = _PROJECT_ROOT / "outputs" / "agent_runs"
_QUICK_RUN_DIR = _PROJECT_ROOT / "outputs" / "quick_runs"
_REVIEW_QUEUE_DIR = _PROJECT_ROOT / "outputs" / "review_queue"


def _utcnow_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _ensure_queue_dir() -> None:
    _REVIEW_QUEUE_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_agent_run_dir() -> None:
    _AGENT_RUN_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_quick_run_dir() -> None:
    _QUICK_RUN_DIR.mkdir(parents=True, exist_ok=True)


def _build_agent_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"ar_{timestamp}"


def _build_quick_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"qr_{timestamp}"


def _validate_run_resource_id(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    normalized = value.strip()
    if "/" in normalized or "\\" in normalized or normalized.startswith("."):
        raise ValueError(f"{name} is invalid")
    return normalized


def _get_agent_run_file(run_id: str) -> Path:
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', run_id):
        raise ValueError('invalid_review_run_id')
    _ensure_agent_run_dir()
    return _AGENT_RUN_DIR / f"{run_id}.json"


def _get_quick_run_file(run_id: str) -> Path:
    _ensure_quick_run_dir()
    return _QUICK_RUN_DIR / f"{run_id}.json"


def _evidence_card_dir() -> Path:
    return _PROJECT_ROOT / "evidence_cards"


def _load_agent_run(run_id: str) -> dict[str, Any]:
    run_file = _get_agent_run_file(run_id)
    if not run_file.exists():
        raise KeyError(f"NOT_FOUND: agent run not found: {run_id}")
    return json.loads(run_file.read_text(encoding="utf-8"))


def _save_agent_run(run_file: Path, payload: dict[str, Any]) -> None:
    run_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_quick_run(run_id: str) -> dict[str, Any]:
    run_file = _get_quick_run_file(run_id)
    if not run_file.exists():
        raise KeyError(f"NOT_FOUND: quick run not found: {run_id}")
    return json.loads(run_file.read_text(encoding="utf-8"))


def _save_quick_run(run_file: Path, payload: dict[str, Any]) -> None:
    run_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _coerce_positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return default
        return parsed if parsed > 0 else default
    return default


def _resolve_project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return _PROJECT_ROOT / path


def _event_to_payload(event: Any) -> dict[str, Any]:
    return {
        "run_id": getattr(event, "run_id", ""),
        "event_type": getattr(event, "event_type", ""),
        "round_index": getattr(event, "round_index", 0),
        "payload": getattr(event, "payload", {}),
        "timestamp": getattr(event, "timestamp", ""),
    }


def _execute_local_dry_run(run_id: str, options: dict[str, Any]) -> dict[str, Any]:
    from tools.config.fragments import PolicyConfig
    from tools.infra.persistence.file_run_store import FileRunStore
    from tools.orchestration.agent_loop import AgentLoop

    max_rounds = _coerce_positive_int(options.get("max_rounds"), 1)
    store = FileRunStore(base_dir=str(_AGENT_RUN_DIR))
    policy = PolicyConfig(
        n_pass_required=1,
        matching_threshold=0.6,
        evaluation_threshold=0.6,
        max_rounds=max_rounds,
        gate_mode="simulate",
        delivery_mode="auto",
        batch_review=False,
        excluded_companies=(),
        excluded_legal_entities=(),
        max_deliveries=0,
    )
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        result = AgentLoop(
            policy=policy,
            run_id=run_id,
            dry_run=True,
            run_store=store,
        ).run()
    events = [_event_to_payload(event) for event in store.load_events(run_id)]

    return {
        "status": result.status,
        "round": result.rounds_completed,
        "events": events,
        "stdout": stdout_buffer.getvalue()[-4000:],
        "stderr": stderr_buffer.getvalue()[-4000:],
    }


def _read_domain_job_profile(job_profile_id: str) -> Any:
    from tools.domain.models import JobProfile
    from tools.infra.persistence.job_lead_binding import reviewed_official_profile

    profile_path = _PROJECT_ROOT / "job_profiles" / f"{job_profile_id}.yaml"
    if not profile_path.exists():
        raise ValueError(f"job_profile_not_found: {job_profile_id}")
    doc = parse_simple_yaml(profile_path.read_text(encoding="utf-8"))
    status = doc["scalars"].get("status", "").strip()
    if status and status != "active":
        raise ValueError(f"job_profile_not_active: {job_profile_id}")
    if doc["scalars"].get("source") == "liepin_official":
        lead_id = doc["scalars"].get("job_lead_id", "")
        if not lead_id or "/" in lead_id or "\\" in lead_id:
            raise ValueError("job_profile_review_required")
        lead_path = _PROJECT_ROOT / "job_leads" / f"{lead_id}.yaml"
        if not lead_path.is_file():
            raise ValueError("job_profile_review_required")
        lead = parse_simple_yaml(lead_path.read_text())["scalars"]
        if lead.get("job_profile_id") != job_profile_id or not reviewed_official_profile(lead, _PROJECT_ROOT / "job_profiles"):
            raise ValueError("job_profile_review_required")
    return JobProfile(
        id=job_profile_id,
        title=doc["scalars"].get("target_role", job_profile_id),
        keywords=tuple(doc["lists"].get("keywords", [])),
        level=doc["scalars"].get("seniority", ""),
        tone=doc["scalars"].get("tone", ""),
        must_have=tuple(doc["lists"].get("must_have", [])),
        nice_to_have=tuple(doc["lists"].get("nice_to_have", [])),
    )


def _domain_evidence_cards(options: dict[str, Any]) -> tuple[Any, ...]:
    from tools.domain.models import EvidenceCard

    requested_ids = options.get("evidence_ids")
    allowed_ids = {
        str(item).strip()
        for item in requested_ids
        if str(item).strip()
    } if isinstance(requested_ids, list) else set()
    cards: list[Any] = []
    evidence_dir = _evidence_card_dir()
    if not evidence_dir.exists():
        raise ValueError("missing_eligible_evidence_cards")
    for path in sorted(evidence_dir.glob("*.yaml")):
        if allowed_ids and path.stem not in allowed_ids:
            continue
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if not _is_saved_eligible_evidence(doc):
            continue
        cards.append(
            EvidenceCard(
                id=doc["scalars"].get("id", path.stem),
                title=doc["scalars"].get("title", path.stem),
                raw_source=doc["scalars"].get("raw_source", ""),
                results=tuple(doc["lists"].get("results", [])),
                artifacts=tuple(doc["lists"].get("artifacts", [])),
                tags=tuple(doc["lists"].get("tags", [])),
                stack=tuple(doc["lists"].get("stack", [])),
                period=doc["scalars"].get("time_range", ""),
                context=doc["scalars"].get("context", ""),
            )
        )
    if not cards:
        raise ValueError("missing_eligible_evidence_cards")
    return tuple(cards)


def _job_lead_candidates(options: dict[str, Any]) -> tuple[Any, ...]:
    from tools.domain.value_objects import Candidate
    from tools.infra.persistence.job_lead_binding import reviewed_official_profile

    selected_ids_raw = options.get("candidate_ids")
    selected_ids = [
        str(item).strip()
        for item in selected_ids_raw
        if str(item).strip()
    ] if isinstance(selected_ids_raw, list) else []
    excluded_ids_raw = options.get("excluded_candidate_ids")
    excluded_ids = {
        str(item).strip()
        for item in excluded_ids_raw
        if str(item).strip()
    } if isinstance(excluded_ids_raw, list) else set()
    pinned_ids_raw = options.get("pinned_candidate_ids")
    pinned_ids = [
        str(item).strip()
        for item in pinned_ids_raw
        if str(item).strip()
    ] if isinstance(pinned_ids_raw, list) else []

    lead_dir = _PROJECT_ROOT / "job_leads"
    lead_map: dict[str, Any] = {}
    if lead_dir.exists():
        for path in sorted(lead_dir.glob("*.yaml")):
            try:
                doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            lead_id = doc["scalars"].get("id", path.stem)
            url = doc["scalars"].get("url", doc["scalars"].get("job_url", ""))
            if not url:
                continue
            source_fields = doc["scalars"]
            if source_fields.get("source") == "liepin_official":
                if not reviewed_official_profile(source_fields, _PROJECT_ROOT / "job_profiles"):
                    continue
            profile_id = source_fields.get("job_profile_id", "")
            if profile_id and options.get("job_profile_id") and profile_id != options["job_profile_id"]:
                continue
            lead_map[lead_id] = Candidate(
                candidate_id=lead_id,
                direction=doc["scalars"].get("position", doc["scalars"].get("title", "")),
                company=doc["scalars"].get("company", ""),
                job_url=url,
                confidence=float(doc["scalars"].get("confidence", "0.75") or 0.75),
                source=doc["scalars"].get("source", "job_leads"),
                merged_sources=("job_leads",),
                legal_entity=doc["scalars"].get("legal_entity", ""),
                platform=source_fields.get("platform", ""),
                platform_job_id=source_fields.get("platform_job_id", ""),
                platform_job_type=source_fields.get("platform_job_type", ""),
                job_profile_id=profile_id,
                jd_status=source_fields.get("jd_status", ""),
                source_jd_sha256=source_fields.get("source_jd_sha256", ""),
            )

    ordered_ids = [lead_id for lead_id in pinned_ids + selected_ids if lead_id in lead_map]
    if not ordered_ids and not selected_ids:
        ordered_ids = sorted(lead_map)
    candidates = [
        lead_map[lead_id]
        for lead_id in dict.fromkeys(ordered_ids)
        if lead_id not in excluded_ids
    ]
    max_candidates = _coerce_positive_int(options.get("max_candidates"), 5)
    candidates = candidates[:max_candidates]
    if not candidates:
        raise ValueError("missing_candidate_job_leads")
    return tuple(candidates)


def _execute_guided_batch_run(
    run_id: str,
    job_profile_id: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    from tools.config.composer import Composer
    from tools.config.fragments import PolicyConfig
    from tools.infra.persistence.file_run_store import FileRunStore

    max_rounds = _coerce_positive_int(options.get("max_rounds"), 2)
    from tools.policy.exclusions import load_exclusion_policy, resolve_policy_path
    exclusions = load_exclusion_policy(resolve_policy_path(_PROJECT_ROOT))
    policy = PolicyConfig(
        n_pass_required=1,
        matching_threshold=float(options.get("matching_threshold") or 0.3),
        evaluation_threshold=float(options.get("evaluation_threshold") or 0.3),
        max_rounds=max_rounds,
        gate_mode="strict",
        delivery_mode="manual",
        batch_review=True,
        excluded_companies=exclusions.company_rules,
        excluded_legal_entities=exclusions.legal_entities,
        max_deliveries=0,
    )
    job_profile = _read_domain_job_profile(job_profile_id)
    evidence_cards = _domain_evidence_cards(options)
    candidates = _job_lead_candidates({**options, "job_profile_id": job_profile_id})
    store = FileRunStore(base_dir=str(_AGENT_RUN_DIR))
    composer = Composer(policy=policy)
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    cwd = Path.cwd()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            os.chdir(_PROJECT_ROOT)
            result = composer.build_agent_loop(
                run_id=run_id,
                dry_run=True,
                run_store=store,
                evidence_cards=evidence_cards,
                job_profile=job_profile,
                candidates=candidates,
            ).run()
        finally:
            os.chdir(cwd)

    events = [_event_to_payload(event) for event in store.load_events(run_id)]
    gate_checks = [
        event
        for event in events
        if event.get("event_type") == "GATE"
    ]
    queue_path = _PROJECT_ROOT / "outputs" / "review_queue" / f"{run_id}.json"
    review_queue: dict[str, Any] = {}
    if queue_path.exists():
        review_queue = json.loads(queue_path.read_text(encoding="utf-8"))
    delivery_events = [
        event for event in events if event.get("event_type") == "DELIVER"
    ]
    policy_limits = {
        "max_candidates": _coerce_positive_int(options.get("max_candidates"), 5),
        "max_passed_candidates": _coerce_positive_int(
            options.get("max_passed_candidates"), 3
        ),
        "max_generated_resumes": _coerce_positive_int(
            options.get("max_generated_resumes"), 3
        ),
        "submit_enabled": False,
    }
    preflight_confirmation = {
        "confirmed_by_user": bool(options.get("preflight_confirmed")),
        "confirmed_no_real_submit": bool(options.get("confirmed_no_real_submit")),
        "confirmed_at": _utcnow_iso() if options.get("preflight_confirmed") else "",
        "confirmed_policy_limits": policy_limits,
    }
    selected_candidate_ids = [candidate.candidate_id for candidate in candidates]
    return {
        "status": result.status,
        "round": result.rounds_completed,
        "events": events,
        "gate_checks": gate_checks,
        "review_queue": {
            "path": str(queue_path.relative_to(_PROJECT_ROOT)),
            "candidate_count": len(review_queue.get("candidates", [])),
            "pending_count": len(
                [
                    candidate
                    for candidate in review_queue.get("candidates", [])
                    if candidate.get("status") == "pending"
                ]
            ),
        },
        "selected_candidate_ids": selected_candidate_ids,
        "policy_limits": policy_limits,
        "preflight_confirmation": preflight_confirmation,
        "delivery_plan": {
            "submit_enabled": False,
            "submit_status": "blocked_pending_manual_review",
            "external_submission_attempted": False,
            "delivery_events": len(delivery_events),
        },
        "run_log": str(
            Path("outputs") / "agent_runs" / run_id / "run_log.json"
        ),
        "stdout": stdout_buffer.getvalue()[-4000:],
        "stderr": stderr_buffer.getvalue()[-4000:],
    }


def _quick_run_material_sources() -> list[dict[str, Any]]:
    materials_dir = _PROJECT_ROOT / "materials"
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
    summary_path = _PROJECT_ROOT / "outputs" / "agent_runs" / run_id / "summary.json"
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
    target_dir = _PROJECT_ROOT / evidence_dir
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
    pdf_path = _PROJECT_ROOT / "outputs" / "quick_runs" / run_id / "exports" / pdf_filename_for_resume(resume_md, _PROJECT_ROOT / 'outputs', readable=True)
    trace_path=resume_md.with_suffix('.trace.json')
    source_hash=hashlib.sha256(resume_md.read_bytes()).hexdigest()
    trace_hash=hashlib.sha256(trace_path.read_bytes()).hexdigest() if trace_path.is_file() else ''
    markdown_to_pdf(resume_md, pdf_path)
    if (hashlib.sha256(resume_md.read_bytes()).hexdigest()!=source_hash
            or (hashlib.sha256(trace_path.read_bytes()).hexdigest() if trace_path.is_file() else '')!=trace_hash):
        raise RuntimeError('resume_pdf_source_changed')
    artifacts['resume_pdf_source_sha256']=source_hash
    artifacts['resume_pdf_trace_sha256']=trace_hash
    return str(pdf_path.relative_to(_PROJECT_ROOT))


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
                from tools.infra.semantic_matching import load_direction_report
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
                "pages": pdf_page_count(pdf_path),
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


def handle_quick_start(params: dict[str, Any]) -> dict[str, Any]:
    """Run the single-pass pipeline from the desktop Quick Run page."""
    correlation_id = params["meta"]["correlation_id"]
    job_profile_id = _validate_run_resource_id(
        "job_profile_id", params.get("job_profile_id")
    )
    evidence_id = params.get("evidence_id")
    if evidence_id is not None:
        _validate_run_resource_id("evidence_id", evidence_id)
    options = params.get("options", {})
    if not isinstance(options, dict):
        raise ValueError("options must be an object")

    raw_path, job_profile_path, material_context = _quick_run_paths(job_profile_id, options)
    job_profile_context = _load_job_profile_context(job_profile_id, job_profile_path)
    selected_evidence_cards = _selected_evidence_cards(
        str(evidence_id).strip() if evidence_id is not None else None, options
    )
    selected_evidence_card_ids = [
        str(card["evidence_id"]) for card in selected_evidence_cards
    ]
    resume_positioning = _quick_run_positioning(options)
    llm_config_summary, llm_env = _persisted_llm_runtime_context()
    run_id = _build_quick_run_id()
    evidence_dir = Path("outputs") / "quick_runs" / run_id / "evidence_cards"
    _stage_selected_evidence(selected_evidence_cards, evidence_dir)
    started_at = _utcnow_iso()
    pipeline_script = _PROJECT_ROOT / "tools" / "run_pipeline.py"
    command = [
        sys.executable,
        str(pipeline_script),
        "--raw",
        str(raw_path),
        "--job-profile",
        str(job_profile_path),
        "--evidence-dir",
        str(evidence_dir),
        "--run-id",
        run_id,
        "--skip-evidence-extraction",
        "--personal-profile",
        str(_PROJECT_ROOT / "personal_profile.yaml"),
        "--resume-positioning",
        resume_positioning["mode"],
        "--custom-positioning",
        resume_positioning["custom"],
    ]
    timeout_seconds = _coerce_positive_int(options.get("timeout_seconds"), 120)
    if options.get("use_llm") is True:
        command.append("--use-llm")
    if options.get("require_llm") is True:
        command.append("--require-llm")

    status = "queued"
    exit_code: int | None = None
    stdout = ""
    stderr = ""
    finished_at = ""

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(_PROJECT_ROOT),
            env={**os.environ, **llm_env},
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
        if completed.returncode == 0:
            status = "DONE"
        elif completed.returncode == 2:
            status = "SKIPPED"
        else:
            status = "FAILED"
        finished_at = _utcnow_iso()
    except subprocess.TimeoutExpired as exc:
        status = "TIMEOUT"
        exit_code = None
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        finished_at = _utcnow_iso()

    payload = {
        "run": {
            "run_id": run_id,
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "job_profile_id": job_profile_id,
            "evidence_id": evidence_id or "",
            "job_profile": job_profile_context,
            "selected_evidence_card_ids": selected_evidence_card_ids,
            "raw_path": str(raw_path),
            "job_profile_path": str(job_profile_path),
            "material_source": material_context,
            "evidence_dir": str(evidence_dir),
            "resume_positioning": resume_positioning,
            "command": command,
            "exit_code": exit_code,
            "options": options,
            "llm_config_summary": llm_config_summary,
        },
        "stdout": stdout[-4000:],
        "stderr": stderr[-4000:],
    }
    details = _quick_run_result_details(
        run_id,
        stdout,
        stderr,
        selected_evidence_card_ids=selected_evidence_card_ids,
        resume_positioning=resume_positioning,
    )
    payload.update(details)
    _save_quick_run(_get_quick_run_file(run_id), payload)

    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "status": status,
        "exit_code": exit_code,
        "run_record": str(Path("outputs") / "agent_runs" / run_id / "run_log.json"),
        "summary": str(Path("outputs") / "agent_runs" / run_id / "summary.json"),
        "llm_config_summary": llm_config_summary,
        "material_source": material_context,
        "job_profile": job_profile_context,
        "selected_evidence_card_ids": selected_evidence_card_ids,
        **details,
    }


def handle_quick_cancel(params: dict[str, Any]) -> dict[str, Any]:
    """Best-effort cancellation marker for Quick Run records."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = _validate_run_resource_id("run_id", params.get("run_id"))
    run_file = _get_quick_run_file(run_id)
    payload = _load_quick_run(run_id)
    run_payload = payload.setdefault("run", {})
    if run_payload.get("status") not in {"DONE", "FAILED", "SKIPPED", "TIMEOUT"}:
        run_payload["status"] = "stopped"
    run_payload["cancel_requested_at"] = _utcnow_iso()
    _save_quick_run(run_file, payload)

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": True,
    }


def _get_queue_file(run_id: str | None = None) -> Path:
    _ensure_queue_dir()
    if run_id is None:
        # Use the most recent queue file or create a default
        files = sorted(_REVIEW_QUEUE_DIR.glob("*.json"), key=lambda path: (path.stat().st_mtime_ns, path.name))
        if files:
            return files[-1]
        return _REVIEW_QUEUE_DIR / "default.json"
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', run_id):
        raise ValueError('invalid_review_run_id')
    return _REVIEW_QUEUE_DIR / f"{run_id}.json"


def _load_queue(queue_file: Path) -> dict[str, Any]:
    if not queue_file.exists():
        return {
            "run_id": queue_file.stem,
            "candidates": [],
            "created_at": _utcnow_iso(),
        }
    return json.loads(queue_file.read_text(encoding="utf-8"))


def _save_queue(queue_file: Path, queue: dict[str, Any]) -> None:
    from tools.infra.persistence.review_queue import atomic_write_json
    atomic_write_json(queue_file, queue)


def handle_prepare_liepin_default(params: dict[str, Any]) -> dict[str, Any]:
    """从已审核岗位准备默认简历审批；此入口只有读取操作，绝不发送。"""
    from tools.sidecar.handlers import jobs
    from tools.channels.base import DeliveryRequest
    from tools.infra.liepin_job_detail import fetch_liepin_job_detail, LiepinJobDetailError
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    from tools.infra.persistence.job_lead_binding import reviewed_official_profile
    from tools.infra.persistence.review_queue import atomic_write_json, locked_review_queue
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    from tools.orchestration.approved_delivery import _job_key
    from tools.policy.exclusions import load_exclusion_policy, match_exclusion, resolve_policy_path

    base = {'meta': {'correlation_id': params['meta']['correlation_id']}, 'status': 'blocked'}
    lead_id = params.get('job_lead_id')
    if (set(params) - {'meta', 'job_lead_id'} or not isinstance(lead_id, str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', lead_id)):
        return {**base, 'code': 'INVALID_INPUT'}
    try:
        binding = jobs._bound_lead(lead_id)
        if not binding:
            return {**base, 'code': 'JOB_REVIEW_REQUIRED'}
        lead = binding[1]
        if (lead.get('source') != 'liepin_official' or lead.get('platform') != 'liepin'
                or not reviewed_official_profile(lead, jobs._JOB_PROFILE_DIR)):
            return {**base, 'code': 'JOB_REVIEW_REQUIRED'}
        if match_exclusion(lead.get('company', ''), lead.get('legal_entity', ''),
                           load_exclusion_policy(resolve_policy_path(_PROJECT_ROOT))):
            return {**base, 'code': 'EXCLUDED_TARGET'}
        request = DeliveryRequest('', lead_id, 'liepin', '', lead['url'], False, lead)
        store = DeliveryAttemptStore(_PROJECT_ROOT / 'outputs/submissions/delivery_attempts.sqlite3')
        if store.has_attempt(_job_key(request)):
            return {**base, 'code': 'ALREADY_ATTEMPTED'}
        batch = store.active_batch()
        if batch and batch.get('allowed_delivery_kind') not in (None, 'platform_default'):
            return {**base, 'code': 'BATCH_ROUTE_NOT_AUTHORIZED'}
        if batch and batch['remaining'] == 0:
            return {**base, 'code': 'BATCH_LIMIT_REACHED'}
        if batch and batch['unresolved']:
            return {**base, 'code': 'BATCH_UNRESOLVED'}
        from tools.infra.resume_content import current_career,content_body_issues
        career=current_career(_PROJECT_ROOT)
        detail = fetch_liepin_job_detail(lead['url'], lead['platform_job_id'])
        if detail['source_jd_sha256'] != lead['source_jd_sha256']:
            return {**base, 'code': 'JOB_REVIEW_REQUIRED'}
        resume = jobs.liepin_readonly.read_resume()
        if resume['status'] != 'pass':
            return {**base, 'code': 'RESUME_UNAVAILABLE'}
        content = resume.get('resume_text', '')
        if not isinstance(content, str) or not content.strip():
            return {**base, 'code': 'RESUME_UNAVAILABLE'}
        if content_body_issues(career,content):return {**base,'code':'RESUME_CONTENT_INCOMPLETE'}
        digest = hashlib.sha256(content.encode()).hexdigest()
        candidate = {key: lead.get(key, '') for key in (
            'company', 'position', 'platform', 'platform_job_id', 'platform_job_type',
            'job_profile_id', 'jd_status', 'source_jd_sha256', 'source', 'legal_entity')}
        candidate.update(job_lead_id=lead_id, job_url=lead['url'], delivery_kind='platform_default',
                         career_revision=career['revision'],content_schema_version=1,
                         platform_resume_sha256=digest, resume_version='platform-default-' + digest[:12],
                         matching_score=None, evaluation_score=None, round_index=0, status='pending',
                         created_at=_utcnow_iso())
        snapshots = ReviewSnapshotStore(_AGENT_RUN_DIR)
        # 多窗口同时准备时只创建一个任务；审批与真实发送仍使用各自原有锁和占位。
        with locked_review_queue(_REVIEW_QUEUE_DIR / '.prepare-liepin'):
            if store.has_attempt(_job_key(request)):
                return {**base, 'code': 'ALREADY_ATTEMPTED'}
            for path in _REVIEW_QUEUE_DIR.glob('*.json'):
                with locked_review_queue(path):
                    queue = _load_queue(path)
                    for existing in queue.get('candidates', []):
                        if (existing.get('status') != 'pending' or existing.get('delivery')
                                or any(existing.get(key) != candidate.get(key) for key in candidate
                                       if key not in {'created_at', 'matching_score', 'evaluation_score', 'round_index'})):
                            continue
                        try:
                            sealed = snapshots.load(path.stem, existing)
                            run = _load_agent_run(path.stem)['run']
                        except (ValueError, KeyError, OSError):
                            continue
                        if not sealed['dry_run'] and run.get('status') == 'REVIEW_PENDING':
                            return {**base, 'status': 'ready', 'code': 'OK', 'run_id': path.stem,
                                    'job_profile_id': lead['job_profile_id'], 'reused': True}
            run_id = _build_agent_run_id()
            candidate['snapshot'] = snapshots.create(run_id, candidate, content, dry_run=False)
            queue = {'run_id': run_id, 'candidates': [candidate], 'created_at': _utcnow_iso()}
            payload = {'run': {'run_id': run_id, 'status': 'REVIEW_PENDING', 'round': 0,
                       'started_at': _utcnow_iso(), 'job_profile_id': lead['job_profile_id'],
                       'options': {'delivery_kind': 'platform_default'}, 'review_queue': queue,
                       'deliveries_completed': 0, 'app_verified_deliveries': 0, 'externally_confirmed_deliveries': 0},
                       'events': [], 'gate_checks': [], 'next_event_cursor': None}
            atomic_write_json(_get_agent_run_file(run_id), payload)
            _save_queue(_get_queue_file(run_id), queue)
        return {**base, 'status': 'ready', 'code': 'OK', 'run_id': run_id,
                'job_profile_id': lead['job_profile_id'], 'reused': False}
    except LiepinJobDetailError:
        return {**base, 'code': 'JOB_DETAIL_UNAVAILABLE'}
    except ValueError as error:
        return {**base,'code':'CAREER_PROFILE_UNCONFIRMED' if str(error)=='career_profile_unconfirmed' else 'PREPARATION_UNAVAILABLE'}
    except (OSError, KeyError):
        return {**base, 'code': 'PREPARATION_UNAVAILABLE'}


def handle_agent_start(params: dict[str, Any]) -> dict[str, Any]:
    """Create a desktop-visible Agent Run control record."""
    correlation_id = params["meta"]["correlation_id"]
    job_profile_id = params.get("job_profile_id")
    options = params.get("options", {})

    if not isinstance(job_profile_id, str) or not job_profile_id:
        raise ValueError("job_profile_id is required")
    if not isinstance(options, dict):
        raise ValueError("options must be an object")

    llm_config_summary, _llm_env = _persisted_llm_runtime_context()
    if options.get("submit_enabled") is True:
        raise ValueError("submit_enable_blocked_for_case")
    if options.get("execute_guided_batch") is True:
        if not llm_config_summary.get("provider") or not llm_config_summary.get("model"):
            raise ValueError("missing_provider_config")
        if not options.get("preflight_confirmed"):
            raise ValueError("preflight_confirmation_required")
        if not options.get("confirmed_no_real_submit"):
            raise ValueError("no_real_submit_confirmation_required")
    run_id = _build_agent_run_id()
    started_at = _utcnow_iso()
    run_payload = {
        "run": {
            "run_id": run_id,
            "status": "queued",
            "round": 0,
            "started_at": started_at,
            "job_profile_id": job_profile_id,
            "options": options,
            "llm_config_summary": llm_config_summary,
        },
        "gate_checks": [],
        "events": [],
        "next_event_cursor": None,
    }

    if options.get("execute_guided_batch") is True:
        execution = _execute_guided_batch_run(run_id, job_profile_id, options)
        run_payload["run"]["status"] = execution["status"]
        run_payload["run"]["round"] = execution["round"]
        run_payload["run"]["completed_at"] = _utcnow_iso()
        run_payload["run"]["guided_batch"] = True
        run_payload["run"]["selected_candidate_ids"] = execution[
            "selected_candidate_ids"
        ]
        run_payload["run"]["policy_limits"] = execution["policy_limits"]
        run_payload["run"]["preflight_confirmation"] = execution[
            "preflight_confirmation"
        ]
        run_payload["run"]["delivery_plan"] = execution["delivery_plan"]
        run_payload["run"]["review_queue"] = execution["review_queue"]
        run_payload["run"]["run_log"] = execution["run_log"]
        run_payload["events"] = execution["events"]
        run_payload["gate_checks"] = execution["gate_checks"]
        run_payload["stdout"] = execution.get("stdout", "")
        run_payload["stderr"] = execution.get("stderr", "")
    elif options.get("execute_dry_run") is True:
        execution = _execute_local_dry_run(run_id, options)
        run_payload["run"]["status"] = execution["status"]
        run_payload["run"]["round"] = execution["round"]
        run_payload["run"]["completed_at"] = _utcnow_iso()
        run_payload["events"] = execution["events"]
        run_payload["stdout"] = execution.get("stdout", "")
        run_payload["stderr"] = execution.get("stderr", "")

    _save_agent_run(_get_agent_run_file(run_id), run_payload)

    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "status": run_payload["run"]["status"],
        "llm_config_summary": llm_config_summary,
        "guided_batch": bool(run_payload["run"].get("guided_batch")),
        "review_queue": run_payload["run"].get("review_queue"),
        "delivery_plan": run_payload["run"].get("delivery_plan"),
    }


def handle_agent_get(params: dict[str, Any]) -> dict[str, Any]:
    """Return the persisted Agent Run control record."""
    from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is required")

    payload = _load_agent_run(run_id)
    events = list(payload.get("events", []))
    event_cursor = _coerce_positive_int(params.get("event_cursor"), 0)
    event_limit = _coerce_positive_int(params.get("event_limit"), 50)
    visible_events = events[event_cursor : event_cursor + event_limit]
    next_cursor_index = event_cursor + len(visible_events)
    next_event_cursor = (
        str(next_cursor_index) if next_cursor_index < len(events) else None
    )
    queue = _load_queue(_get_queue_file(run_id))
    # 每日项在原 daily 历史展示所属批次；不能借用当前手动验证批次的成功计数。
    delivery_batch = None if queue.get('daily_cycle') else DeliveryAttemptStore(
        _AGENT_RUN_DIR.parent / 'submissions/delivery_attempts.sqlite3').active_batch()

    return {
        "meta": {"correlation_id": correlation_id},
        "run": _delivery_summary(payload.get("run", {})),
        "delivery_batch": delivery_batch,
        "gate_checks": payload.get("gate_checks", []),
        "events": visible_events,
        "next_event_cursor": next_event_cursor,
    }


def handle_agent_stop(params: dict[str, Any]) -> dict[str, Any]:
    """Mark a desktop-visible Agent Run as stopped."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")

    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is required")

    run_file = _get_agent_run_file(run_id)
    payload = _load_agent_run(run_id)
    run_payload = payload.setdefault("run", {})
    run_payload["status"] = "stopped"
    run_payload["stopped_at"] = _utcnow_iso()
    _save_agent_run(run_file, payload)

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": True,
    }


def handle_get_pending_review(params: dict[str, Any]) -> dict[str, Any]:
    """Return pending REVIEW candidates for the active run."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")

    queue_file = _get_queue_file(run_id)
    queue = _load_queue(queue_file)

    # Filter only pending candidates
    pending = [c for c in queue.get("candidates", []) if c.get("status") == "pending"
               or (c.get('status') == 'approved' and 'delivery' not in c)]
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    for candidate in pending:
        try:
            snapshot = ReviewSnapshotStore(_AGENT_RUN_DIR).load(queue_file.stem, candidate)
            candidate.update(snapshot_status='ready', resume_preview=snapshot['resume_markdown'])
        except ValueError:
            candidate.update(snapshot_status='invalid', resume_preview='')

    return {
        "meta": {"correlation_id": correlation_id},
        "candidates": pending,
        "run_id": queue_file.stem,
        "native_pdf_quick_run_id": queue.get("quick_run_id"),
        "delivery_results": [_delivery_confirmation(c['delivery']) for c in queue.get('candidates', []) if 'delivery' in c],
    }


def handle_submit_review(params: dict[str, Any]) -> dict[str, Any]:
    """持久化审批决定，从对应快照恢复执行，不重新生成简历。"""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id")
    decisions = params.get("decisions", [])

    if not isinstance(decisions, list) or not decisions or not isinstance(run_id, str) or not run_id:
        raise ValueError("decisions must be a list")

    queue_file = _get_queue_file(run_id)
    from tools.infra.persistence.review_queue import locked_review_queue
    from tools.infra.persistence.review_snapshot import ReviewSnapshotStore
    from tools.orchestration.approved_delivery import resume_approved_candidate
    actions = {'approve': 'approved', 'reject': 'rejected', 'skip': 'skipped', 'skip_all': 'skipped'}
    with locked_review_queue(queue_file):
        queue = _load_queue(queue_file)
        if queue.get('run_id') != run_id:
            raise ValueError('review_run_mismatch')
        # 原生 PDF 的批准依据与平台副作用由原上传/每日流程管理，不能混用通用投递。
        if queue.get('quick_run_id'):
            raise ValueError('native_pdf_review_required')
        candidates = queue.get('candidates', [])
        unresolved = any(c.get('delivery', {}).get('status') == 'unknown' for c in candidates)
        if unresolved and any(isinstance(d, dict) and d.get('action') == 'approve' for d in decisions):
            raise ValueError('review_batch_has_unresolved_delivery')
        lookup = {c['job_lead_id']: c for c in candidates}
        if len(lookup) != len(candidates):
            raise ValueError('duplicate_review_candidate')
        selected = set()
        snapshots = ReviewSnapshotStore(_AGENT_RUN_DIR)
        for decision in decisions:
            if not isinstance(decision, dict):
                raise ValueError('invalid_review_decision')
            lead_id, action = decision.get('job_lead_id'), decision.get('action')
            if (not isinstance(lead_id, str) or lead_id not in lookup or lead_id in selected
                    or not isinstance(action, str) or action not in actions):
                raise ValueError('invalid_review_decision')
            selected.add(lead_id)
            candidate = lookup[lead_id]
            if candidate.get('status') not in {'pending', actions[action]}:
                raise ValueError('review_decision_already_final')
            if action == 'approve':
                snapshots.load(run_id, candidate)
                run_file = _AGENT_RUN_DIR / f'{run_id}.json'
                if run_file.exists() and _load_agent_run(run_id).get('run', {}).get('status') == 'stopped':
                    raise ValueError('review_run_stopped')
        accepted_count = 0
        for decision in decisions:
            candidate = lookup[decision['job_lead_id']]
            if candidate['status'] != 'pending':
                continue
            candidate.update(status=actions[decision['action']],
                             decided_by=decision.get('decided_by', 'user'), decided_at=_utcnow_iso())
            if 'note' in decision:
                candidate['note'] = decision['note']
            accepted_count += int(decision['action'] == 'approve')
        # 批准先落盘；中断后同一批准可恢复，真实调用由持久化占位防重。
        _save_queue(queue_file, queue)
        for decision in decisions:
            candidate = lookup[decision['job_lead_id']]
            if candidate['status'] == 'approved' and 'delivery' not in candidate:
                try:
                    candidate['delivery'] = resume_approved_candidate(run_id, candidate, _AGENT_RUN_DIR)
                except Exception:
                    candidate['delivery'] = {'job_lead_id': candidate['job_lead_id'], 'success': False,
                                             'submission_id': '', 'status': 'blocked', 'code': 'review_execution_failed'}
                _save_queue(queue_file, queue)
                if candidate['delivery']['status'] == 'unknown':
                    break
        results = [c['delivery'] for c in candidates if 'delivery' in c]
        _sync_review_run(run_id, queue, results)

    return {
        "meta": {"correlation_id": correlation_id},
        "accepted": accepted_count,
        "delivery_results": [_delivery_confirmation(result) for result in results],
    }


def handle_recheck_receipt(params: dict[str, Any]) -> dict[str, Any]:
    """App 重新核验已有 API 回执；没有发送或网络操作。"""
    from tools.infra.liepin_default_delivery import recheck_api_receipt
    from tools.infra.persistence.review_queue import locked_review_queue, atomic_write_json
    base = {'meta': {'correlation_id': params['meta']['correlation_id']}, 'status':'blocked'}
    run_id, lead_id = params.get('run_id'), params.get('job_lead_id')
    if (set(params) - {'meta','run_id','job_lead_id'} or
            not all(isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', v) for v in (run_id, lead_id))):
        return {**base, 'code':'INVALID_INPUT'}
    with locked_review_queue(_get_queue_file(run_id)):
        queue = _load_queue(_get_queue_file(run_id))
        candidate = next((c for c in queue['candidates'] if c['job_lead_id'] == lead_id), None)
        if not candidate or queue.get('run_id') != run_id:
            return {**base, 'code':'RECEIPT_EVIDENCE_UNAVAILABLE'}
        if (candidate.get('delivery', {}).get('status') == 'unknown'
                or candidate.get('delivery', {}).get('receipt_source') == 'website_history'):
            try:
                result = recheck_api_receipt(_PROJECT_ROOT, run_id, candidate)
            except (OSError, ValueError, KeyError, TypeError):
                return {**base, 'code':'RECEIPT_EVIDENCE_UNAVAILABLE'}
            changed = result != candidate['delivery']
            candidate['delivery'] = result
            _save_queue(_get_queue_file(run_id), queue)
            if changed:
                payload = _load_agent_run(run_id)
                payload.setdefault('events', []).append({'event_type':'DELIVER', 'round_index':candidate.get('round_index', 0),
                    'timestamp':_utcnow_iso(), 'payload':{**result, 'source':'api_receipt_recheck'}})
                atomic_write_json(_get_agent_run_file(run_id), payload)
        results = [c['delivery'] for c in queue['candidates'] if 'delivery' in c]
        _sync_review_run(run_id, queue, results)
    return {**base, 'status':'ready', 'code':'RECEIPT_RECHECKED',
            'delivery_results':[_delivery_confirmation(r) for r in results]}


def _delivery_confirmation(result: dict) -> dict:
    """保留实际投递事实，单独标记其确认来源；历史记录不自动升级。"""
    result = {**result, 'app_verified': False}
    if result.get('success'):
        if result.get('receipt_source') == 'website_history':
            result.update(status='externally_confirmed', code='external_observation_confirmed')
        elif result.get('receipt_source') in {'app_api', 'app_browser'} and result.get('submission_id'):
            result['app_verified'] = True
        else:
            result.update(status='unknown', code='receipt_source_unverified')
    return result


def _delivery_summary(run: dict) -> dict:
    run = dict(run)
    if 'delivery_results' not in run:
        return run
    results = [_delivery_confirmation(r) for r in run['delivery_results']]
    run.update(delivery_results=results, deliveries_completed=sum(bool(r.get('success')) for r in results),
               app_verified_deliveries=sum(r['app_verified'] for r in results),
               externally_confirmed_deliveries=sum(r.get('status') == 'externally_confirmed' for r in results))
    if run.get('status') not in {'REVIEW_PENDING', 'stopped'}:
        if any(r.get('status') in {'blocked', 'unknown'} for r in results):
            run['status'] = 'DELIVERY_BLOCKED'
        elif run['externally_confirmed_deliveries']:
            run['status'] = 'EXTERNAL_CONFIRMATION_ONLY'
    return run


def _sync_review_run(run_id: str, queue: dict, results: list[dict]) -> None:
    """审批队列为恢复来源，同步 App 已有运行记录与事件流。"""
    from tools.infra.persistence.review_queue import atomic_write_json
    run_file = _AGENT_RUN_DIR / f'{run_id}.json'
    if not run_file.exists():
        return
    payload = _load_agent_run(run_id)
    run = payload.setdefault('run', {})
    run['review_queue'] = queue
    run['delivery_results'] = results
    run['deliveries_completed'] = sum(bool(r['success']) for r in results)
    if any(c.get('status') == 'pending' for c in queue['candidates']):
        run['status'] = 'REVIEW_PENDING'
    elif any(r['status'] in {'blocked', 'unknown'} for r in results):
        run['status'] = 'DELIVERY_BLOCKED'
    elif results and all(r['status'] == 'checked' for r in results):
        run['status'] = 'REVIEWED_CHECK_ONLY'
    else:
        run['status'] = 'DONE'
    run.update(_delivery_summary(run))
    events = payload.setdefault('events', [])
    for result in results:
        event_key = 'review-delivery:' + result['job_lead_id']
        if not any(e.get('payload', {}).get('event_key') == event_key for e in events):
            round_index = next((c.get('round_index', 0) for c in queue['candidates'] if c['job_lead_id'] == result['job_lead_id']), 0)
            events.append({'event_type': 'DELIVER', 'round_index': round_index, 'timestamp': _utcnow_iso(),
                           'payload': {**result, 'dry_run': result['status'] == 'checked', 'event_key': event_key}})
    atomic_write_json(run_file, payload)


def handle_create_review_candidates(params: dict[str, Any]) -> dict[str, Any]:
    """Internal API to create review candidates from a run (called by run_agent)."""
    correlation_id = params["meta"]["correlation_id"]
    run_id = params.get("run_id", "default")
    candidates_data = params.get("candidates", [])

    if not isinstance(candidates_data, list):
        raise ValueError("candidates must be a list")

    queue_file = _get_queue_file(run_id)

    candidates = []
    for data in candidates_data:
        candidate = {
            "job_lead_id": data.get("job_lead_id", ""),
            "company": data.get("company", ""),
            "position": data.get("position", ""),
            "matching_score": data.get("matching_score", 0),
            "evaluation_score": data.get("evaluation_score", 0),
            "round_index": data.get("round_index", 0),
            "resume_version": data.get("resume_version", ""),
            "status": "pending",
            "created_at": _utcnow_iso(),
        }
        if "job_url" in data:
            candidate["job_url"] = data["job_url"]
        candidates.append(candidate)

    queue = {
        "run_id": run_id,
        "candidates": candidates,
        "created_at": _utcnow_iso(),
    }
    from tools.infra.persistence.review_queue import locked_review_queue
    with locked_review_queue(queue_file):
        if queue_file.exists():
            raise ValueError('review_queue_already_exists')
        _save_queue(queue_file, queue)

    return {
        "meta": {"correlation_id": correlation_id},
        "run_id": run_id,
        "created": len(candidates),
    }
