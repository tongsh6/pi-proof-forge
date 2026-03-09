import unittest
from importlib import import_module

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
    def test_liepin_dry_run_ok(self) -> None:
        channel = _liepin_class()()
        result = channel.deliver(_request("liepin"))
        self.assertIsInstance(result, Ok)

    def test_email_dry_run_ok(self) -> None:
        channel = _email_class()()
        result = channel.deliver(_request("email"))
        self.assertIsInstance(result, Ok)

    def test_deliver_with_fallback_uses_second_channel(self) -> None:
        base = _base_module()
        DeliveryRequest = base.DeliveryRequest
        deliver_with_fallback = base.deliver_with_fallback

        class FailingChannel:
            channel_id = "fail"

            def deliver(self, request):
                _ = request
                return Err(
                    ChannelFailure(
                        channel_id="fail",
                        reason="retryable",
                        details="temporary",
                    )
                )

        class SuccessChannel:
            channel_id = "ok"

            def deliver(self, request):
                _ = request
                from tools.domain.value_objects import DeliveryResult

                return Ok(
                    DeliveryResult(
                        channel_id="ok",
                        success=True,
                        submission_id="ok-1",
                        message="done",
                    )
                )

        req = DeliveryRequest(
            run_id="r1",
            candidate_id="c1",
            channel="liepin",
            resume_path="a.pdf",
            job_url="https://x",
            dry_run=False,
        )
        result = deliver_with_fallback(req, [FailingChannel(), SuccessChannel()])
        self.assertIsInstance(result, Ok)


if __name__ == "__main__":
    _ = unittest.main()
