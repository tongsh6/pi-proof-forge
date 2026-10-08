from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from tools.acceptance.external_l3_job_lead_bridge import (
    build_external_l3_lead_packet,
    format_env_template,
    load_job_lead_candidates,
    redacted_packet_dict,
    select_job_lead_candidate,
)


def _write_session(root: Path) -> Path:
    session_dir = root / "outputs" / "submissions"
    liepin_dir = session_dir / "liepin" / "session" / "liepin"
    (liepin_dir / "Default").mkdir(parents=True)
    (liepin_dir / "Local State").write_text("state", encoding="utf-8")
    (liepin_dir / "Default" / "Preferences").write_text("prefs", encoding="utf-8")
    return session_dir


def _write_resume_and_profile(root: Path) -> tuple[Path, Path]:
    resume = root / "uploaded_resumes" / "resume.pdf"
    profile = root / "profiles" / "candidate_profile.yaml"
    resume.parent.mkdir(parents=True)
    profile.parent.mkdir(parents=True)
    resume.write_bytes(b"%PDF-1.4\nbridge\n")
    profile.write_text('name: "Candidate"\nemail: "candidate@example.com"\n', encoding="utf-8")
    return resume, profile


def _write_validation_log(root: Path) -> Path:
    log = root / "outputs" / "submissions" / "validated" / "submission_log.yaml"
    log.parent.mkdir(parents=True)
    log.write_text(
        "\n".join(
            [
                'status: "success"',
                "steps:",
                '  - name: "target_verify"',
                '    status: "success"',
                '    detail: "url_job_id=1980984659; dom_jobid=80984659; params_jobid=80984659; recruiter=虞女士"',
                '    screenshot: ""',
                '  - name: "submit"',
                '    status: "skipped"',
                '    detail: "submit not enabled"',
                '    screenshot: ""',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return log


def test_builds_redacted_confirmation_packet_from_validated_list_lead(tmp_path: Path) -> None:
    validation_log = _write_validation_log(tmp_path)
    resume, profile = _write_resume_and_profile(tmp_path)
    session_dir = _write_session(tmp_path)
    lead_source = tmp_path / "job_leads" / "jl-validated.yaml"
    lead_source.parent.mkdir()
    lead_source.write_text(
        "\n".join(
            [
                'generated_at: "2026-05-13T00:29:20+08:00"',
                "items:",
                '  - job_url: "https://www.liepin.com/job/1980984659.shtml"',
                '    position: "架构师"',
                '    company_name: "海程新材料(芜湖)有限公司"',
                "    direction: backend",
                "    confidence: 0.82",
                f'    validation_log: "{validation_log}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    packet = build_external_l3_lead_packet(
        lead_source=lead_source,
        lead_index=0,
        job_lead_id="",
        resume_pdf=resume,
        profile_yaml=profile,
        session_dir=session_dir,
    )
    redacted = redacted_packet_dict(packet)
    env_template = format_env_template(packet)
    redacted_text = json.dumps(redacted, ensure_ascii=False)

    assert packet.missing_items == ()
    assert redacted["status"] == "ready_for_operator_confirmation"
    assert redacted["candidate"]["job_url_host"] == "www.liepin.com"
    assert redacted["target_confirmation"]["url_job_id_present"] is True
    assert redacted["target_confirmation"]["recruiter_present"] is True
    assert redacted["artifacts"]["resume_pdf"]["basename_persisted"] is False
    assert redacted["session"]["storage_ready"] is True

    assert "https://www.liepin.com/job/1980984659.shtml" not in redacted_text
    assert "虞女士" not in redacted_text
    assert "resume.pdf" not in redacted_text
    assert "PIPF_EXTERNAL_L3_AUTHORIZED=false" in env_template
    assert "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED=false" in env_template
    assert "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID=1980984659" in env_template
    assert "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER=" in env_template


def test_reports_structured_gaps_when_target_verify_is_missing(tmp_path: Path) -> None:
    resume, profile = _write_resume_and_profile(tmp_path)
    session_dir = _write_session(tmp_path)
    lead_source = tmp_path / "job_leads" / "jl-missing.yaml"
    lead_source.parent.mkdir()
    lead_source.write_text(
        "\n".join(
            [
                'id: "jl_missing"',
                'company: "Example"',
                'position: "Backend Engineer"',
                'job_url: "https://www.liepin.com/job/100.shtml"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    packet = build_external_l3_lead_packet(
        lead_source=lead_source,
        lead_index=None,
        job_lead_id="",
        resume_pdf=resume,
        profile_yaml=profile,
        session_dir=session_dir,
    )
    redacted = redacted_packet_dict(packet)

    assert redacted["status"] == "blocked_until_missing_evidence"
    assert "validation_log_present" in packet.missing_items
    assert "target_verify_success" in packet.missing_items
    assert "confirm_job_id_present" in packet.missing_items
    assert "confirm_recruiter_present" in packet.missing_items


def _ready_packet(tmp_path: Path, *, job_id: str = "1980984659"):
    validation_log = _write_validation_log(tmp_path)
    resume, profile = _write_resume_and_profile(tmp_path)
    session_dir = _write_session(tmp_path)
    lead_source = tmp_path / "lead.yaml"
    lead_source.write_text(
        f'id: "jl_shell"\njob_url: "https://www.liepin.com/job/{job_id}.shtml"\n'
        f'validation_log: "{validation_log}"\n',
        encoding="utf-8",
    )
    return build_external_l3_lead_packet(
        lead_source=lead_source,
        lead_index=None,
        job_lead_id="",
        resume_pdf=resume,
        profile_yaml=profile,
        session_dir=session_dir,
    )


def test_env_template_passes_literal_values_to_child_process(tmp_path: Path) -> None:
    root = tmp_path / "资料 $name 'quoted'"
    packet = _ready_packet(root)
    template = format_env_template(packet)
    probe = (
        "import json, os; "
        "print(json.dumps({key: value for key, value in os.environ.items() "
        "if key.startswith('PIPF_EXTERNAL_L3_')}))"
    )
    # 用只读探针替代最后的验收命令，验证真实 shell 传参而不访问外部渠道。
    script = "\n".join(template.splitlines()[:-1]) + "\n"
    script += f"exec {shlex.quote(sys.executable)} -c {shlex.quote(probe)}"
    completed = subprocess.run(
        ["/bin/sh", "-c", script],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    env = json.loads(completed.stdout)
    assert env.get("PIPF_EXTERNAL_L3_JOB_URL") == packet.candidate.job_url
    assert env.get("PIPF_EXTERNAL_L3_RESUME_PDF") == packet.resume_pdf.path
    assert env.get("PIPF_EXTERNAL_L3_CONFIRM_RECRUITER") == packet.target_verify.recruiter
    assert env.get("PIPF_EXTERNAL_L3_AUTHORIZED") == "false"
    assert env.get("PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED") == "false"


def test_session_storage_does_not_imply_manual_login_confirmation(tmp_path: Path) -> None:
    packet = _ready_packet(tmp_path)
    assert packet.session.storage_ready is True
    template = format_env_template(packet)
    assert "PIPF_EXTERNAL_L3_SESSION_READY_CONFIRMED=false" in template


def test_rejects_validation_log_for_another_job(tmp_path: Path) -> None:
    packet = _ready_packet(tmp_path, job_id="1980984660")
    assert "target_job_id_matches" in packet.missing_items
    assert redacted_packet_dict(packet)["status"] == "blocked_until_missing_evidence"


def test_lead_index_keeps_original_items_position_after_filtering(tmp_path: Path) -> None:
    source = tmp_path / "leads.yaml"
    source.write_text(
        'items:\n  - position: "尚无链接"\n'
        '  - job_url: "https://www.liepin.com/job/101.shtml"\n'
        '  - job_url: "https://www.liepin.com/job/102.shtml"\n',
        encoding="utf-8",
    )
    candidates = load_job_lead_candidates(source)
    first = select_job_lead_candidate(candidates, lead_index=1)
    assert first.lead_index == 1
    assert first.job_url.endswith("/101.shtml")
    assert select_job_lead_candidate(candidates, lead_index=2).lead_index == 2
    with pytest.raises(ValueError, match="lead_index"):
        select_job_lead_candidate(candidates, lead_index=0)
