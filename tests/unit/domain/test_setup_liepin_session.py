import inspect
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from tools import setup_liepin_session


class SetupLiepinSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = self.enterContext(TemporaryDirectory())

    def test_main_launches_playwright_persistent_chrome_profile(self) -> None:
        with patch.object(
            setup_liepin_session,
            "_setup_playwright_login_session",
            return_value=True,
        ) as setup_session:
            with patch("builtins.print"):
                code = setup_liepin_session.main(["--session-dir", self._tmp])

        self.assertEqual(code, 0)
        setup_session.assert_called_once()
        call_args = setup_session.call_args.kwargs
        self.assertEqual(str(call_args["session_root"]), f"{self._tmp}/liepin")
        self.assertEqual(call_args["browser_channel"], "chrome")
        self.assertFalse(call_args["headless"])

    def test_playwright_login_session_opens_liepin_in_persistent_context(self) -> None:
        page = Mock(url="https://www.liepin.com/")
        page.locator.return_value.count.return_value = 0
        context = Mock()
        context.pages = [page]
        chromium = Mock()
        chromium.launch_persistent_context.return_value = context
        playwright = Mock(chromium=chromium)
        sync_playwright = MagicMock()
        sync_playwright.return_value.__enter__.return_value = playwright

        with patch.object(setup_liepin_session, "_wait_for_login_confirmation"), (
            patch("builtins.print")
        ):
            ok = setup_liepin_session._setup_playwright_login_session(
                session_root=setup_liepin_session.Path(self._tmp) / "liepin",
                browser_channel="chrome",
                headless=False,
                timeout_ms=12_000,
                sync_playwright_factory=sync_playwright,
            )

        self.assertTrue(ok)
        chromium.launch_persistent_context.assert_called_once_with(
            user_data_dir=f"{self._tmp}/liepin",
            headless=False,
            channel="chrome",
        )
        page.goto.assert_called_once_with(
            "https://www.liepin.com/",
            wait_until="domcontentloaded",
            timeout=12_000,
        )
        context.close.assert_called_once()

    def test_browser_channel_can_be_disabled_for_bundled_chromium(self) -> None:
        page = Mock(url="https://www.liepin.com/")
        page.locator.return_value.count.return_value = 0
        context = Mock(pages=[page])
        chromium = Mock()
        chromium.launch_persistent_context.return_value = context
        playwright = Mock(chromium=chromium)
        sync_playwright = MagicMock()
        sync_playwright.return_value.__enter__.return_value = playwright

        with patch.object(setup_liepin_session, "_wait_for_login_confirmation"), (
            patch("builtins.print")
        ):
            ok = setup_liepin_session._setup_playwright_login_session(
                session_root=setup_liepin_session.Path(self._tmp) / "liepin",
                browser_channel="",
                headless=False,
                timeout_ms=12_000,
                sync_playwright_factory=sync_playwright,
            )

        self.assertTrue(ok)
        chromium.launch_persistent_context.assert_called_once_with(
            user_data_dir=f"{self._tmp}/liepin",
            headless=False,
        )

    def test_session_ready_rejects_login_page(self) -> None:
        page = Mock(url="https://passport.liepin.com/login")

        self.assertFalse(setup_liepin_session._is_session_ready(page))

    def test_session_ready_rejects_visible_login_prompt(self) -> None:
        page = Mock(url="https://www.liepin.com/")
        page.locator.return_value.count.return_value = 1

        self.assertFalse(setup_liepin_session._is_session_ready(page))

    def test_waits_for_login_confirmation_when_interactive(self) -> None:
        with patch.object(
            setup_liepin_session.sys.stdin,
            "isatty",
            return_value=True,
        ), patch("builtins.input") as prompt:
            setup_liepin_session._wait_for_login_confirmation()

        prompt.assert_called_once()

    def test_script_does_not_use_chrome_cookie_bridge_or_keychain(self) -> None:
        source = inspect.getsource(setup_liepin_session)

        self.assertNotIn("osascript", source)
        self.assertNotIn("AppleScript", source)
        self.assertNotIn("document.cookie", source)
        self.assertNotIn("Chrome Safe Storage", source)
        self.assertNotIn("find-generic-password", source)
        self.assertNotIn("sqlite3", source)
        self.assertNotIn("encrypted_value", source)


if __name__ == "__main__":
    _ = unittest.main()
