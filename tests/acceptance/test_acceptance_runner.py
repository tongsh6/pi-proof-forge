from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from tools.acceptance.acceptance_runner import (
    build_run_id,
    run_acceptance,
    write_acceptance_report,
)


def test_acceptance_runner_defaults_to_l1(tmp_path: Path) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=0, stdout="l1 ok", stderr="")

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1",),
            timeout_seconds=10,
        )

    assert report.status == "pass"
    assert report.levels == ("L1",)
    assert [step.level for step in report.steps] == [
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
    ]
    assert [step.name for step in report.steps] == [
        "first_launch_configure_lm_studio",
        "setup_profile_and_material_library",
        "generate_review_and_complete_evidence_card",
        "setup_job_target",
        "quick_run_generate_and_evaluate_resume",
        "agent_run_guided_batch",
        "channel_session_setup",
        "submission_check_mode",
        "feedback_iteration_after_check_mode",
        "closed_loop_e2e_audit",
    ]
    assert run_mock.call_count == 9
    assert run_mock.call_args_list[0].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_first_launch_configure_lm_studio.py",
        "-q",
    ]
    assert run_mock.call_args_list[1].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_setup_profile_and_material_library.py",
        "-q",
    ]
    assert run_mock.call_args_list[2].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_generate_review_and_complete_evidence_card.py",
        "-q",
    ]
    assert run_mock.call_args_list[3].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_setup_job_target.py",
        "-q",
    ]
    assert run_mock.call_args_list[4].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_quick_run_generate_and_evaluate_resume.py",
        "-q",
    ]
    assert run_mock.call_args_list[5].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_agent_run_guided_batch.py",
        "-q",
    ]
    assert run_mock.call_args_list[6].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_channel_session_setup.py",
        "-q",
    ]
    assert run_mock.call_args_list[7].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_submission_check_mode.py",
        "-q",
    ]
    assert run_mock.call_args_list[8].args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/acceptance/test_scenario_feedback_iteration_after_check_mode.py",
        "-q",
    ]


def test_acceptance_runner_all_includes_l2_gate_and_l3_blocker_record(
    tmp_path: Path,
) -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(returncode=0, stdout="l1 ok", stderr="")

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1", "L2", "L3"),
            timeout_seconds=10,
        )

    assert report.status == "pass"
    assert [step.level for step in report.steps] == [
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L1",
        "L2",
        "L3",
    ]
    assert [step.status for step in report.steps] == [
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "pass",
        "not_started",
        "not_started",
        "pass",
    ]
    assert run_mock.call_count == 9


def test_acceptance_runner_level_without_implementation_is_not_started(
    tmp_path: Path,
) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L2",),
            timeout_seconds=10,
        )

    assert report.status == "not_started"
    assert report.steps[0].level == "L2"
    assert report.steps[0].status == "not_started"
    assert run_mock.call_count == 0


def test_acceptance_runner_l3_records_authorization_blocker(tmp_path: Path) -> None:
    with patch.dict(os.environ, {}, clear=True):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    assert report.status == "pass"
    assert report.steps[0].level == "L3"
    assert report.steps[0].name == "external_l3_submission_validation"
    assert report.steps[0].status == "pass"
    assert "explicit_user_authorization_required" in report.steps[0].message

    evidence_path = Path(report.steps[0].evidence)
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is False
    assert payload["live_blocker"]["reason"] == "explicit_user_authorization_required"
    assert "user_authorization" in payload["live_blocker"]["failed_checks"]
    assert (
        payload["live_blocker"]["diagnostics"]["submit_command_allowed"]
        is False
    )
    assert "job_url_present" in payload["live_blocker"]["diagnostics"]["missing_gates"]
    assert isinstance(
        payload["live_blocker"]["diagnostics"]["readiness_gates"],
        list,
    )
    assert (
        payload["live_blocker"]["diagnostics"]["live_input_artifacts"]["job_url"][
            "raw_value_persisted"
        ]
        is False
    )
    assert payload["coverage"]["user_authorized_external_session"] == "blocked_recorded"
    assert payload["coverage"]["post_submit_feedback_traceability"] == "pass"
    assert payload["coverage"]["no_secret_or_captcha_bypass"] == "pass"
    assert payload["rate_limit_policy"]["enabled"] is True
    assert payload["rate_limit_policy"]["max_per_batch"] == 5
    assert payload["rate_limit_policy"]["cooldown_seconds"] == 900
    assert payload["rate_limit_policy"]["daily_limit"] == 30
    assert payload["rate_limit_policy"]["state_path"].endswith(
        "outputs/submissions/liepin_rate_limit.json"
    )
    forbidden_audit = payload["forbidden_input_audit"]
    assert forbidden_audit["forbidden_inputs_present"] is False
    assert forbidden_audit["raw_values_persisted"] is False
    assert {
        item["name"] for item in forbidden_audit["inputs"]
    } == {"password", "captcha_code", "sms_code", "raw_api_key"}
    assert all(item["raw_value_persisted"] is False for item in forbidden_audit["inputs"])
    target_audit = payload["target_confirmation_audit"]
    assert target_audit["job_url_has_parseable_job_id"] is False
    assert target_audit["confirm_submit_job_id_present"] is False
    assert target_audit["job_id_matches_confirmation"] is False
    assert target_audit["raw_values_persisted"] is False
    input_artifacts = payload["live_input_artifacts"]
    assert input_artifacts["job_url"]["present"] is False
    assert input_artifacts["job_url"]["raw_value_persisted"] is False
    assert input_artifacts["confirmations"]["raw_values_persisted"] is False
    assert all(
        item["raw_content_persisted"] is False
        for item in input_artifacts["files"]
    )
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "blocked_before_command"
    assert submit_decision["submit_command_allowed"] is False
    assert submit_decision["external_submission_attempted"] is False
    assert submit_decision["authorization_confirmed"] is False
    assert submit_decision["final_submit_confirmed"] is False
    assert submit_decision["requires_explicit_user_authorization"] is True
    assert submit_decision["requires_separate_final_submit_confirmation"] is True
    assert submit_decision["credentials_or_challenge_inputs_accepted"] is False
    assert submit_decision["forbidden_inputs_present"] is False
    assert submit_decision["blocking_reason"] == "explicit_user_authorization_required"
    feedback_trace = payload["post_submit_feedback_traceability"]
    assert feedback_trace["traceable"] is True
    assert feedback_trace["source_type"] == "live_blocker"
    assert feedback_trace["source_status"] == "pre_submit_blocked"
    assert feedback_trace["source_reason"] == "explicit_user_authorization_required"
    assert (
        feedback_trace["feedback_iteration_route"]
        == "resolve_live_blocker_before_feedback_iteration"
    )
    readiness = payload["live_run_readiness"]
    assert readiness["ready"] is False
    assert readiness["submit_command_allowed"] is False
    assert readiness["blocking_reason"] == "explicit_user_authorization_required"
    assert "user_authorization" in readiness["missing_gates"]
    assert "job_url_present" in readiness["missing_gates"]
    assert "job_url_valid" in readiness["missing_gates"]
    assert "resume_pdf_file_ready" in readiness["missing_gates"]
    assert "profile_yaml_file_ready" in readiness["missing_gates"]
    handoff = payload["operator_handoff"]
    assert handoff["status"] == "blocked_until_operator_action"
    assert "显式授权" in handoff["next_action"]
    assert "password" in handoff["forbidden_inputs"]
    assert "captcha_code" in handoff["forbidden_inputs"]
    assert "PIPF_EXTERNAL_L3_RATE_LIMIT_MAX_PER_BATCH=5" in handoff["command_template"]
    required_env = {item["name"]: item for item in handoff["required_env"]}
    assert required_env["PIPF_EXTERNAL_L3_AUTHORIZED"]["present"] is False
    assert required_env["PIPF_EXTERNAL_L3_JOB_URL"]["present"] is False
    assert handoff["forbidden_input_audit"]["forbidden_inputs_present"] is False
    assert all("value" not in item for item in handoff["required_env"])
    authorization_packet = handoff["authorization_packet"]
    assert authorization_packet["status"] == "blocked_until_missing_gates_resolved"
    assert authorization_packet["raw_confirmation_values_persisted"] is False
    assert len(authorization_packet["required_confirmation_statements"]) >= 3
    assert "live_run_readiness" in authorization_packet["required_evidence"]
    assert "submit_safety_decision" in authorization_packet["required_evidence"]
    assert "password" in authorization_packet["operator_must_not_provide"]
    assert "captcha_code" in authorization_packet["operator_must_not_provide"]
    assert any(
        "当前缺失 gate" in item
        for item in authorization_packet["abort_conditions"]
    )
    assert all(
        "https://www.liepin.com/job/123.shtml" not in item
        for item in authorization_packet["required_confirmation_statements"]
    )
    markdown = (evidence_path.parent / "external-l3-validation.md").read_text(
        encoding="utf-8"
    )
    assert "# External L3 投递验证" in markdown
    assert "## Live Run Readiness" in markdown
    assert "- 是否允许启动 submit 命令: `False`" in markdown
    assert "## 最终提交安全决策" in markdown
    assert "- 决策: `blocked_before_command`" in markdown
    assert "## 真实输入产物审计" in markdown
    assert "- Job URL 原值是否持久化: `False`" in markdown
    assert "## 频控策略" in markdown
    assert "- 是否启用: `True`" in markdown
    assert "## 禁止输入审计" in markdown
    assert "- 禁止输入是否出现: `False`" in markdown
    assert "## 目标确认审计" in markdown
    assert "- URL 岗位 ID 与确认值是否一致: `False`" in markdown
    assert "| Gate | 状态 | 说明 |" in markdown
    assert "## 授权交接包" in markdown
    assert "### 授权确认包" in markdown
    assert "#### 必需确认声明" in markdown
    assert "#### 中止条件" in markdown
    assert "| 必需环境变量 | 是否存在 | 是否敏感 |" in markdown
    assert "## 提交后反馈追溯" in markdown
    assert "- 来源类型: `live_blocker`" in markdown


def test_acceptance_runner_l3_journey_report_records_live_blocker_rule(
    tmp_path: Path,
) -> None:
    with patch.dict(os.environ, {}, clear=True):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    assert journey_payload["status"] == "pass"
    external_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_result_or_blocker_recorded"
    )
    assert external_rule["level"] == "L3"
    assert external_rule["stage"] == "submissions"
    assert external_rule["status"] == "pass"
    assert "external-l3-validation.json" in external_rule["evidence"]
    assert "explicit_user_authorization_required" in external_rule["message"]
    safety_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submit_safety_decision_recorded"
    )
    assert safety_rule["level"] == "L3"
    assert safety_rule["stage"] == "submissions"
    assert safety_rule["status"] == "pass"
    assert "blocked_before_command" in safety_rule["message"]
    input_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_live_input_artifacts_fingerprinted"
    )
    assert input_rule["level"] == "L3"
    assert input_rule["stage"] == "submissions"
    assert input_rule["status"] == "pass"
    assert "真实输入产物审计" in input_rule["message"]
    rate_limit_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_rate_limit_policy_recorded"
    )
    assert rate_limit_rule["level"] == "L3"
    assert rate_limit_rule["stage"] == "submissions"
    assert rate_limit_rule["status"] == "pass"
    assert "频控策略" in rate_limit_rule["message"]
    forbidden_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_forbidden_inputs_rejected"
    )
    assert forbidden_rule["level"] == "L3"
    assert forbidden_rule["stage"] == "submissions"
    assert forbidden_rule["status"] == "pass"
    assert "禁止输入审计" in forbidden_rule["message"]
    target_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_target_confirmation_matches_url"
    )
    assert target_rule["level"] == "L3"
    assert target_rule["stage"] == "submissions"
    assert target_rule["status"] == "pass"
    assert "目标确认审计" in target_rule["message"]
    command_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_live_command_redacted"
    )
    assert command_rule["level"] == "L3"
    assert command_rule["stage"] == "submissions"
    assert command_rule["status"] == "pass"
    assert "命令" in command_rule["message"]
    output_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_live_output_redacted"
    )
    assert output_rule["level"] == "L3"
    assert output_rule["stage"] == "submissions"
    assert output_rule["status"] == "pass"
    assert "output" in output_rule["message"]
    feedback_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_post_submit_feedback_traceable"
    )
    assert feedback_rule["level"] == "L3"
    assert feedback_rule["stage"] == "submissions"
    assert feedback_rule["status"] == "pass"
    assert "live_blocker" in feedback_rule["message"]
    diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_post_command_blocker_diagnostics_recorded"
        )
    )
    assert diagnostics_rule["level"] == "L3"
    assert diagnostics_rule["stage"] == "submissions"
    assert diagnostics_rule["status"] == "pass"
    assert "post-command blocker" in diagnostics_rule["message"]
    summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_summary_recorded"
    )
    assert summary_rule["level"] == "L3"
    assert summary_rule["stage"] == "submissions"
    assert summary_rule["status"] == "pass"
    assert "submission log" in summary_rule["message"]
    log_redaction_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_raw_inputs_redacted"
    )
    assert log_redaction_rule["level"] == "L3"
    assert log_redaction_rule["stage"] == "submissions"
    assert log_redaction_rule["status"] == "pass"
    assert "未执行真实渠道命令" in log_redaction_rule["message"]
    authorization_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_authorization_packet_recorded"
    )
    assert authorization_rule["level"] == "L3"
    assert authorization_rule["stage"] == "submissions"
    assert authorization_rule["status"] == "pass"
    assert "授权确认包" in authorization_rule["message"]
    pre_submit_diagnostics_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_pre_submit_blocker_diagnostics_recorded"
        )
    )
    assert pre_submit_diagnostics_rule["level"] == "L3"
    assert pre_submit_diagnostics_rule["stage"] == "submissions"
    assert pre_submit_diagnostics_rule["status"] == "pass"
    assert "pre-submit blocker" in pre_submit_diagnostics_rule["message"]
    timeout_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_timeout_recorded_as_live_blocker"
    )
    assert timeout_rule["level"] == "L3"
    assert timeout_rule["stage"] == "submissions"
    assert timeout_rule["status"] == "pass"
    assert "超时" in timeout_rule["message"]
    command_error_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_command_error_recorded_as_live_blocker"
        )
    )
    assert command_error_rule["level"] == "L3"
    assert command_error_rule["stage"] == "submissions"
    assert command_error_rule["status"] == "pass"
    assert "启动错误" in command_error_rule["message"]


def test_acceptance_runner_l3_requires_separate_final_submit_confirmation(
    tmp_path: Path,
) -> None:
    with patch.dict(os.environ, {"PIPF_EXTERNAL_L3_AUTHORIZED": "true"}, clear=True):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["authorized"] is True
    assert payload["final_submit_confirmed"] is False
    assert (
        payload["live_blocker"]["reason"]
        == "explicit_final_submit_confirmation_required"
    )
    assert "final_submit_confirmation" in payload["live_blocker"]["failed_checks"]
    assert payload["coverage"]["user_authorized_external_session"] == "pass"
    assert payload["coverage"]["explicit_final_submit_gate"] == "blocked_recorded"
    readiness = payload["live_run_readiness"]
    assert readiness["ready"] is False
    assert "user_authorization" not in readiness["missing_gates"]
    assert "final_submit_confirmation" in readiness["missing_gates"]
    required_env = {
        item["name"]: item for item in payload["operator_handoff"]["required_env"]
    }
    assert required_env["PIPF_EXTERNAL_L3_AUTHORIZED"]["present"] is True
    assert (
        required_env["PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED"]["present"] is False
    )
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "blocked_before_command"
    assert submit_decision["authorization_confirmed"] is True
    assert submit_decision["final_submit_confirmed"] is False
    assert (
        submit_decision["blocking_reason"]
        == "explicit_final_submit_confirmation_required"
    )


def test_acceptance_runner_l3_rejects_forbidden_secret_or_challenge_inputs(
    tmp_path: Path,
) -> None:
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_PASSWORD": "do-not-store",
        "PIPF_EXTERNAL_L3_CAPTCHA_CODE": "123456",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is False
    assert payload["live_blocker"]["reason"] == "forbidden_external_l3_sensitive_inputs"
    assert payload["live_blocker"]["category"] == "safety"
    assert "forbidden_sensitive_inputs_absent" in payload["live_blocker"]["failed_checks"]
    assert "do-not-store" not in json.dumps(payload, ensure_ascii=False)
    assert "123456" not in json.dumps(payload, ensure_ascii=False)
    forbidden_audit = payload["forbidden_input_audit"]
    assert forbidden_audit["forbidden_inputs_present"] is True
    assert forbidden_audit["raw_values_persisted"] is False
    inputs = {item["name"]: item for item in forbidden_audit["inputs"]}
    assert inputs["password"]["present"] is True
    assert inputs["captcha_code"]["present"] is True
    assert inputs["sms_code"]["present"] is False
    assert all(item["raw_value_persisted"] is False for item in inputs.values())
    assert payload["submit_safety_decision"]["forbidden_inputs_present"] is True
    assert (
        payload["submit_safety_decision"]["credentials_or_challenge_inputs_accepted"]
        is False
    )
    readiness = payload["live_run_readiness"]
    assert "forbidden_sensitive_inputs_absent" in readiness["missing_gates"]
    diagnostics = payload["live_blocker"]["diagnostics"]["forbidden_input_audit"]
    assert diagnostics["forbidden_inputs_present"] is True
    assert run_mock.call_count == 0

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    forbidden_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_forbidden_inputs_rejected"
    )
    assert forbidden_rule["status"] == "pass"
    assert "阻断在 submit 命令前" in forbidden_rule["message"]


def test_acceptance_runner_l3_blocks_confirm_job_id_mismatch_before_submit(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123456789.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "987654321",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    payload_text = json.dumps(payload, ensure_ascii=False)
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is False
    assert payload["live_blocker"]["reason"] == "target_confirmation_mismatch"
    assert "target_job_id_matches_confirmation" in payload["live_blocker"]["failed_checks"]
    assert "123456789" not in payload_text
    assert "987654321" not in payload_text
    target_audit = payload["target_confirmation_audit"]
    assert target_audit["job_url_has_parseable_job_id"] is True
    assert target_audit["confirm_submit_job_id_present"] is True
    assert target_audit["job_id_matches_confirmation"] is False
    assert target_audit["raw_values_persisted"] is False
    assert (
        payload["submit_safety_decision"]["target_confirmation_audit"]
        == target_audit
    )
    readiness = payload["live_run_readiness"]
    assert "target_job_id_extractable" not in readiness["missing_gates"]
    assert "target_job_id_matches_confirmation" in readiness["missing_gates"]
    diagnostics = payload["live_blocker"]["diagnostics"]["target_confirmation_audit"]
    assert diagnostics["job_id_matches_confirmation"] is False
    assert run_mock.call_count == 0

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    target_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_target_confirmation_matches_url"
    )
    assert target_rule["status"] == "pass"
    assert "阻断 URL 岗位 ID 与确认岗位 ID 不一致" in target_rule["message"]


def test_acceptance_runner_l3_records_invalid_live_input_gates(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.txt"
    profile = tmp_path / "profile.json"
    resume.write_text("not a pdf\n", encoding="utf-8")
    profile.write_text("{}\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "invalid_live_resume_pdf"
    assert "resume_pdf_file_ready" in payload["live_blocker"]["failed_checks"]
    assert "profile_yaml_file_ready" in payload["live_blocker"]["failed_checks"]
    assert payload["external_submission_attempted"] is False
    assert run_mock.call_count == 0
    readiness = payload["live_run_readiness"]
    assert readiness["ready"] is False
    assert "resume_pdf_file_ready" in readiness["missing_gates"]
    assert "profile_yaml_file_ready" in readiness["missing_gates"]
    input_artifacts = payload["live_input_artifacts"]
    files = {item["id"]: item for item in input_artifacts["files"]}
    assert files["resume_pdf"]["suffix"] == ".txt"
    assert files["resume_pdf"]["suffix_valid"] is False
    assert files["resume_pdf"]["sha256"]
    assert files["profile_yaml"]["suffix"] == ".json"
    assert files["profile_yaml"]["suffix_valid"] is False
    assert files["profile_yaml"]["sha256"]
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "blocked_before_command"
    assert submit_decision["live_inputs_ready"] is False
    assert submit_decision["blocking_reason"] == "invalid_live_resume_pdf"


def test_acceptance_runner_l3_records_invalid_job_url_gate(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "ftp://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["live_blocker"]["reason"] == "invalid_live_job_url"
    assert run_mock.call_count == 0
    readiness = payload["live_run_readiness"]
    assert "job_url_valid" in readiness["missing_gates"]
    assert "resume_pdf_file_ready" not in readiness["missing_gates"]
    assert "profile_yaml_file_ready" not in readiness["missing_gates"]


def test_acceptance_runner_l3_blocks_disabled_rate_limit_policy(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
        "PIPF_EXTERNAL_L3_RATE_LIMIT_MAX_PER_BATCH": "0",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is False
    assert payload["live_blocker"]["reason"] == "invalid_external_l3_rate_limit_policy"
    assert payload["rate_limit_policy"]["enabled"] is False
    assert payload["rate_limit_policy"]["max_per_batch"] == 0
    assert (
        payload["live_blocker"]["diagnostics"]["rate_limit_policy"]["enabled"]
        is False
    )
    assert "rate_limit_policy_enabled" in payload["live_run_readiness"]["missing_gates"]
    assert "rate_limit_policy_enabled" in payload["live_blocker"]["failed_checks"]
    assert run_mock.call_count == 0


def test_acceptance_runner_l3_executes_live_command_only_after_all_gates(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "resume.pdf",
                            "suffix": ".pdf",
                            "size_bytes": len(b"%PDF-1.4\n"),
                            "sha256": hashlib.sha256(b"%PDF-1.4\n").hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "profile.yaml",
                            "suffix": ".yaml",
                            "size_bytes": len(b"id: profile\n"),
                            "sha256": hashlib.sha256(
                                b"id: profile\n"
                            ).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
        "PIPF_EXTERNAL_L3_HEADLESS": "true",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=(
                "submitted "
                "https://www.liepin.com/job/123.shtml "
                f"{resume} {profile} 123 Verifier\n"
                f"[DONE] submit log: {log_yaml}\n"
            ),
            stderr=(
                "trace "
                "https://www.liepin.com/job/123.shtml "
                f"{resume} {profile} 123 Verifier\n"
            ),
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "external_validated"
    assert payload["external_submission_attempted"] is True
    assert payload["command_redaction"]["raw_live_inputs_persisted"] is False
    assert "--job-url" in payload["command"]
    assert "https://www.liepin.com/job/123.shtml" not in payload["command"]
    assert str(resume) not in payload["command"]
    assert str(profile) not in payload["command"]
    assert "123" not in payload["command"]
    assert "Verifier" not in payload["command"]
    assert payload["command"].count("<redacted>") == 5
    assert payload["live_output_redaction"]["raw_live_inputs_persisted"] is False
    assert set(payload["live_output_redaction"]["redacted_fields"]) == {
        "job_url",
        "resume_pdf_path",
        "profile_path",
        "confirm_submit_job_id",
        "confirm_submit_recruiter",
    }
    assert "https://www.liepin.com/job/123.shtml" not in payload["stdout_tail"]
    assert str(resume) not in payload["stdout_tail"]
    assert str(profile) not in payload["stdout_tail"]
    assert "Verifier" not in payload["stdout_tail"]
    assert "https://www.liepin.com/job/123.shtml" not in payload["stderr_tail"]
    assert str(resume) not in payload["stderr_tail"]
    assert str(profile) not in payload["stderr_tail"]
    assert "Verifier" not in payload["stderr_tail"]
    assert payload["stdout_tail"].count("<redacted>") >= 5
    assert payload["stderr_tail"].count("<redacted>") >= 5
    assert payload["rate_limit_policy"]["enabled"] is True
    assert payload["rate_limit_policy"]["max_per_batch"] == 5
    assert payload["rate_limit_policy"]["cooldown_seconds"] == 900
    assert payload["rate_limit_policy"]["daily_limit"] == 30
    assert payload["coverage"]["explicit_final_submit_gate"] == "pass"
    target_audit = payload["target_confirmation_audit"]
    assert target_audit["job_url_has_parseable_job_id"] is True
    assert target_audit["confirm_submit_job_id_present"] is True
    assert target_audit["job_id_matches_confirmation"] is True
    assert target_audit["raw_values_persisted"] is False
    assert payload["submission_traceability"]["linked_to_validation"] is True
    assert payload["submission_traceability"]["log_links_back_to_validation"] is True
    assert (
        payload["submission_traceability"]["submission_log_input_artifacts_match"]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is True
    )
    assert (
        payload["submission_traceability"]["logged_external_l3_validation_run_id"]
        == "acceptance_external_l3"
    )
    assert (
        payload["submission_traceability"]["logged_external_l3_validation_path"]
        == validation_path
    )
    assert payload["submission_traceability"]["log_yaml_path"] == str(log_yaml)
    assert payload["submission_traceability"]["log_json_path"] == str(log_json)
    input_artifacts = payload["live_input_artifacts"]
    assert input_artifacts["job_url"]["scheme"] == "https"
    assert input_artifacts["job_url"]["hostname"] == "www.liepin.com"
    assert input_artifacts["job_url"]["raw_value_persisted"] is False
    assert input_artifacts["confirmations"]["confirm_submit_job_id_present"] is True
    assert input_artifacts["confirmations"]["raw_values_persisted"] is False
    files = {item["id"]: item for item in input_artifacts["files"]}
    assert files["resume_pdf"]["basename"] == "resume.pdf"
    assert files["resume_pdf"]["suffix_valid"] is True
    assert files["resume_pdf"]["sha256"] == hashlib.sha256(
        b"%PDF-1.4\n"
    ).hexdigest()
    assert files["profile_yaml"]["basename"] == "profile.yaml"
    assert files["profile_yaml"]["suffix_valid"] is True
    assert files["profile_yaml"]["sha256"] == hashlib.sha256(
        b"id: profile\n"
    ).hexdigest()
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "allowed_and_executed"
    assert submit_decision["submit_command_allowed"] is True
    assert submit_decision["external_submission_attempted"] is True
    assert submit_decision["authorization_confirmed"] is True
    assert submit_decision["final_submit_confirmed"] is True
    assert submit_decision["live_inputs_ready"] is True
    assert submit_decision["blocking_reason"] == ""
    assert submit_decision["post_run_blocker_reason"] == ""
    assert submit_decision["command_returncode"] == 0
    feedback_trace = payload["post_submit_feedback_traceability"]
    assert feedback_trace["traceable"] is True
    assert feedback_trace["source_type"] == "submission_log"
    assert feedback_trace["source_status"] == "external_validated"
    assert feedback_trace["source_artifact_path"] == str(log_json)
    assert feedback_trace["feedback_iteration_route"] == "feedback_iteration_after_check_mode"
    assert payload["live_run_readiness"]["ready"] is True
    assert payload["live_run_readiness"]["submit_command_allowed"] is True
    assert payload["live_run_readiness"]["missing_gates"] == []
    assert payload["operator_handoff"]["status"] == "executed_with_guarded_live_result"
    authorization_packet = payload["operator_handoff"]["authorization_packet"]
    assert authorization_packet["status"] == "executed"
    assert authorization_packet["raw_confirmation_values_persisted"] is False
    assert "live_input_artifacts" in authorization_packet["required_evidence"]
    assert run_mock.call_count == 1
    command = run_mock.call_args.args[0]
    assert "--submit" in command
    assert "--headless" in command
    assert "--confirm-submit-job-id" in command
    assert "--external-l3-validation-run-id" in command
    assert (
        command[command.index("--external-l3-validation-run-id") + 1]
        == "acceptance_external_l3"
    )
    assert "--external-l3-validation-path" in command
    assert (
        command[command.index("--external-l3-validation-path") + 1]
        == validation_path
    )
    assert "--rate-limit-max-per-batch" in command
    assert command[command.index("--rate-limit-max-per-batch") + 1] == "5"
    assert "--rate-limit-cooldown-seconds" in command
    assert command[command.index("--rate-limit-cooldown-seconds") + 1] == "900"
    assert "--rate-limit-daily-limit" in command
    assert command[command.index("--rate-limit-daily-limit") + 1] == "30"


def test_acceptance_runner_l3_blocks_submission_log_with_raw_live_inputs(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    validation_path = "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "job_url": "https://www.liepin.com/job/123.shtml",
                "resume_path": str(resume),
                "profile_path": str(profile),
                "live_inputs_redacted": False,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": {
                    "job_url": {
                        "present": True,
                        "scheme": "https",
                        "hostname": "www.liepin.com",
                        "supported_scheme": True,
                        "raw_value_persisted": False,
                    },
                    "files": [
                        {
                            "id": "resume_pdf",
                            "basename": "resume.pdf",
                            "suffix": ".pdf",
                            "size_bytes": len(resume_bytes),
                            "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                        {
                            "id": "profile_yaml",
                            "basename": "profile.yaml",
                            "suffix": ".yaml",
                            "size_bytes": len(profile_bytes),
                            "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                            "raw_content_persisted": False,
                        },
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert (
        payload["submission_traceability"]["submission_log_input_artifacts_match"]
        is True
    )
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is False
    )
    assert payload["submission_traceability"]["linked_to_validation"] is False
    assert (
        "submission_log_raw_live_inputs_redacted"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert (
        "submission_log_raw_live_inputs_redacted"
        in payload["live_blocker"]["failed_checks"]
    )


def test_acceptance_runner_l3_blocks_success_without_submission_log(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(returncode=0, stdout="[DONE] submit log: missing\n", stderr="")

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert payload["live_run_readiness"]["ready"] is True
    assert payload["live_run_readiness"]["submit_command_allowed"] is True
    assert payload["live_run_readiness"]["blocking_reason"] == ""
    assert payload["live_run_readiness"]["missing_gates"] == []
    assert payload["live_blocker"]["failed_checks"] == [
        "submission_log_hint_found",
        "submission_log_yaml_exists",
        "submission_log_json_exists",
        "submission_log_json_parseable",
        "external_l3_validation_run_id_matches",
        "external_l3_validation_path_matches",
        "input_artifacts_match_validation",
        "submission_log_raw_live_inputs_redacted",
    ]
    assert payload["live_blocker"]["diagnostics"]["returncode"] == 0
    assert (
        payload["live_blocker"]["diagnostics"][
            "submission_traceability_failed_checks"
        ]
        == payload["live_blocker"]["failed_checks"]
    )
    assert payload["submission_traceability"]["linked_to_validation"] is False
    assert "submission_log_hint_found" in payload["submission_traceability"]["failed_checks"]
    assert "submission_log_json_exists" in payload["submission_traceability"]["failed_checks"]
    submit_decision = payload["submit_safety_decision"]
    assert submit_decision["decision"] == "allowed_and_executed"
    assert submit_decision["submit_command_allowed"] is True
    assert submit_decision["post_run_blocker_reason"] == "submission_log_not_linked"
    feedback_trace = payload["post_submit_feedback_traceability"]
    assert feedback_trace["traceable"] is True
    assert feedback_trace["source_type"] == "live_blocker"
    assert feedback_trace["source_status"] == "external_submission_attempted_blocked"
    assert feedback_trace["source_reason"] == "submission_log_not_linked"


def test_acceptance_runner_l3_promotes_rate_limit_submission_log_summary(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "rate_limited"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume_bytes = b"%PDF-1.4\n"
    profile_bytes = b"id: profile\n"
    resume.write_bytes(resume_bytes)
    profile.write_bytes(profile_bytes)
    validation_path = (
        "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
    )
    input_artifacts = {
        "job_url": {
            "scheme": "https",
            "hostname": "www.liepin.com",
            "raw_value_persisted": False,
        },
        "files": [
            {
                "id": "resume_pdf",
                "basename": "resume.pdf",
                "suffix": ".pdf",
                "size_bytes": len(resume_bytes),
                "sha256": hashlib.sha256(resume_bytes).hexdigest(),
                "raw_content_persisted": False,
            },
            {
                "id": "profile_yaml",
                "basename": "profile.yaml",
                "suffix": ".yaml",
                "size_bytes": len(profile_bytes),
                "sha256": hashlib.sha256(profile_bytes).hexdigest(),
                "raw_content_persisted": False,
            },
        ],
    }
    log_yaml.write_text('status: "blocked"\nerror: "batch_cooldown"\n', encoding="utf-8")
    log_json.write_text(
        json.dumps(
            {
                "status": "blocked",
                "error": "batch_cooldown",
                "mode": "submit",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": validation_path,
                "input_artifacts": input_artifacts,
                "steps": [
                    {
                        "name": "rate_limit",
                        "status": "blocked",
                        "detail": (
                            "batch_cooldown; wait_seconds=385; "
                            "batch_count=5; daily_count=7"
                        ),
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=14,
            stdout=f"[INFO] log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["returncode"] == 14
    assert payload["live_blocker"]["reason"] == "external_channel_rate_limited"
    summary = payload["submission_traceability"]["submission_log_summary"]
    assert summary["status"] == "blocked"
    assert summary["error"] == "batch_cooldown"
    assert summary["mode"] == "submit"
    assert summary["last_step"]["name"] == "rate_limit"
    assert summary["last_step"]["status"] == "blocked"
    assert (
        payload["live_blocker"]["diagnostics"]["submission_log_summary"]
        == summary
    )
    assert payload["submission_traceability"]["linked_to_validation"] is True
    assert (
        payload["submission_traceability"]["submission_log_raw_live_inputs_redacted"]
        is True
    )
    assert payload["submit_safety_decision"]["post_run_blocker_reason"] == (
        "external_channel_rate_limited"
    )
    markdown = (
        Path(report.steps[0].evidence).parent / "external-l3-validation.md"
    ).read_text(encoding="utf-8")
    assert "- Submission Status: `blocked`" in markdown
    assert "- Submission Error: `batch_cooldown`" in markdown
    assert "- Last Step: `rate_limit/blocked`" in markdown

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    summary_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_submission_log_summary_recorded"
    )
    assert summary_rule["status"] == "pass"
    assert "blocked/batch_cooldown" in summary_rule["message"]


def test_acceptance_runner_l3_records_timeout_as_live_blocker(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["submit"],
            timeout=10,
            output=f"partial https://www.liepin.com/job/123.shtml {resume}",
            stderr=f"slow {profile} Verifier",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is True
    assert payload["command_timed_out"] is True
    assert payload["timeout_seconds"] == 10
    assert payload["returncode"] is None
    assert payload["live_blocker"]["reason"] == "external_channel_command_timed_out"
    assert payload["live_blocker"]["diagnostics"]["command_timed_out"] is True
    assert payload["live_blocker"]["diagnostics"]["timeout_seconds"] == 10
    assert payload["submit_safety_decision"]["post_run_blocker_reason"] == (
        "external_channel_command_timed_out"
    )
    assert "https://www.liepin.com/job/123.shtml" not in payload["stdout_tail"]
    assert str(resume) not in payload["stdout_tail"]
    assert str(profile) not in payload["stderr_tail"]
    assert "Verifier" not in payload["stderr_tail"]
    feedback_trace = payload["post_submit_feedback_traceability"]
    assert feedback_trace["source_type"] == "live_blocker"
    assert feedback_trace["source_status"] == "external_submission_attempted_blocked"
    assert feedback_trace["source_reason"] == "external_channel_command_timed_out"

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    timeout_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "external_l3_timeout_recorded_as_live_blocker"
    )
    assert timeout_rule["status"] == "pass"
    assert "超时已记录" in timeout_rule["message"]


def test_acceptance_runner_l3_records_command_error_as_live_blocker(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.side_effect = OSError(
            f"browser failed for https://www.liepin.com/job/123.shtml {resume}"
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert report.status == "pass"
    assert payload["status"] == "live_blocker_recorded"
    assert payload["external_submission_attempted"] is True
    assert payload["returncode"] is None
    assert payload["live_blocker"]["reason"] == (
        "external_channel_command_launch_failed"
    )
    command_error = payload["live_blocker"]["diagnostics"]["command_error"]
    assert command_error["type"] == "OSError"
    assert "https://www.liepin.com/job/123.shtml" not in command_error["message"]
    assert str(resume) not in command_error["message"]
    assert "<redacted>" in command_error["message"]
    assert payload["command_error"] == command_error
    assert payload["submit_safety_decision"]["post_run_blocker_reason"] == (
        "external_channel_command_launch_failed"
    )

    _, _, journey_json_path, _ = write_acceptance_report(tmp_path, report)
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    command_error_rule = next(
        step
        for step in journey_payload["steps"]
        if (
            step["rule_id"]
            == "external_l3_command_error_recorded_as_live_blocker"
        )
    )
    assert command_error_rule["status"] == "pass"
    assert "启动错误已记录" in command_error_rule["message"]


def test_acceptance_runner_l3_blocks_submission_log_without_matching_input_artifacts(
    tmp_path: Path,
) -> None:
    resume = tmp_path / "resume.pdf"
    profile = tmp_path / "profile.yaml"
    log_dir = tmp_path / "outputs" / "submissions" / "liepin" / "live"
    log_dir.mkdir(parents=True)
    log_yaml = log_dir / "submission_log.yaml"
    log_json = log_dir / "submission_log.json"
    resume.write_bytes(b"%PDF-1.4\n")
    profile.write_text("id: profile\n", encoding="utf-8")
    log_yaml.write_text('status: "success"\n', encoding="utf-8")
    log_json.write_text(
        json.dumps(
            {
                "status": "success",
                "job_url": "<redacted>",
                "resume_path": "<redacted>",
                "profile_path": "<redacted>",
                "live_inputs_redacted": True,
                "external_l3_validation_run_id": "acceptance_external_l3",
                "external_l3_validation_path": (
                    "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
                ),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "PIPF_EXTERNAL_L3_AUTHORIZED": "true",
        "PIPF_EXTERNAL_L3_FINAL_SUBMIT_CONFIRMED": "true",
        "PIPF_EXTERNAL_L3_JOB_URL": "https://www.liepin.com/job/123.shtml",
        "PIPF_EXTERNAL_L3_RESUME_PDF": str(resume),
        "PIPF_EXTERNAL_L3_PROFILE": str(profile),
        "PIPF_EXTERNAL_L3_CONFIRM_JOB_ID": "123",
        "PIPF_EXTERNAL_L3_CONFIRM_RECRUITER": "Verifier",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("tools.acceptance.external_l3.subprocess.run") as run_mock,
    ):
        run_mock.return_value = Mock(
            returncode=0,
            stdout=f"[DONE] submit log: {log_yaml}\n",
            stderr="",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_external_l3",
            levels=("L3",),
            timeout_seconds=10,
        )

    payload = json.loads(Path(report.steps[0].evidence).read_text(encoding="utf-8"))
    assert payload["status"] == "live_blocker_recorded"
    assert payload["live_blocker"]["reason"] == "submission_log_not_linked"
    assert payload["live_run_readiness"]["ready"] is True
    assert payload["live_run_readiness"]["submit_command_allowed"] is True
    assert payload["live_run_readiness"]["blocking_reason"] == ""
    assert payload["live_run_readiness"]["missing_gates"] == []
    assert payload["submission_traceability"]["log_links_back_to_validation"] is True
    assert (
        payload["submission_traceability"]["submission_log_input_artifacts_match"]
        is False
    )
    assert (
        "input_artifacts_match_validation"
        in payload["submission_traceability"]["failed_checks"]
    )
    assert payload["submission_traceability"]["linked_to_validation"] is False
    assert (
        "input_artifacts_match_validation"
        in payload["live_blocker"]["failed_checks"]
    )
    assert payload["live_blocker"]["diagnostics"]["log_yaml_path"] == str(log_yaml)
    assert payload["live_blocker"]["diagnostics"]["log_json_path"] == str(log_json)


def test_acceptance_runner_failure_returns_fail(tmp_path: Path) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=1, stdout="", stderr="boom")

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1",),
            timeout_seconds=10,
        )

    assert report.status == "fail"
    assert report.steps[0].status == "fail"
    assert "L1 scenario validation failed" in report.steps[0].message
    assert report.steps[0].stderr_tail.endswith("boom")


def test_acceptance_runner_timeout_returns_fail(tmp_path: Path) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        run_mock.side_effect = subprocess.TimeoutExpired(
            cmd=["pytest"],
            timeout=10,
            output="partial",
            stderr="slow",
        )

        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1",),
            timeout_seconds=10,
        )

    assert report.status == "fail"
    assert report.steps[0].status == "fail"
    assert "timed out" in report.steps[0].message
    assert report.steps[0].stdout_tail.endswith("partial")


def test_write_acceptance_report_outputs_json_markdown_and_journey_report(
    tmp_path: Path,
) -> None:
    with patch("tools.acceptance.acceptance_runner.subprocess.run") as run_mock:
        run_mock.return_value = Mock(returncode=0, stdout="l1 ok", stderr="")
        report = run_acceptance(
            root=tmp_path,
            run_id="acceptance_test",
            levels=("L1",),
            timeout_seconds=10,
        )

    json_path, markdown_path, journey_json_path, journey_markdown_path = (
        write_acceptance_report(tmp_path, report)
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert payload["summary"]["L1"] == "pass"
    assert payload["steps"][0]["name"] == "first_launch_configure_lm_studio"
    assert payload["steps"][1]["name"] == "setup_profile_and_material_library"

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# PiProofForge Acceptance Runner" in markdown
    assert "setup_profile_and_material_library" in markdown

    assert journey_json_path.name == "journey-report.json"
    assert journey_markdown_path.name == "journey-report.md"
    assert journey_json_path.exists()
    assert journey_markdown_path.exists()
    journey_payload = json.loads(journey_json_path.read_text(encoding="utf-8"))
    material_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "profile_and_materials_persisted"
    )
    assert material_rule["status"] == "pass"
    evidence_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "evidence_card_requires_review"
    )
    assert evidence_rule["status"] == "pass"
    job_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "job_target_ready_for_runs"
    )
    assert job_rule["status"] == "pass"
    quick_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "quick_run_outputs_are_traceable"
    )
    assert quick_rule["status"] == "pass"
    agent_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "agent_run_batch_is_guarded"
    )
    assert agent_rule["status"] == "pass"
    channel_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "channel_session_validity_is_positive_signal_based"
    )
    assert channel_rule["status"] == "pass"
    check_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "check_mode_never_final_submits"
    )
    assert check_rule["status"] == "pass"
    feedback_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "feedback_iteration_preserves_traceability"
    )
    assert feedback_rule["status"] == "pass"
    visible_rule = next(
        step
        for step in journey_payload["steps"]
        if step["rule_id"] == "lm_studio_visible_to_run_pages"
    )
    assert visible_rule["level"] == "L2"
    assert visible_rule["status"] == "not_started"


def test_build_run_id_uses_acceptance_prefix() -> None:
    assert build_run_id().startswith("acceptance_")
