import unittest

from tools.submission import liepin


class FakeElement:
    def __init__(self, attrs=None, text="") -> None:
        self.attrs = attrs or {}
        self.text = text
        self.clicked = False
        self.scrolled = False

    def get_attribute(self, name: str):
        return self.attrs.get(name)

    def inner_text(self, timeout=None):
        return self.text

    def scroll_into_view_if_needed(self, timeout=None):
        self.scrolled = True

    def click(self, timeout=None):
        self.clicked = True


class FakeLocator:
    def __init__(self, elements=None) -> None:
        self.elements = list(elements or [])

    def count(self):
        return len(self.elements)

    @property
    def first(self):
        return self.elements[0]

    def nth(self, index: int):
        return self.elements[index]

    def locator(self, selector: str):
        return self


class FakePage:
    def __init__(self, selector_map, url="https://www.liepin.com/job/123456.shtml") -> None:
        self.selector_map = selector_map
        self.url = url
        self.waits = []

    def locator(self, selector: str):
        return self.selector_map.get(selector, FakeLocator())

    def wait_for_timeout(self, timeout: int):
        self.waits.append(timeout)


class LiepinChatSendResumeTests(unittest.TestCase):
    def test_extract_liepin_job_id_from_job_url(self) -> None:
        self.assertEqual(
            liepin._extract_liepin_job_id("https://www.liepin.com/job/123456.shtml"),
            "123456",
        )

    def test_verify_main_chat_target_uses_main_button_and_ignores_recommended_button(self) -> None:
        main = FakeElement(
            attrs={
                "data-jobid": "123456",
                "data-params": '{"jobId": 123456, "recruiterName": "Sun"}',
            },
            text="继续聊",
        )
        recommended = FakeElement(attrs={"data-jobid": "999999"}, text="聊一聊")
        page = FakePage(
            {
                liepin.MAIN_CHAT_SELECTOR: FakeLocator([main]),
                "a[data-tlg-elem-id='c_pc_job_detail_like_chat_btn']": FakeLocator(
                    [recommended]
                ),
            }
        )

        result = liepin._verify_main_chat_target(
            page, "https://www.liepin.com/job/123456.shtml"
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.dom_jobid, "123456")
        self.assertEqual(result.params_jobid, "123456")
        self.assertEqual(result.recruiter_name, "Sun")

    def test_login_check_rejects_login_prompt_even_when_chat_button_exists(self) -> None:
        page = FakePage(
            {
                (
                    "[data-selector='chat-chat']:visible, "
                    "[data-selector='c-logout']:visible, "
                    ".recruiter-info-box:visible, "
                    ".nav-user-item:visible"
                ): FakeLocator([FakeElement(text="聊一聊")]),
                "a:has-text('登录'):visible, button:has-text('登录/注册'):visible": FakeLocator(
                    [FakeElement(text="登录/注册")]
                ),
            }
        )

        self.assertFalse(liepin._is_logged_in(page))

    def test_verify_main_chat_target_rejects_job_id_mismatch(self) -> None:
        page = FakePage(
            {
                liepin.MAIN_CHAT_SELECTOR: FakeLocator(
                    [
                        FakeElement(
                            attrs={
                                "data-jobid": "999999",
                                "data-params": '{"jobId": 999999}',
                            }
                        )
                    ]
                )
            }
        )

        result = liepin._verify_main_chat_target(
            page, "https://www.liepin.com/job/123456.shtml"
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "target_mismatch")

    def test_verify_main_chat_target_rejects_multiple_main_buttons_with_different_job_ids(self) -> None:
        page = FakePage(
            {
                liepin.MAIN_CHAT_SELECTOR: FakeLocator(
                    [
                        FakeElement(attrs={"data-jobid": "123456"}),
                        FakeElement(attrs={"data-jobid": "123457"}),
                    ]
                )
            }
        )

        result = liepin._verify_main_chat_target(
            page, "https://www.liepin.com/job/123456.shtml"
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "target_mismatch")

    def test_click_confirm_send_resume_prefers_modal_primary_button(self) -> None:
        confirm = FakeElement(text="确 定")
        page = FakePage(
            {
                ".ant-im-modal-confirm-btns button.ant-im-btn-primary:visible": FakeLocator(
                    [confirm]
                )
            }
        )

        ok, detail = liepin._click_confirm_send_resume(page, timeout_ms=5000)

        self.assertTrue(ok)
        self.assertTrue(confirm.clicked)
        self.assertEqual(detail, "confirm_modal_primary")

    def test_submit_safety_requires_explicit_job_and_recruiter_confirmation(self) -> None:
        config = liepin.LiepinSubmissionConfig(
            job_url="https://www.liepin.com/job/123456.shtml",
            resume_path="outputs/resume.pdf",
            profile_path="profiles/candidate_profile.yaml",
            headless=True,
            dry_run=False,
            submit=True,
            output_dir="outputs/submissions",
            session_dir="outputs/submissions",
            timeout_ms=45000,
        )
        verification = liepin.TargetVerification(
            ok=True,
            url_job_id="123456",
            dom_jobid="123456",
            params_jobid="123456",
            recruiter_name="Sun",
        )

        ok, detail = liepin._verify_submit_safety(config, verification)

        self.assertFalse(ok)
        self.assertEqual(detail, "submit_confirmation_missing")

    def test_submit_safety_rejects_non_pdf_resume(self) -> None:
        config = liepin.LiepinSubmissionConfig(
            job_url="https://www.liepin.com/job/123456.shtml",
            resume_path="outputs/v1.md",
            profile_path="profiles/candidate_profile.yaml",
            headless=True,
            dry_run=False,
            submit=True,
            output_dir="outputs/submissions",
            session_dir="outputs/submissions",
            timeout_ms=45000,
            confirm_submit_job_id="123456",
            confirm_submit_recruiter="Sun",
        )
        verification = liepin.TargetVerification(
            ok=True,
            url_job_id="123456",
            dom_jobid="123456",
            params_jobid="123456",
            recruiter_name="Sun",
        )

        ok, detail = liepin._verify_submit_safety(config, verification)

        self.assertFalse(ok)
        self.assertEqual(detail, "submit_resume_must_be_pdf")

    def test_submit_safety_accepts_matching_job_and_recruiter_confirmation(self) -> None:
        config = liepin.LiepinSubmissionConfig(
            job_url="https://www.liepin.com/job/123456.shtml",
            resume_path="outputs/resume.pdf",
            profile_path="profiles/candidate_profile.yaml",
            headless=True,
            dry_run=False,
            submit=True,
            output_dir="outputs/submissions",
            session_dir="outputs/submissions",
            timeout_ms=45000,
            confirm_submit_job_id="123456",
            confirm_submit_recruiter="Sun",
        )
        verification = liepin.TargetVerification(
            ok=True,
            url_job_id="123456",
            dom_jobid="123456",
            params_jobid="123456",
            recruiter_name="Sun",
        )

        ok, detail = liepin._verify_submit_safety(config, verification)

        self.assertTrue(ok)
        self.assertEqual(detail, "submit_confirmed:job_id=123456; recruiter=Sun")


if __name__ == "__main__":
    unittest.main()
