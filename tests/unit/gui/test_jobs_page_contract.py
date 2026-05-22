import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
JOBS_PAGE = ROOT / "ui" / "src" / "pages" / "jobs" / "index.tsx"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_jobs_page_matches_product_center_contract():
    source = JOBS_PAGE.read_text(encoding="utf-8")

    for marker in (
        'type ActiveTab = "profiles" | "leads"',
        "profileStats",
        "listJobProfiles",
        "listJobLeads",
        "convertJobLead",
        "generateJobProfileDraft",
        "saveJobProfileDraft",
        "pages.jobs.tabs.${tab}",
        "pages.jobs.jdDraft.title",
        "pages.jobs.leads.detailTitle",
        "pages.jobs.actions.newProfile",
    ):
        assert marker in source


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
        "jdDraft",
    }
    required_action_keys = {
        "newProfile",
        "creating",
        "clearDraft",
        "save",
        "saving",
        "converting",
        "generateDraft",
        "generatingDraft",
        "saveIncomplete",
        "saveComplete",
    }
    required_jd_draft_keys = {
        "title",
        "subtitle",
        "jdPlaceholder",
        "sourceUrlPlaceholder",
        "ready",
        "incomplete",
        "missing",
        "none",
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
        missing_jd_draft = required_jd_draft_keys.difference(
            jobs_messages["jdDraft"]
        )
        assert not missing_jd_draft, (
            f"{i18n_file.name} missing jd draft keys: {sorted(missing_jd_draft)}"
        )
