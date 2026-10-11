import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SUBMISSIONS_PAGE = ROOT / "ui" / "src" / "pages" / "submissions" / "index.tsx"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_submissions_page_matches_product_log_contract():
    source = SUBMISSIONS_PAGE.read_text(encoding="utf-8")

    for marker in (
        "listSubmissions",
        "getChannelSession",
        "startChannelSession",
        "checkChannelSession",
        "clearChannelSession",
        "startSubmissionCheckMode",
        "listSubmissionFeedback",
        "createFeedbackIteration",
        "checkModeForm",
        "checkModeConfirmationItems",
        "final_submit_attempted",
        "jobLeadId",
        "resumeVersionId",
        "resumePdfPath",
        "getSubmissionDetail",
        "retrySubmission",
        "defaultSubmissionChannel",
        "screenshotSteps",
        "retryStrategy.sameChannel",
        "retryStrategy.fallbackEmail",
        "pages.submissions.session.manualBoundary",
        "pages.submissions.checkMode.boundary",
        "pages.submissions.feedback.boundary",
        "syncLiepinFeedback",
        "pages.submissions.platformFeedback.boundary",
        "pages.submissions.timeline",
        "pages.submissions.screenshots.title",
    ):
        assert marker in source


def test_submissions_i18n_contract_is_complete():
    required_keys = {
        "title",
        "subtitle",
        "refresh",
        "stats",
        "session",
        "checkMode",
        "feedback",
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
    required_session_keys = {
        "title",
        "manualBoundary",
        "channel",
        "start",
        "check",
        "clear",
        "statusLabel",
        "path",
        "log",
        "status",
    }
    required_session_status_keys = {
        "ready_to_setup",
        "waiting_for_manual_login",
        "session_valid",
        "login_required",
        "session_unknown",
        "session_cleared",
    }
    required_check_mode_keys = {
        "title",
        "boundary",
        "start",
        "running",
        "status",
        "jobLead",
        "jobLeadPlaceholder",
        "resume",
        "resumeVersion",
        "resumeVersionPlaceholder",
        "resumePathPlaceholder",
        "submit",
        "attempted",
        "skipped",
        "json",
        "steps",
    }
    required_feedback_keys = {
        "title",
        "boundary",
        "create",
        "recording",
        "items",
        "action",
        "version",
        "next",
        "record",
        "snapshot",
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

        missing_session = required_session_keys.difference(
            submissions_messages["session"]
        )
        assert not missing_session, (
            f"{i18n_file.name} missing session keys: {sorted(missing_session)}"
        )

        missing_session_status = required_session_status_keys.difference(
            submissions_messages["session"]["status"]
        )
        assert not missing_session_status, (
            f"{i18n_file.name} missing session status keys: {sorted(missing_session_status)}"
        )

        missing_check_mode = required_check_mode_keys.difference(
            submissions_messages["checkMode"]
        )
        assert not missing_check_mode, (
            f"{i18n_file.name} missing check mode keys: {sorted(missing_check_mode)}"
        )

        missing_feedback = required_feedback_keys.difference(
            submissions_messages["feedback"]
        )
        assert not missing_feedback, (
            f"{i18n_file.name} missing feedback keys: {sorted(missing_feedback)}"
        )
