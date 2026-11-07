import unittest
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import Mock, patch

import pytest

from tools.domain.result import Err, Ok
from tools.domain.value_objects import ChannelFailure


def _base_module():
    return import_module("tools.channels.base")


def _liepin_class():
    return import_module("tools.channels.liepin").LiepinChannel


def _email_class():
    return import_module("tools.channels.email").EmailChannel


def _request(channel: str = "liepin"):
    DeliveryRequest = _base_module().DeliveryRequest
    return DeliveryRequest(
        run_id="run-1",
        candidate_id="cand-1",
        channel=channel,
        resume_path="outputs/resume.pdf",
        job_url="https://example.com/job/1",
        dry_run=True,
    )


class ChannelTests(unittest.TestCase):
    def setUp(self) -> None:
        output_dir = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.dict(
            "os.environ", {"PPF_OUTPUT_DIR": output_dir, "PPF_SUBMIT_ENABLED": "0"}
        ))

    def test_liepin_dry_run_ok(self) -> None:
        channel = _liepin_class()()
        result = channel.deliver(_request("liepin"))
        self.assertIsInstance(result, Ok)
        self.assertFalse(result.value.success)

    def test_liepin_uses_explicit_session_dir_without_run_id_suffix(self) -> None:
        channel = _liepin_class()()
        DeliveryRequest = _base_module().DeliveryRequest
        sync_api = ModuleType("playwright.sync_api")
        sync_api.sync_playwright = object()
        req = DeliveryRequest(
            run_id="run-1",
            candidate_id="cand-1",
            channel="liepin",
            resume_path="outputs/resume.pdf",
            job_url="https://example.com/job/1",
            dry_run=False,
        )

        with patch.dict(
            "sys.modules",
            {
                "playwright": ModuleType("playwright"),
                "playwright.sync_api": sync_api,
            },
        ), patch.dict(
            "os.environ",
            {"PPF_LIEPIN_SESSION_DIR": "outputs/submissions/liepin/session"},
        ), patch(
            "tools.submission.liepin.run_liepin_submission",
            return_value=0,
        ) as run_submission:
            result = channel.deliver(req)

        self.assertIsInstance(result, Ok)
        self.assertFalse(result.value.success)
        config = run_submission.call_args.args[0]
        self.assertEqual(config.session_dir, "outputs/submissions/liepin/session")

    def test_liepin_submit_passes_explicit_confirmation_from_environment(self) -> None:
        channel = _liepin_class()()
        DeliveryRequest = _base_module().DeliveryRequest
        sync_api = ModuleType("playwright.sync_api")
        sync_api.sync_playwright = object()
        req = DeliveryRequest(
            run_id="run-1",
            candidate_id="cand-1",
            channel="liepin",
            resume_path="outputs/resume.pdf",
            job_url="https://www.liepin.com/job/123456.shtml",
            dry_run=False,
        )

        with patch.dict(
            "sys.modules",
            {
                "playwright": ModuleType("playwright"),
                "playwright.sync_api": sync_api,
            },
        ), patch.dict(
            "os.environ",
            {
                "PPF_SUBMIT_ENABLED": "1",
                "PPF_CONFIRM_SUBMIT_JOB_ID": "123456",
                "PPF_CONFIRM_SUBMIT_RECRUITER": "Sun",
            },
        ), patch(
            "tools.submission.liepin.run_liepin_submission",
            return_value=0,
        ) as run_submission:
            result = channel.deliver(req)

        self.assertIsInstance(result, Err)
        config = run_submission.call_args.args[0]
        self.assertTrue(config.submit)
        self.assertEqual(config.confirm_submit_job_id, "123456")
        self.assertEqual(config.confirm_submit_recruiter, "Sun")

    def test_email_dry_run_ok(self) -> None:
        channel = _email_class()()
        result = channel.deliver(_request("email"))
        self.assertIsInstance(result, Ok)
        self.assertFalse(result.value.success)

    def test_deliver_with_fallback_requires_matching_channel(self) -> None:
        channels = [_RecordingChannel("fail"), _RecordingChannel("ok")]
        result = _base_module().deliver_with_fallback(_request("liepin"), channels)

        self.assertIsInstance(result, Err)
        self.assertEqual(result.error.reason, "no_channel")
        self.assertEqual([channel.calls for channel in channels], [[], []])


class _RecordingChannel:
    def __init__(self, channel_id, result=None):
        self.channel_id = channel_id
        self.calls = []
        self.result = result

    def deliver(self, request):
        from tools.domain.value_objects import DeliveryResult

        self.calls.append(request)
        if self.result is not None:
            return self.result
        return Ok(DeliveryResult(self.channel_id, True, "local-result", "本地测试结果"))


def test_delivery_selects_only_requested_channel_instead_of_first_configured_channel():
    channels = [_RecordingChannel("email"), _RecordingChannel("liepin"), _RecordingChannel("boss")]
    request = replace(_request("boss"), dry_run=False)

    result = _base_module().deliver_with_fallback(request, channels)

    assert isinstance(result, Ok)
    assert result.value.channel_id == "boss"
    assert [channel.calls for channel in channels] == [[], [], [request]]


@pytest.mark.parametrize("reason", ["timeout", "network_error", "temporary_failure", "retryable", "submission_uncertain"])
def test_delivery_failure_never_retries_duplicate_channel_or_falls_back_to_email(reason):
    failure = Err(ChannelFailure("liepin", reason, "结果不能确认"))
    channels = [_RecordingChannel("liepin", failure), _RecordingChannel("liepin"), _RecordingChannel("email")]
    request = replace(_request(), dry_run=False)

    result = _base_module().deliver_with_fallback(request, channels)

    assert result is failure
    assert [channel.calls for channel in channels] == [[request], [], []]


def test_delivery_unconfirmed_result_never_retries_or_falls_back():
    from tools.domain.value_objects import DeliveryResult

    unconfirmed = Ok(DeliveryResult("liepin", False, "", "结果未知"))
    channels = [_RecordingChannel("liepin", unconfirmed), _RecordingChannel("email")]
    request = replace(_request(), dry_run=False)

    result = _base_module().deliver_with_fallback(request, channels)

    assert result is unconfirmed
    assert [channel.calls for channel in channels] == [[request], []]


def test_liepin_missing_browser_dependency_is_failure() -> None:
    with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
        result = _liepin_class()().deliver(replace(_request(), dry_run=False))
    assert isinstance(result, Err)
    assert result.error.reason == "playwright_missing"


@pytest.mark.parametrize(
    ("mode", "status", "error", "submit_status", "expected_success"),
    [
        ("submit", "success", "", "success", True),
        ("check", "success", "", "skipped", False),
        ("submit", "uncertain", "", "uncertain", False),
        ("submit", "success", "unexpected_error", "success", False),
        ("submit", "success", "", "missing", False),
    ],
)
def test_liepin_requires_current_persisted_success_record(
    tmp_path: Path,
    mode: str,
    status: str,
    error: str,
    submit_status: str,
    expected_success: bool,
) -> None:
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = object()

    def record_browser_outcome(config, *, recorder=None):
        # 只替代外部浏览器边界；使用真实 recorder 写入本次调用的结果。
        if recorder is not None:
            recorder.record.mode = mode
            for name in (
                "rate_limit", "login_check", "target_verify",
                "submit_safety", "chat_send_resume",
            ):
                recorder.add_step(name, "success", "已验证")
            if submit_status != "missing":
                recorder.add_step("submit", submit_status, "结果已记录")
            recorder.finish(status, error=error)
        return 0

    with patch.dict(
        "sys.modules",
        {"playwright": ModuleType("playwright"), "playwright.sync_api": sync_api},
    ), patch.dict(
        "os.environ",
        {"PPF_OUTPUT_DIR": str(tmp_path), "PPF_SUBMIT_ENABLED": "1"},
        clear=True,
    ), patch(
        "tools.submission.liepin.run_liepin_submission", side_effect=record_browser_outcome,
    ):
        result = _liepin_class()().deliver(replace(_request(), dry_run=False))

    if expected_success:
        assert isinstance(result, Ok)
        assert result.value.success is True
        assert list(tmp_path.rglob("submission_log.json"))
    else:
        assert isinstance(result, Err)
        assert result.error.reason == "submission_uncertain"


def test_unverified_attachment_is_not_retried_through_email(tmp_path):
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = object()
    fallback = Mock()
    with patch.dict("sys.modules", {"playwright": ModuleType("playwright"), "playwright.sync_api": sync_api}), patch.dict(
        "os.environ", {"PPF_OUTPUT_DIR": str(tmp_path), "PPF_SUBMIT_ENABLED": "1"}, clear=True,
    ), patch("tools.submission.liepin.run_liepin_submission", return_value=16):
        result = _base_module().deliver_with_fallback(replace(_request(), dry_run=False), [_liepin_class()(), fallback])

    assert isinstance(result, Err)
    assert result.error.reason == "resume_attachment_binding_unverified"
    fallback.deliver.assert_not_called()


def test_liepin_reuses_app_profile_unless_session_override_is_configured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app_profile = tmp_path / "outputs/channel_sessions/liepin/browser_profile"
    app_profile.mkdir(parents=True)
    sync_api = ModuleType("playwright.sync_api")
    sync_api.sync_playwright = object()
    with patch.dict("sys.modules", {"playwright": ModuleType("playwright"), "playwright.sync_api": sync_api}), patch.dict("os.environ", {}, clear=True), patch("tools.submission.liepin.run_liepin_submission", return_value=0) as run:
        _liepin_class()().deliver(replace(_request(), dry_run=False))
        assert run.call_args.args[0].session_profile_path == str(app_profile)
        with patch.dict("os.environ", {"PPF_LIEPIN_SESSION_DIR": str(tmp_path / "explicit")}):
            _liepin_class()().deliver(replace(_request(), dry_run=False))
            assert run.call_args.args[0].session_profile_path == ""


if __name__ == "__main__":
    _ = unittest.main()
