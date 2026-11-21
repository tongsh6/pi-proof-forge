"""岗位画像草稿、读写与线索转换 handler。

从 ``jobs.py`` 拆出；路径常量与测试会 patch 的辅助函数仍从原模块运行时读取。
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, cast
from urllib.parse import urlparse
from uuid import uuid4

from tools.domain.job_lead_state import JD_CAPTURE_KEY, current_jd_capture, invalidate_jd_capture, lead_has_complete_jd
from tools.infra.persistence.job_lead_binding import reviewed_official_profile, same_official_source_url
from tools.infra.llm.task_contract import JOB_PROFILE_DRAFT, REASON_OUTPUT_TRUNCATED
from tools.sidecar.handlers import jobs as _origin
from tools.sidecar.handlers._shared.llm_config import load_llm_config
from tools.sidecar.handlers.jobs import (
    MANUAL_IMPORT_PLATFORMS,
    _bound_lead,
    _clear_lead_profile_reference,
    _find_lead_path,
    _lead_identity,
    _lead_path,
    _preserved_profile_fields,
    _profile_path,
    _read_yaml_doc,
    _running_submission_profile_ids,
    _utcnow_iso,
    _validate_non_empty_string_list,
    _validate_string_list,
    _write_job_lead_file,
    _write_job_profile_file,
    platform_from_url,
)

_JOB_DRAFT_REQUIRED_FIELDS = {
    "target_role",
    "must_have",
    "keywords",
    "jd_summary",
}
_JOB_DRAFT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        **{
            field: {"type": "string", "maxLength": 600 if field == "jd_summary" else 120}
            for field in (
                "target_role", "company", "city", "jd_summary", "business_domain", "tone"
            )
        },
        **{
            field: {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 64 if field == "keywords" else 500}}
            for field in ("must_have", "nice_to_have", "keywords", "seniority_signal")
        },
    },
    "required": sorted(_JOB_DRAFT_REQUIRED_FIELDS),
    "additionalProperties": False,
}


def _missing_items_for_job_draft(draft: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not str(draft.get("target_role", "")).strip():
        missing.append("missing_target_role")
    jd_text = str(draft.get("source_jd", "")).strip()
    if not jd_text or re.fullmatch(r"https?://\S+", jd_text):
        missing.append("missing_jd_text")
    if not draft.get("must_have"):
        missing.append("missing_must_have")
    if not draft.get("keywords"):
        missing.append("missing_keywords")
    if not str(draft.get("jd_summary", "")).strip():
        missing.append("missing_jd_summary")
    return missing


def _build_job_profile_draft(
    parsed: dict[str, Any], jd_text: str, source_url: str
) -> dict[str, Any]:
    # 供应方即使忽略 schema，也不能把重复膨胀的输出发布成可审核稿。
    for field,rule in _JOB_DRAFT_RESPONSE_SCHEMA['properties'].items():
        if field not in parsed:continue
        value=parsed[field]
        if rule['type']=='string':
            valid=isinstance(value,str) and len(value)<=rule['maxLength']
        else:
            valid=isinstance(value,list) and len(value)<=rule['maxItems'] and all(
                isinstance(item,str) and len(item)<=rule['items']['maxLength'] for item in value)
        if not valid:raise ValueError('job_profile_draft_output_limit')
    missing_schema_fields = sorted(_JOB_DRAFT_REQUIRED_FIELDS - set(parsed))
    if missing_schema_fields:
        raise ValueError(
            "job profile draft missing required fields: "
            + ", ".join(missing_schema_fields)
        )

    draft = {
        "target_role": str(parsed.get("target_role", "")).strip(),
        "company": str(parsed.get("company", "")).strip(),
        "source_jd": jd_text.strip(),
        "jd_summary": str(parsed.get("jd_summary", "")).strip(),
        "source_url": source_url.strip(),
        "business_domain": str(parsed.get("business_domain", "")).strip(),
        "tone": str(parsed.get("tone", "")).strip(),
        "description": str(parsed.get("jd_summary", "")).strip(),
        "keywords": _validate_non_empty_string_list(
            "keywords", parsed.get("keywords", [])
        ),
        "must_have": _validate_non_empty_string_list(
            "must_have", parsed.get("must_have", [])
        ),
        "nice_to_have": _validate_non_empty_string_list(
            "nice_to_have", parsed.get("nice_to_have", [])
        ),
        "seniority_signal": _validate_non_empty_string_list(
            "seniority_signal", parsed.get("seniority_signal", [])
        ),
    }
    missing_items = _missing_items_for_job_draft(draft)
    draft["missing_items"] = missing_items
    draft["status"] = "draft_incomplete" if missing_items else "draft_ready_for_review"
    draft["active_target_eligible"] = False
    return draft


def _job_draft_prompt(jd_text: str, source_url: str) -> str:
    return (
        "请用岗位原文语言提取简洁的岗位画像 JSON，只提取明确写出的要求，不补充资历，不重复条目。"
        "必填 target_role、must_have、keywords、jd_summary；可选 company、city、nice_to_have、business_domain、seniority_signal、tone。"
        "must_have、nice_to_have、keywords、seniority_signal 是字符串数组，其余为字符串。"
        "source_jd 和 source_url 已由 App 原样保存，不要生成。只返回 JSON。\n\n"
        f"JD:\n{jd_text}"
    )

def handle_jobs_generate_profile_draft(params: dict[str, object], *, llm_config_override: dict | None = None) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    jd_text = str(params.get("jd_text", "")).strip()
    source_url = str(params.get("source_url", "")).strip()
    binding = _bound_lead(params.get("job_lead_id"), source_url)
    if binding:
        source_url = binding[1]["url"]
    if not jd_text:
        raise ValueError("jd_text is required")

    llm_config = llm_config_override if llm_config_override is not None else load_llm_config()
    base_url = str(llm_config.get("base_url") or "").strip()
    if not base_url:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "parse_blocked_local_provider",
            "code": "BLOCKED_LOCAL_PROVIDER",
            "message": "LLM base_url is not configured.",
            "draft": None,
            "active_target_eligible": False,
        }

    payload = {
        "model": str(llm_config["model"]),
        "messages": [{"role": "user", "content": _job_draft_prompt(jd_text, source_url) + (
            "\n严格来源模式：must_have、nice_to_have每项必须逐字复制JD中的完整要求条款，保留否定、条件和限定词；不得概括、补充、拼接。没有明确要求时返回空数组。"
            if params.get("strict_extract") is True else "")}],
        "temperature": float(llm_config["temperature"]),
        "response_format": {"type": "json_object"},
    }
    payload["max_tokens"] = JOB_PROFILE_DRAFT.capability.max_output_tokens
    try:
        client = _origin.LLMClient(
            base_url=base_url,
            api_key=str(llm_config["api_key_for_request"]),
            timeout=int(llm_config["timeout"]),
            provider=str(llm_config["provider"]),
            thinking_enabled=bool(llm_config.get("thinking_enabled", False)),
            reasoning_effort=str(llm_config.get("thinking_effort", "high")),
        )
        response = client.post_json(
            client.chat_completions_url, payload, response_schema=_JOB_DRAFT_RESPONSE_SCHEMA
        )
        choices = response.get("choices") or []
        if choices and choices[0].get("finish_reason") == "length":
            return {
                "meta": {"correlation_id": correlation_id},
                "status": "parse_output_truncated",
                "code": REASON_OUTPUT_TRUNCATED,
                "message": "JD 解析输出达到 token 上限，未生成可用草稿。请缩短 JD 或检查结构化输出的思考设置后重试。",
                "draft": None,
                "active_target_eligible": False,
            }
        content = _origin.LLMClient.extract_content(response).strip()
    except Exception as exc:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "parse_blocked_local_provider",
            "code": "BLOCKED_LOCAL_PROVIDER",
            "message": f"LLM JD parsing is unavailable: {exc}",
            "draft": None,
            "active_target_eligible": False,
        }

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "parse_invalid_json",
            "code": "parse_invalid_json",
            "message": "LLM output is not strict JSON.",
            "draft": None,
            "active_target_eligible": False,
        }
    if not isinstance(parsed, dict):
        return {
            "meta": {"correlation_id": correlation_id},
            "status": "parse_invalid_json",
            "code": "parse_invalid_json",
            "message": "LLM output JSON must be an object.",
            "draft": None,
            "active_target_eligible": False,
        }

    if binding:
        parsed.update(target_role=binding[1].get('position',''),company=binding[1].get('company',''))
    draft = _build_job_profile_draft(cast(dict[str, Any], parsed), jd_text, source_url)
    if binding:
        lead = binding[1]
        draft.update({**_lead_identity(lead), "source_url": lead["url"],
                      "job_lead_id": lead["id"], "job_profile_id": lead.get("job_profile_id", ""),
                      "source_jd_sha256": hashlib.sha256(jd_text.strip().encode()).hexdigest()})
    return {
        "meta": {"correlation_id": correlation_id},
        "status": draft["status"],
        "code": "OK",
        "message": "Job Profile draft generated for user review.",
        "draft": draft,
        "active_target_eligible": False,
    }


def handle_jobs_save_profile_draft(params: dict[str, object]) -> dict[str, object]:
    correlation_id = cast(dict[str, str], params["meta"])["correlation_id"]
    draft = params.get("draft")
    review = params.get("review")
    if not isinstance(draft, dict):
        raise ValueError("draft must be an object")
    if not isinstance(review, dict) or review.get("decision") != "approved":
        raise ValueError("review_required_before_save")
    requested_profile = str(params.get("job_profile_id") or draft.get("job_profile_id") or "")
    existing: dict[str, str] = {}
    if requested_profile and _profile_path(requested_profile).exists():
        existing = _read_yaml_doc(_profile_path(requested_profile))["scalars"]
    lead_id = params.get("job_lead_id") or draft.get("job_lead_id") or existing.get("job_lead_id", "")
    source_url = str(draft.get("source_url", "")).strip()
    binding = _bound_lead(lead_id, source_url)
    if existing.get("job_lead_id") and existing["job_lead_id"] != lead_id:
        raise ValueError("job_profile_binding_mismatch")
    lead = binding[1] if binding else {}
    linked_profile = lead.get("job_profile_id", "")
    if binding and requested_profile and linked_profile and requested_profile != linked_profile:
        raise ValueError("job_profile_binding_mismatch")
    if binding and requested_profile and not linked_profile and _profile_path(requested_profile).exists() and existing.get("job_lead_id") != lead_id:
        raise ValueError("job_profile_binding_mismatch")
    profile_id = requested_profile or linked_profile or f"jp_{uuid4().hex[:8]}"
    profile_path = _profile_path(profile_id)
    if profile_path.exists():
        existing = _read_yaml_doc(profile_path)["scalars"]
    normalized = {key: str(draft.get(key, "")).strip() for key in
                  ("target_role", "company", "source_jd", "jd_summary", "source_url", "business_domain", "tone")}
    normalized["description"] = str(draft.get("description") or draft.get("jd_summary") or "")
    for key in ("keywords", "must_have", "nice_to_have", "seniority_signal"):
        normalized[key] = _validate_non_empty_string_list(key, draft.get(key, []))
    if binding:
        normalized.update(_lead_identity(lead))
        normalized["source_url"] = lead["url"]
        normalized["company"] = lead.get("company", "")
    missing = _missing_items_for_job_draft(normalized)
    mode = str(params.get("save_mode") or "incomplete")
    if mode not in {"complete", "incomplete"}:
        raise ValueError("unsupported save_mode")
    if mode == "complete" and missing:
        raise ValueError("complete job profile requires JD text, role, must_have, keywords, and summary")
    digest = hashlib.sha256(normalized["source_jd"].encode()).hexdigest()
    capture = current_jd_capture(lead) if binding else None
    from_public_detail = bool(capture and capture["source_jd_sha256"] == digest)
    if mode == "complete" and binding and lead.get("source") == "liepin_official" and not from_public_detail:
        raise ValueError("stored_jd_source_unverified")
    if from_public_detail:
        normalized["source_url"] = capture["source_url"]
    # 人工导入：没有官方线索绑定（或线索本身就是人工 JD）；平台按链接域名识别。
    manual_source = (not binding) or lead.get("source", "manual_jd") == "manual_jd"
    platform = str(normalized.get("platform") or lead.get("platform") or platform_from_url(normalized["source_url"]))
    if mode == "complete" and from_public_detail:
        source_check = {"checked": True, "accessible": True, "status": "verified_public_detail", "verified_at": capture["fetched_at"]}
    elif mode == "complete" and manual_source and platform in MANUAL_IMPORT_PLATFORMS and normalized["source_url"]:
        parsed_url = urlparse(normalized["source_url"])
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            source_check = {"checked": True, "accessible": False, "status": "invalid_url"}
        else:
            source_check = {"checked": False, "accessible": None, "status": "manual_platform_not_checked", "platform": platform}
    elif mode == "complete":
        source_check = _origin._check_source_url_accessible(normalized["source_url"])
    else:
        source_check = {"checked": False, "accessible": False, "status": "not_required"}
    if mode == "complete" and normalized["source_url"] and source_check.get("checked") and not source_check.get("accessible"):
        raise ValueError("job_source_unavailable")
    now = _utcnow_iso()
    source_recorded_at = str(existing.get("source_recorded_at") or (now if normalized["source_url"] else ""))
    if not binding and mode == "complete" and normalized["source_url"]:
        lead_id = f"jl_{uuid4().hex[:8]}"
        lead = {"id": lead_id, "source": "manual_jd", "url": normalized["source_url"],
                "company": normalized["company"], "position": normalized["target_role"], "created_at": now,
                "platform": platform, "import_mode": "manual", "source_recorded_at": source_recorded_at}
        binding = (_lead_path(lead_id), lead)
    fields = {**normalized, "job_lead_id": str(lead_id or ""), "source_jd_sha256": digest,
              "jd_origin": "public_page" if from_public_detail else "manual_input",
              "import_mode": "manual" if manual_source else str(existing.get("import_mode", "")),
              "source_recorded_at": source_recorded_at,
              "status": "active" if mode == "complete" else "saved_incomplete",
              "created_at": existing.get("created_at") or now, "updated_at": now,
              "review_decision": "approved" if mode == "complete" else "",
              "reviewed_at": str(review.get("reviewed_at") or now) if mode == "complete" else "",
              "missing_items": missing}
    if platform:
        fields["platform"] = platform
    _write_job_profile_file(profile_path, fields)
    if binding:
        lead.update({"job_profile_id": profile_id, "updated_at": now})
        if lead.get("source") != "liepin_official" or from_public_detail:
            # A user draft is separate; never replace the archived (even invalidated) captured body.
            lead.update({"source_jd":normalized["source_jd"], "source_jd_sha256":digest,
                         "jd_origin":fields["jd_origin"],
                         "jd_status":"complete_reviewed" if mode == "complete" else "full_unreviewed"})
        if manual_source:
            lead.setdefault("import_mode", "manual")
            if platform and not lead.get("platform"):
                lead["platform"] = platform
            if source_recorded_at and not lead.get("source_recorded_at"):
                lead["source_recorded_at"] = source_recorded_at
        _write_job_lead_file(binding[0], lead)
    return {"meta": {"correlation_id": correlation_id}, "job_profile_id": profile_id,
            "job_lead_id": str(lead_id or ""), "status": "saved_complete" if mode == "complete" else "saved_incomplete",
            "active_target_eligible": mode == "complete", "missing_items": missing,
            "source_url_check": source_check, "updated_at": now}

def handle_jobs_fetch_liepin_detail(params: dict[str, Any]) -> dict[str, Any]:
    from tools.infra.liepin_job_detail import LiepinJobDetailError, fetch_liepin_job_detail
    base = {"meta": {"correlation_id": params["meta"]["correlation_id"]}, "status": "blocked",
            "job_lead_id": str(params.get("job_lead_id") or ""), "job_profile_id": "",
            "jd_text": "", "source_url": "", "source_jd_sha256": "", "jd_status": "summary_only"}
    try:
        binding = _bound_lead(params.get("job_lead_id"))
        if not binding or binding[1].get("source") != "liepin_official" or not binding[1].get("platform_job_id"):
            return {**base, "code": "INVALID_INPUT", "message": "请选择已保存的猎聘官方岗位线索。"}
        path, lead = binding
        detail = fetch_liepin_job_detail(lead["url"], expected_job_id=lead["platform_job_id"])
        current = _read_yaml_doc(path)["scalars"]
        capture = {key:detail.get(key) for key in ("source_url", "platform_job_id", "source_jd_sha256", "fetched_at")}
        capture["platform_job_type"] = current.get("platform_job_type")
        captured = {**current, "source_jd": detail["jd_text"], "source_jd_sha256":detail["source_jd_sha256"],
                    "jd_origin":"public_page", "jd_status":"full_unreviewed",
                    JD_CAPTURE_KEY:json.dumps({**capture, "invalidated":False}, ensure_ascii=False)}
        if (current.get("id") != lead.get("id") or current.get("platform_job_type") != lead.get("platform_job_type")
                or not current_jd_capture(captured)):
            return {**base, "code":"JOB_ID_MISMATCH", "message":"岗位身份或详情读取依据已变化，未保存正文。"}
        lead = current
        keep_review = (lead.get("source_jd_sha256") == detail["source_jd_sha256"]
                       and reviewed_official_profile(lead, _origin._JOB_PROFILE_DIR) is not None)
        if not keep_review and lead.get("job_profile_id"):
            profile_path = _profile_path(lead["job_profile_id"])
            if profile_path.exists():
                profile = _preserved_profile_fields(_read_yaml_doc(profile_path))
                same_unapproved_draft = (
                    profile.get("status") == "draft" and not profile.get("review_decision")
                    and not profile.get("reviewed_at") and profile.get("job_lead_id") == lead.get("id")
                    and same_official_source_url(profile.get("source_url", ""), capture["source_url"])
                    and profile.get("source_jd") == detail["jd_text"]
                    and profile.get("source_jd_sha256") == capture["source_jd_sha256"]
                    and all(profile.get(key) == lead.get(key) for key in
                            ("source", "platform", "platform_job_id", "platform_job_type"))
                )
                if not same_unapproved_draft:
                    profile.update({"status":"saved_incomplete", "review_decision":"", "reviewed_at":"",
                                    "missing_items":["review_required"]})
                    _write_job_profile_file(profile_path, profile)
        lead.update({"source_jd": detail["jd_text"], "source_jd_sha256": detail["source_jd_sha256"],
                     "jd_origin": "public_page", "fetched_at": detail["fetched_at"], "updated_at": _utcnow_iso(),
                     "jd_status": "complete_reviewed" if keep_review else "full_unreviewed",
                     JD_CAPTURE_KEY:captured[JD_CAPTURE_KEY]})
        _write_job_lead_file(path, lead)
        return {**base, "status": "pass", "code": "OK", "message": "完整 JD 已读取，请解析并审核后保存。",
                "job_lead_id": lead["id"], "job_profile_id": lead.get("job_profile_id", ""),
                "jd_text": detail["jd_text"], "source_url": capture["source_url"],
                "source_jd_sha256": detail["source_jd_sha256"], "jd_status": lead["jd_status"]}
    except LiepinJobDetailError as exc:
        if exc.code == "JOB_ID_MISMATCH" or exc.detail_reason in ("source_reports_unavailable", "source_page_not_found"):
            raw_capture = lead.get(JD_CAPTURE_KEY)
            invalidated = invalidate_jd_capture(raw_capture)
            if raw_capture != invalidated:
                try:
                    latest = _read_yaml_doc(path)["scalars"]
                    if (latest.get("id") == lead.get("id")
                            and latest.get(JD_CAPTURE_KEY) == raw_capture
                            and latest.get("platform_job_id") == lead.get("platform_job_id")
                            and latest.get("platform_job_type") == lead.get("platform_job_type")
                            and same_official_source_url(latest.get("url",""), lead.get("url",""))):
                        was_current = current_jd_capture(latest) is not None
                        _write_job_lead_file(path, {**latest, JD_CAPTURE_KEY:invalidated})
                        if was_current:
                            # For a blocked result a linked ID means this request
                            # actually revoked that lead's current capture.
                            base["job_profile_id"] = latest.get("job_profile_id") or ""
                except (OSError, KeyError, ValueError):
                    return {**base, "code":"STORAGE_ERROR", "message":"未能保存当前来源校验结果。"}
        reason = {"detail_reason": exc.detail_reason} if exc.detail_reason else {}
        return {**base, "code": exc.code, "message": exc.message, **reason}
    except KeyError:
        return {**base, "code": "NOT_FOUND", "message": "岗位线索不存在。"}
    except ValueError:
        return {**base, "code": "INVALID_INPUT", "message": "岗位线索标识无效。"}
    except OSError:
        return {**base, "code": "STORAGE_ERROR", "message": "完整 JD 保存失败，原审核不可用于投递。"}

def handle_jobs_create_profile(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    title = str(params.get("title", "")).strip()
    if not title:
        raise ValueError("title is required")
    if len(title) > 200:
        raise ValueError("title must not exceed 200 characters")
    status = str(params.get("status") or "draft")
    if status not in {"active", "draft"}:
        raise ValueError(f"unsupported status: {status}")
    created_at = _utcnow_iso()
    job_profile_id = f"jp_{uuid4().hex[:8]}"
    fields = {
        "target_role": title,
        "company": "",
        "source_jd": "",
        "business_domain": "",
        "tone": "",
        "description": str(params.get("description", "")),
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "keywords": _validate_string_list("tags", params.get("tags", [])),
        "must_have": [],
        "nice_to_have": [],
        "seniority_signal": [],
    }
    _write_job_profile_file(_profile_path(job_profile_id), fields)
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
        "status": status,
        "created_at": created_at,
    }


def handle_jobs_update_profile(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    job_profile_id = str(params["job_profile_id"])
    patch = cast(dict[str, object], params.get("patch") or {})
    path = _profile_path(job_profile_id)
    if not path.exists():
        raise KeyError(f"NOT_FOUND: {job_profile_id}")
    if "title" in patch and not str(patch.get("title", "")).strip():
        raise ValueError("title must not be empty")
    if "status" in patch and str(patch["status"]) not in {
        "active",
        "draft",
        "archived",
    }:
        raise ValueError(f"unsupported status: {patch['status']}")

    doc = _read_yaml_doc(path)
    s = doc["scalars"]
    l = doc["lists"]
    updated_at = _utcnow_iso()
    fields = {
        **_preserved_profile_fields(doc),
        "target_role": str(patch.get("title", s.get("target_role", ""))).strip(),
        "company": s.get("company", ""),
        "source_jd": s.get("source_jd", ""),
        "business_domain": s.get("business_domain", ""),
        "tone": s.get("tone", ""),
        "description": str(patch.get("description", s.get("description", ""))),
        "status": str(patch.get("status", s.get("status", "draft"))),
        "created_at": s.get("created_at", ""),
        "updated_at": updated_at,
        "keywords": _validate_string_list(
            "tags", patch.get("tags", l.get("keywords", []))
        ),
        "must_have": cast(list[str], l.get("must_have", [])),
        "nice_to_have": cast(list[str], l.get("nice_to_have", [])),
        "seniority_signal": cast(list[str], l.get("seniority_signal", [])),
    }
    if s.get("job_lead_id"):
        semantic_change = (fields["target_role"] != s.get("target_role", "")
                           or fields["keywords"] != l.get("keywords", [])
                           or fields["description"] != s.get("description", ""))
        if semantic_change:
            fields.update({"status": "saved_incomplete", "review_decision": "", "reviewed_at": "", "missing_items": ["review_required"]})
        elif fields["status"] == "active" and s.get("review_decision") != "approved":
            raise ValueError("review_required_before_activation")
    _write_job_profile_file(path, fields)
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
        "updated_at": updated_at,
    }


def handle_jobs_delete_profile(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    job_profile_id = str(params["job_profile_id"])
    path = _profile_path(job_profile_id)
    if not path.exists():
        raise KeyError(f"NOT_FOUND: {job_profile_id}")
    if job_profile_id in _running_submission_profile_ids():
        raise RuntimeError(f"CONFLICT: active run references {job_profile_id}")
    path.rename(path.with_suffix(".yaml.deleted"))
    _clear_lead_profile_reference(job_profile_id)
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
        "deleted": True,
    }


def handle_jobs_convert_lead(params: dict[str, object]) -> dict[str, object]:
    meta = cast(dict[str, str], params["meta"])
    correlation_id = meta["correlation_id"]
    job_lead_id = str(params["job_lead_id"])
    path = _find_lead_path(job_lead_id)
    if path is None:
        raise KeyError(f"NOT_FOUND: {job_lead_id}")
    doc = _read_yaml_doc(path)
    s = doc["scalars"]
    if s.get("job_profile_id") and _profile_path(s["job_profile_id"]).exists():
        return {"meta": {"correlation_id": correlation_id}, "job_profile_id": s["job_profile_id"], "job_lead_id": job_lead_id}
    created_at = _utcnow_iso()
    job_profile_id = f"jp_{uuid4().hex[:8]}"
    summary_only = not lead_has_complete_jd(s)
    capture = current_jd_capture(s)
    if not summary_only and s.get("source") == "liepin_official" and not capture:
        raise ValueError("stored_jd_source_unverified")
    fields = {
        **_lead_identity(s),
        "target_role": s.get("position", s.get("title", "")),
        "company": s.get("company", ""),
        "source_jd": s.get("source_jd", ""),
        "source_jd_sha256": s.get("source_jd_sha256", ""),
        "jd_origin": s.get("jd_origin", ""),
        "source_url": capture["source_url"] if capture else s.get("url", ""),
        "job_lead_id": job_lead_id,
        "business_domain": "",
        "tone": "",
        "description": "",
        "status": "saved_incomplete" if summary_only else "draft",
        "missing_items": ["source_jd", "must_have", "keywords", "jd_summary"] if summary_only else [],
        "created_at": created_at,
        "updated_at": created_at,
        "keywords": [],
        "must_have": [],
        "nice_to_have": [],
        "seniority_signal": [],
    }
    _write_job_profile_file(_profile_path(job_profile_id), fields)
    _write_job_lead_file(path, {**s, "job_profile_id": job_profile_id})
    return {
        "meta": {"correlation_id": correlation_id},
        "job_profile_id": job_profile_id,
        "job_lead_id": job_lead_id,
    }
