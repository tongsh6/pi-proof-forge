from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.submission.liepin import _extract_liepin_job_id


_TARGET_VERIFY_PART_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^;]+)")
_SESSION_STATE_MARKER_PATHS = (
    "Local State",
    "Default/Preferences",
    "Default/Cookies",
    "Default/Network/Cookies",
    "Cookies",
    "storage-state.json",
)


@dataclass(frozen=True)
class JobLeadCandidate:
    lead_source: str
    lead_index: int | None
    job_lead_id: str
    company: str
    position: str
    job_url: str
    direction: str
    confidence: str
    validation_log: str


@dataclass(frozen=True)
class TargetVerifyEvidence:
    status: str
    url_job_id: str
    dom_job_id: str
    params_job_id: str
    recruiter: str
    source_path: str


@dataclass(frozen=True)
class LocalFileEvidence:
    path: str
    provided: bool
    exists: bool
    extension: str
    size: int
    sha256: str


@dataclass(frozen=True)
class SessionEvidence:
    session_dir: str
    channel_session_dir_exists: bool
    state_markers: tuple[str, ...]
    storage_ready: bool


@dataclass(frozen=True)
class ExternalL3LeadPacket:
    candidate: JobLeadCandidate
    target_verify: TargetVerifyEvidence
    resume_pdf: LocalFileEvidence
    profile_yaml: LocalFileEvidence
    session: SessionEvidence
    missing_items: tuple[str, ...]


def load_job_lead_candidates(lead_source: Path) -> list[JobLeadCandidate]:
    doc = parse_simple_yaml(lead_source.read_text(encoding="utf-8"))
    candidates: list[JobLeadCandidate] = []
    items = doc.get("lists", {}).get("items", [])
    if items:
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            job_url = str(item.get("job_url") or item.get("url") or "").strip()
            if not job_url:
                continue
            candidates.append(
                JobLeadCandidate(
                    lead_source=str(lead_source),
                    lead_index=index,
                    job_lead_id=str(
                        item.get("id") or item.get("job_lead_id") or f"{lead_source.stem}:{index}"
                    ),
                    company=str(item.get("company_name") or item.get("company") or "").strip(),
                    position=str(item.get("position") or "").strip(),
                    job_url=job_url,
                    direction=str(item.get("direction") or "").strip(),
                    confidence=str(item.get("confidence") or "").strip(),
                    validation_log=str(item.get("validation_log") or "").strip(),
                )
            )
        return candidates

    scalars = doc.get("scalars", {})
    job_url = str(scalars.get("job_url") or scalars.get("url") or "").strip()
    if not job_url:
        return []
    return [
        JobLeadCandidate(
            lead_source=str(lead_source),
            lead_index=None,
            job_lead_id=str(scalars.get("id") or scalars.get("job_lead_id") or lead_source.stem),
            company=str(scalars.get("company") or scalars.get("company_name") or "").strip(),
            position=str(scalars.get("position") or "").strip(),
            job_url=job_url,
            direction=str(scalars.get("direction") or "").strip(),
            confidence=str(scalars.get("confidence") or "").strip(),
            validation_log=str(scalars.get("validation_log") or "").strip(),
        )
    ]


def select_job_lead_candidate(
    candidates: Sequence[JobLeadCandidate],
    *,
    lead_index: int | None = None,
    job_lead_id: str = "",
) -> JobLeadCandidate:
    if job_lead_id:
        for candidate in candidates:
            if candidate.job_lead_id == job_lead_id:
                return candidate
        raise ValueError(f"job lead id not found: {job_lead_id}")
    if lead_index is None:
        if len(candidates) == 1:
            return candidates[0]
        raise ValueError("lead_index is required when lead source has multiple candidates")
    for candidate in candidates:
        if candidate.lead_index == lead_index:
            return candidate
    raise ValueError(f"lead_index unavailable in source: {lead_index}")


def load_target_verify_evidence(validation_log: str) -> TargetVerifyEvidence:
    if not validation_log:
        return TargetVerifyEvidence(
            status="missing_validation_log",
            url_job_id="",
            dom_job_id="",
            params_job_id="",
            recruiter="",
            source_path="",
        )
    path = Path(validation_log)
    if not path.exists():
        return TargetVerifyEvidence(
            status="validation_log_not_found",
            url_job_id="",
            dom_job_id="",
            params_job_id="",
            recruiter="",
            source_path=str(path),
        )

    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        steps = payload.get("steps", [])
    else:
        steps = _parse_submission_log_steps(path.read_text(encoding="utf-8"))

    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("name") or "") != "target_verify":
            continue
        detail = str(step.get("detail") or "")
        parts = {
            match.group(1): match.group(2).strip()
            for match in _TARGET_VERIFY_PART_RE.finditer(detail)
        }
        return TargetVerifyEvidence(
            status=str(step.get("status") or ""),
            url_job_id=parts.get("url_job_id", "") or parts.get("job_id", ""),
            dom_job_id=parts.get("dom_jobid", "") or parts.get("dom_job_id", ""),
            params_job_id=parts.get("params_jobid", "") or parts.get("params_job_id", ""),
            recruiter=parts.get("recruiter", ""),
            source_path=str(path),
        )

    return TargetVerifyEvidence(
        status="target_verify_missing",
        url_job_id="",
        dom_job_id="",
        params_job_id="",
        recruiter="",
        source_path=str(path),
    )


def _parse_submission_log_steps(text: str) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_steps = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^steps\s*:\s*$", line):
            in_steps = True
            continue
        if in_steps and not line[:1].isspace():
            break
        if not in_steps:
            continue
        item_match = re.match(r"^\s*-\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if item_match:
            current = {item_match.group(1): _yaml_scalar(item_match.group(2))}
            steps.append(current)
            continue
        if current is None:
            continue
        child_match = re.match(r"^\s+([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if child_match:
            current[child_match.group(1)] = _yaml_scalar(child_match.group(2))
    return steps


def _yaml_scalar(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and (
        (stripped.startswith('"') and stripped.endswith('"'))
        or (stripped.startswith("'") and stripped.endswith("'"))
    ):
        return stripped[1:-1]
    return stripped


def build_external_l3_lead_packet(
    *,
    lead_source: Path,
    lead_index: int | None,
    job_lead_id: str,
    resume_pdf: Path,
    profile_yaml: Path,
    session_dir: Path,
) -> ExternalL3LeadPacket:
    candidates = load_job_lead_candidates(lead_source)
    candidate = select_job_lead_candidate(
        candidates,
        lead_index=lead_index,
        job_lead_id=job_lead_id,
    )
    target_verify = load_target_verify_evidence(candidate.validation_log)
    packet = ExternalL3LeadPacket(
        candidate=candidate,
        target_verify=target_verify,
        resume_pdf=_file_evidence(resume_pdf),
        profile_yaml=_file_evidence(profile_yaml),
        session=_session_evidence(session_dir),
        missing_items=(),
    )
    missing_items = tuple(_missing_items(packet))
    return ExternalL3LeadPacket(
        candidate=packet.candidate,
        target_verify=packet.target_verify,
        resume_pdf=packet.resume_pdf,
        profile_yaml=packet.profile_yaml,
        session=packet.session,
        missing_items=missing_items,
    )


def redacted_packet_dict(packet: ExternalL3LeadPacket) -> dict[str, Any]:
    parsed_url = urlparse(packet.candidate.job_url)
    return {
        "status": "ready_for_operator_confirmation"
        if not packet.missing_items
        else "blocked_until_missing_evidence",
        "raw_live_inputs_persisted": False,
        "candidate": {
            "job_lead_id": packet.candidate.job_lead_id,
            "lead_source": packet.candidate.lead_source,
            "lead_index": packet.candidate.lead_index,
            "company": packet.candidate.company,
            "position": packet.candidate.position,
            "direction": packet.candidate.direction,
            "confidence": packet.candidate.confidence,
            "job_url_scheme": parsed_url.scheme,
            "job_url_host": parsed_url.netloc,
            "job_url_raw_value_persisted": False,
        },
        "target_confirmation": {
            "target_verify_status": packet.target_verify.status,
            "url_job_id_present": bool(packet.target_verify.url_job_id),
            "dom_job_id_present": bool(packet.target_verify.dom_job_id),
            "params_job_id_present": bool(packet.target_verify.params_job_id),
            "recruiter_present": bool(packet.target_verify.recruiter),
            "confirmation_values_persisted": False,
            "source_path": packet.target_verify.source_path,
        },
        "artifacts": {
            "resume_pdf": _redacted_file_dict(packet.resume_pdf),
            "profile_yaml": _redacted_file_dict(packet.profile_yaml),
        },
        "session": {
            "session_dir": packet.session.session_dir,
            "channel_session_dir_exists": packet.session.channel_session_dir_exists,
            "state_markers": list(packet.session.state_markers),
            "storage_ready": packet.session.storage_ready,
        },
        "missing_items": list(packet.missing_items),
        "operator_confirmation_required": {
            "external_l3_authorized": True,
            "final_submit_confirmed": True,
            "target_identity_confirmed": True,
        },
    }


def format_env_template(packet: ExternalL3LeadPacket) -> str:
    assignments = [
        ("PIPF_EXTERNAL_L3_CHANNEL", "liepin"),
        ("PIPF_EXTERNAL_L3_AUTHORIZED", "false"),
        ("PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED", "false"),
        ("PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED", "false"),
        ("PIPF_EXTERNAL_L3_SESSION_DIR", packet.session.session_dir),
        ("PIPF_EXTERNAL_L3_JOB_URL", packet.candidate.job_url),
        ("PIPF_EXTERNAL_L3_RESUME_PDF", packet.resume_pdf.path),
        ("PIPF_EXTERNAL_L3_PROFILE", packet.profile_yaml.path),
        ("PIPF_EXTERNAL_L3_CONFIRM_JOB_ID", packet.target_verify.url_job_id),
        ("PIPF_EXTERNAL_L3_CONFIRM_RECRUITER", packet.target_verify.recruiter),
    ]
    lines = [
        "# 执行前复核候选、简历和目标身份。",
        "# 外部授权、最终提交确认与人工会话确认默认关闭，须由操作者明确确认。",
    ]
    lines.extend(f"export {key}={shlex.quote(value)}" for key, value in assignments)
    lines.append("bash scripts/acceptance/run-acceptance.sh --run-id acceptance_external_l3 --level L3")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an External L3 confirmation packet from a validated Job Lead."
    )
    _ = parser.add_argument("--lead-source", required=True, help="Path to job_leads YAML")
    _ = parser.add_argument("--lead-index", type=int, default=None, help="Zero-based lead index for items list")
    _ = parser.add_argument("--job-lead-id", default="", help="Select by job lead id instead of index")
    _ = parser.add_argument("--resume-pdf", required=True, help="Reviewed resume PDF path")
    _ = parser.add_argument("--profile", required=True, help="Reviewed profile YAML path")
    _ = parser.add_argument("--session-dir", default="outputs/submissions", help="External L3 session root")
    _ = parser.add_argument(
        "--format",
        choices=("json", "env"),
        default="json",
        help="json prints redacted packet; env prints shell env template to stdout",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    packet = build_external_l3_lead_packet(
        lead_source=Path(args.lead_source),
        lead_index=args.lead_index,
        job_lead_id=str(args.job_lead_id or ""),
        resume_pdf=Path(args.resume_pdf),
        profile_yaml=Path(args.profile),
        session_dir=Path(args.session_dir),
    )
    if args.format == "env":
        print(format_env_template(packet))
    else:
        print(json.dumps(redacted_packet_dict(packet), ensure_ascii=False, indent=2))
    return 0 if not packet.missing_items else 1


def _file_evidence(path: Path) -> LocalFileEvidence:
    if not str(path):
        return LocalFileEvidence("", False, False, "", 0, "")
    exists = path.exists() and path.is_file()
    if not exists:
        return LocalFileEvidence(str(path), True, False, path.suffix, 0, "")
    return LocalFileEvidence(
        path=str(path),
        provided=True,
        exists=True,
        extension=path.suffix,
        size=path.stat().st_size,
        sha256=_sha256(path),
    )


def _session_evidence(session_dir: Path) -> SessionEvidence:
    channel_session_dir = session_dir / "liepin" / "session" / "liepin"
    markers: list[str] = []
    for marker in _SESSION_STATE_MARKER_PATHS:
        marker_path = channel_session_dir / marker
        if marker_path.exists() and marker_path.is_file() and marker_path.stat().st_size > 0:
            markers.append(marker)
    return SessionEvidence(
        session_dir=str(session_dir),
        channel_session_dir_exists=channel_session_dir.exists(),
        state_markers=tuple(markers),
        storage_ready=channel_session_dir.exists() and bool(markers),
    )


def _missing_items(packet: ExternalL3LeadPacket) -> list[str]:
    missing: list[str] = []
    parsed_url = urlparse(packet.candidate.job_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        missing.append("job_url_valid")
    if not packet.target_verify.source_path:
        missing.append("validation_log_present")
    if packet.target_verify.status != "success":
        missing.append("target_verify_success")
    if not packet.target_verify.url_job_id:
        missing.append("confirm_job_id_present")
    candidate_job_id = _extract_liepin_job_id(packet.candidate.job_url)
    if not candidate_job_id or candidate_job_id != packet.target_verify.url_job_id:
        missing.append("target_job_id_matches")
    if not packet.target_verify.recruiter:
        missing.append("confirm_recruiter_present")
    if not packet.resume_pdf.exists or packet.resume_pdf.extension.lower() != ".pdf":
        missing.append("resume_pdf_file_ready")
    if not packet.profile_yaml.exists or packet.profile_yaml.extension.lower() not in {".yaml", ".yml"}:
        missing.append("profile_yaml_file_ready")
    if not packet.session.storage_ready:
        missing.append("manual_session_storage_ready")
    return missing


def _redacted_file_dict(evidence: LocalFileEvidence) -> dict[str, Any]:
    return {
        "provided": evidence.provided,
        "exists": evidence.exists,
        "basename_persisted": False,
        "raw_content_persisted": False,
        "extension": evidence.extension,
        "size": evidence.size,
        "sha256": evidence.sha256,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
