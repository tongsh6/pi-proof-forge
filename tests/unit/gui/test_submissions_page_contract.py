import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SUBMISSIONS_PAGE = ROOT / "ui" / "src" / "pages" / "submissions" / "index.tsx"
NATIVE_VERIFY_CONTROLLER = (
    ROOT / "ui" / "src" / "components" / "shell" / "NativeVerifyController.tsx"
)
PACKAGE_JSON = ROOT / "ui" / "package.json"
VERIFY_SCRIPT = ROOT / "ui" / "scripts" / "verify_submissions_native.mjs"
TAURI_MAIN = ROOT / "ui" / "src-tauri" / "src" / "main.rs"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_submissions_page_matches_product_log_contract():
    source = SUBMISSIONS_PAGE.read_text(encoding="utf-8")

    for marker in (
        "submissions.load.ready",
        "listSubmissions",
        "getSubmissionDetail",
        "retrySubmission",
        "screenshotSteps",
        "retryStrategy.sameChannel",
        "retryStrategy.fallbackEmail",
        "pages.submissions.timeline",
        "pages.submissions.screenshots.title",
    ):
        assert marker in source


def test_submissions_native_verifier_is_registered():
    controller = NATIVE_VERIFY_CONTROLLER.read_text(encoding="utf-8")
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    tauri_main = TAURI_MAIN.read_text(encoding="utf-8")

    assert 'submissions: "/submissions"' in controller
    assert (
        package["scripts"]["e2e:submissions"]
        == "node ./scripts/verify_submissions_native.mjs"
    )
    assert "submissions.load.ready" in script
    assert "validateReadyEvent" in script
    assert "submission_count" in script
    assert '"submissions"' in tauri_main
    assert 'event_name.starts_with("submissions.")' in tauri_main


def test_submissions_i18n_contract_is_complete():
    required_keys = {
        "title",
        "subtitle",
        "refresh",
        "stats",
        "runsTitle",
        "table",
        "detailTitle",
        "timeline",
        "screenshots",
        "failure",
        "retryStrategy",
        "status",
    }
    required_stat_keys = {"total", "delivered", "failed", "fallback"}
    required_retry_keys = {"sameChannel", "fallbackEmail"}
    required_screenshot_keys = {
        "title",
        "preview",
        "emptyPreview",
        "empty",
        "missing",
    }

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        submissions_messages = messages["pages"]["submissions"]
        missing = required_keys.difference(submissions_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"

        missing_stats = required_stat_keys.difference(submissions_messages["stats"])
        assert not missing_stats, (
            f"{i18n_file.name} missing stat keys: {sorted(missing_stats)}"
        )

        missing_retry = required_retry_keys.difference(
            submissions_messages["retryStrategy"]
        )
        assert not missing_retry, (
            f"{i18n_file.name} missing retry keys: {sorted(missing_retry)}"
        )

        missing_screenshots = required_screenshot_keys.difference(
            submissions_messages["screenshots"]
        )
        assert not missing_screenshots, (
            f"{i18n_file.name} missing screenshot keys: {sorted(missing_screenshots)}"
        )
