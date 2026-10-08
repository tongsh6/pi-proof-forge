from unittest.mock import Mock

import pytest

from tools.infra.browser.liepin_session import LiepinSessionBrowser, observe_login_page


@pytest.mark.parametrize("url,positive,negative,valid", [
    ("https://www.liepin.com/", True, False, True),
    ("https://www.liepin.com/job/123.shtml", False, False, False),
    ("https://www.liepin.com/", True, True, False),
    ("https://passport.liepin.com/login/", True, False, False),
    ("https://liepin.com.example.org/", True, False, False),
])
def test_login_observation_requires_positive_owned_domain_signal(url, positive, negative, valid):
    page = Mock(url=url)
    page.locator.side_effect = lambda selector: Mock(count=lambda: int(positive if "nav-user-item" in selector else negative))
    observed = observe_login_page(page)
    assert bool(observed["login_signals"].get("authenticated_user_visible")) is valid


def test_owned_browser_reuses_context_and_closes_resources(tmp_path, monkeypatch):
    page = Mock(url="https://www.liepin.com/")
    page.is_closed.return_value = False
    page.locator.side_effect = lambda selector: Mock(count=lambda: int("手机号" in selector))
    context = Mock(pages=[page])
    playwright = Mock()
    playwright.chromium.launch_persistent_context.return_value = context
    browser = LiepinSessionBrowser()
    monkeypatch.setattr(browser, "_start_playwright", lambda: playwright)
    browser.start(tmp_path, "https://passport.liepin.com/login/")
    browser.start(tmp_path, "https://passport.liepin.com/login/")
    playwright.chromium.launch_persistent_context.assert_called_once()
    assert playwright.chromium.launch_persistent_context.call_args.kwargs["user_data_dir"] == str(tmp_path.resolve())
    browser.close()
    context.close.assert_called_once()
    playwright.stop.assert_called_once()


def test_navigation_failure_closes_owned_resources(tmp_path, monkeypatch):
    page = Mock()
    page.goto.side_effect = RuntimeError("navigation failed")
    context = Mock(pages=[page])
    playwright = Mock()
    playwright.chromium.launch_persistent_context.return_value = context
    browser = LiepinSessionBrowser()
    monkeypatch.setattr(browser, "_start_playwright", lambda: playwright)
    with pytest.raises(RuntimeError):
        browser.start(tmp_path, "https://passport.liepin.com/login/")
    context.close.assert_called_once()
    playwright.stop.assert_called_once()


def test_missing_profile_check_does_not_launch_browser(tmp_path, monkeypatch):
    browser = LiepinSessionBrowser()
    launcher = Mock()
    monkeypatch.setattr(browser, "_start_playwright", launcher)
    assert browser.check(tmp_path / "missing")["login_signals"] == {}
    launcher.assert_not_called()


def test_valid_check_releases_profile_for_delivery(tmp_path, monkeypatch):
    page = Mock(url="https://www.liepin.com/")
    page.is_closed.return_value = False
    page.locator.side_effect = lambda selector: Mock(count=lambda: int("nav-user-item" in selector))
    context = Mock(pages=[page])
    playwright = Mock()
    playwright.chromium.launch_persistent_context.return_value = context
    browser = LiepinSessionBrowser()
    monkeypatch.setattr(browser, "_start_playwright", lambda: playwright)
    browser.start(tmp_path, "https://passport.liepin.com/login/")
    assert browser.check(tmp_path)["login_signals"]["authenticated_user_visible"]
    context.close.assert_called_once()


def test_recheck_pumps_pending_navigation_before_reading_cached_url(tmp_path, monkeypatch):
    page = Mock(url="https://passport.liepin.com/login/")
    page.is_closed.return_value = False
    def locator(selector):
        result = Mock(count=lambda: int("nav-user-item" in selector))
        result.wait_for.side_effect = lambda **kwargs: setattr(page, "url", "https://www.liepin.com/")
        return result
    page.locator.side_effect = locator
    browser = LiepinSessionBrowser()
    browser._context = Mock(pages=[page])
    browser._playwright = Mock()
    browser._profile = tmp_path.resolve()
    assert browser.check(tmp_path)["login_signals"].get("authenticated_user_visible") is True


def test_close_tolerates_browser_already_closed_by_user():
    class TargetClosedError(Exception):
        pass
    browser = LiepinSessionBrowser()
    context, driver = Mock(), Mock()
    context.close.side_effect = TargetClosedError("already closed")
    browser._context, browser._playwright = context, driver
    browser.close()
    driver.stop.assert_called_once()


def test_start_rejects_a_page_without_usable_login_ui(tmp_path, monkeypatch):
    browser = LiepinSessionBrowser()
    page = Mock(url="https://www.liepin.com/")
    page.goto.return_value = Mock(status=200)
    page.locator.return_value.count.return_value = 0
    page.locator.return_value.first.wait_for.side_effect = RuntimeError("login form absent")
    monkeypatch.setattr(browser, "_page", lambda *args, **kwargs: page)
    with pytest.raises(RuntimeError, match="login form absent"):
        browser.start(tmp_path, "https://www.liepin.com/")


def test_start_accepts_existing_authenticated_page_without_opening_login(tmp_path, monkeypatch):
    browser = LiepinSessionBrowser()
    page = Mock(url="https://www.liepin.com/")
    page.goto.return_value = Mock(status=200)
    page.locator.side_effect = lambda selector: Mock(count=lambda: int("nav-user-item" in selector))
    monkeypatch.setattr(browser, "_page", lambda *args, **kwargs: page)
    assert browser.start(tmp_path, "https://www.liepin.com/") is True


def test_start_rejects_http_error_instead_of_waiting_for_login(tmp_path, monkeypatch):
    browser = LiepinSessionBrowser()
    page = Mock(url="https://www.liepin.com/")
    page.goto.return_value = Mock(status=404)
    monkeypatch.setattr(browser, "_page", lambda *args, **kwargs: page)
    with pytest.raises(RuntimeError, match="HTTP 404"):
        browser.start(tmp_path, "https://www.liepin.com/")


def test_start_opens_header_login_when_inline_form_is_absent(tmp_path, monkeypatch):
    from tools.infra.browser.liepin_session import LOGIN_PROMPTS
    browser = LiepinSessionBrowser()
    page = Mock(url="https://www.liepin.com/")
    page.goto.return_value = Mock(status=200)
    phone, entry = Mock(), Mock()
    phone.count.return_value = 0
    phone.first.wait_for.side_effect = lambda **kwargs: entry.first.click.assert_called_once()
    page.locator.side_effect = lambda selector: {
        LOGIN_PROMPTS: Mock(count=lambda: 1),
        "input[placeholder='手机号']:visible": phone,
        "#header-quick-menu-login": entry,
    }[selector]
    monkeypatch.setattr(browser, "_page", lambda *args, **kwargs: page)
    assert browser.start(tmp_path, "https://www.liepin.com/") is False
    phone.first.wait_for.assert_called_once()


def test_start_rejects_delayed_blank_redirect(tmp_path, monkeypatch):
    browser = LiepinSessionBrowser()
    page = Mock(url="https://www.liepin.com/")
    page.goto.return_value = Mock(status=200)
    page.locator.side_effect = lambda selector: Mock(count=lambda: int("手机号" in selector))
    page.wait_for_timeout.side_effect = lambda timeout: setattr(page, "url", "about:blank")
    monkeypatch.setattr(browser, "_page", lambda *args, **kwargs: page)
    with pytest.raises(RuntimeError, match="LOGIN_PAGE_REDIRECTED_TO_BLANK"):
        browser.start(tmp_path, "https://www.liepin.com/")


def test_check_reports_blank_redirect_without_reloading_it(tmp_path, monkeypatch):
    browser = LiepinSessionBrowser()
    browser._context = Mock()
    browser._playwright = Mock()
    page = Mock(url="about:blank")
    monkeypatch.setattr(browser, "_page", lambda *args, **kwargs: page)
    with pytest.raises(RuntimeError, match="LOGIN_PAGE_REDIRECTED_TO_BLANK"):
        browser.check(tmp_path)
    page.goto.assert_not_called()
