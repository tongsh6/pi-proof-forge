import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OVERVIEW_PAGE = ROOT / "ui" / "src" / "pages" / "overview" / "index.tsx"
NATIVE_VERIFY_CONTROLLER = (
    ROOT / "ui" / "src" / "components" / "shell" / "NativeVerifyController.tsx"
)
PACKAGE_JSON = ROOT / "ui" / "package.json"
VERIFY_SCRIPT = ROOT / "ui" / "scripts" / "verify_overview_native.mjs"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_overview_page_renders_product_dashboard_contract():
    source = OVERVIEW_PAGE.read_text(encoding="utf-8")

    for marker in (
        "useNavigate",
        "activityIconMap",
        "trendPath",
        "gapSummary",
        "overview.load.ready",
        "pages.overview.startAgent",
        "aria-label={t(\"pages.overview.matchTrend.chartLabel\")}",
    ):
        assert marker in source


def test_overview_native_verifier_is_registered():
    controller = NATIVE_VERIFY_CONTROLLER.read_text(encoding="utf-8")
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")

    assert 'overview: "/"' in controller
    assert package["scripts"]["e2e:overview"] == "node ./scripts/verify_overview_native.mjs"
    assert "overview.load.ready" in script
    assert "validateReadyEvent" in script


def test_overview_i18n_contract_is_complete():
    required_keys = {
        "title",
        "subtitle",
        "startAgent",
        "refresh",
        "gapCount",
        "viewAllGaps",
    }
    required_trend_keys = {"title", "subtitle", "chartLabel", "empty"}
    required_gap_keys = {"title", "subtitle", "none"}
    required_severity_keys = {"high", "medium", "low"}

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        overview_messages = messages["pages"]["overview"]
        missing = required_keys.difference(overview_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"

        missing_trend = required_trend_keys.difference(overview_messages["matchTrend"])
        assert not missing_trend, (
            f"{i18n_file.name} missing trend keys: {sorted(missing_trend)}"
        )

        missing_gap = required_gap_keys.difference(overview_messages["gaps"])
        assert not missing_gap, f"{i18n_file.name} missing gap keys: {sorted(missing_gap)}"

        missing_severity = required_severity_keys.difference(
            overview_messages["severity"]
        )
        assert not missing_severity, (
            f"{i18n_file.name} missing severity keys: {sorted(missing_severity)}"
        )
