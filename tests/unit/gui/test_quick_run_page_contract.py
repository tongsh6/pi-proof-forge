import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
QUICK_RUN_PAGE = ROOT / "ui" / "src" / "pages" / "quick-run" / "index.tsx"
PACKAGE_JSON = ROOT / "ui" / "package.json"
VERIFY_SCRIPT = ROOT / "ui" / "scripts" / "verify_quick_run_native.mjs"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_quick_run_page_renders_product_pipeline_contract():
    source = QUICK_RUN_PAGE.read_text(encoding="utf-8")

    for marker in (
        "stageStatusClass",
        "scoreBars",
        "terminalLines",
        "quick_run.load.ready",
        "quick_run.start.result",
        'data-automation-id="quick-run-start"',
        "pages.quickRun.stageOutput",
        "pages.quickRun.scores",
    ):
        assert marker in source

    assert "Agent (multi-round with gate)" not in source


def test_quick_run_native_verifier_is_registered():
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")

    assert package["scripts"]["e2e:quick-run"] == "node ./scripts/verify_quick_run_native.mjs"
    assert "quick_run.load.ready" in script
    assert "app_events" in script


def test_quick_run_i18n_contract_is_complete():
    required_keys = {
        "title",
        "subtitle",
        "selectProfile",
        "stageOutput",
        "scores",
        "waiting",
        "elapsed",
        "result",
        "noLogs",
    }
    required_score_keys = {"total", "empty"}

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        quick_run_messages = messages["pages"]["quickRun"]
        missing = required_keys.difference(quick_run_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"

        missing_scores = required_score_keys.difference(quick_run_messages["scoreLabels"])
        assert not missing_scores, (
            f"{i18n_file.name} missing score keys: {sorted(missing_scores)}"
        )
