import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
JOBS_PAGE = ROOT / "ui" / "src" / "pages" / "jobs" / "index.tsx"
NATIVE_VERIFY_CONTROLLER = (
    ROOT / "ui" / "src" / "components" / "shell" / "NativeVerifyController.tsx"
)
PACKAGE_JSON = ROOT / "ui" / "package.json"
VERIFY_SCRIPT = ROOT / "ui" / "scripts" / "verify_jobs_native.mjs"
TAURI_MAIN = ROOT / "ui" / "src-tauri" / "src" / "main.rs"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_jobs_page_matches_product_center_contract():
    source = JOBS_PAGE.read_text(encoding="utf-8")

    for marker in (
        'type ActiveTab = "profiles" | "leads"',
        "profileStats",
        "jobs.load.ready",
        "listJobProfiles",
        "listJobLeads",
        "convertJobLead",
        "pages.jobs.tabs.${tab}",
        "pages.jobs.leads.detailTitle",
        "pages.jobs.actions.newProfile",
    ):
        assert marker in source


def test_jobs_native_verifier_is_registered():
    controller = NATIVE_VERIFY_CONTROLLER.read_text(encoding="utf-8")
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    tauri_main = TAURI_MAIN.read_text(encoding="utf-8")

    assert 'jobs: "/jobs"' in controller
    assert package["scripts"]["e2e:jobs"] == "node ./scripts/verify_jobs_native.mjs"
    assert "jobs.load.ready" in script
    assert "validateReadyEvent" in script
    assert "profile_count" in script
    assert "lead_count" in script
    assert '"jobs"' in tauri_main
    assert 'event_name.starts_with("jobs.")' in tauri_main


def test_jobs_i18n_contract_is_complete():
    required_keys = {
        "title",
        "subtitle",
        "detailTitle",
        "tabs",
        "stats",
        "newProfile",
        "actions",
        "filters",
        "status",
        "leadStatus",
        "metrics",
        "card",
        "empty",
        "fields",
        "leads",
        "errors",
    }
    required_action_keys = {
        "newProfile",
        "creating",
        "clearDraft",
        "save",
        "saving",
        "converting",
    }
    required_lead_keys = {
        "searchPlaceholder",
        "allStatuses",
        "favoriteOnly",
        "company",
        "position",
        "source",
        "status",
        "updatedAt",
        "action",
        "view",
        "detailTitle",
        "followUp",
        "favoritedHint",
        "defaultHint",
        "convert",
    }

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        jobs_messages = messages["pages"]["jobs"]
        missing = required_keys.difference(jobs_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"

        missing_actions = required_action_keys.difference(jobs_messages["actions"])
        assert not missing_actions, (
            f"{i18n_file.name} missing action keys: {sorted(missing_actions)}"
        )

        missing_leads = required_lead_keys.difference(jobs_messages["leads"])
        assert not missing_leads, (
            f"{i18n_file.name} missing lead keys: {sorted(missing_leads)}"
        )
