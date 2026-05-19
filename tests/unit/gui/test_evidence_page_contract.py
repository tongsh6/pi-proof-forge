import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PAGE = ROOT / "ui" / "src" / "pages" / "evidence" / "index.tsx"
NATIVE_VERIFY_CONTROLLER = (
    ROOT / "ui" / "src" / "components" / "shell" / "NativeVerifyController.tsx"
)
PACKAGE_JSON = ROOT / "ui" / "package.json"
VERIFY_SCRIPT = ROOT / "ui" / "scripts" / "verify_evidence_native.mjs"
TAURI_MAIN = ROOT / "ui" / "src-tauri" / "src" / "main.rs"
API_FILE = ROOT / "ui" / "src" / "lib" / "sidecar" / "api.ts"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_evidence_page_matches_product_card_contract():
    source = EVIDENCE_PAGE.read_text(encoding="utf-8")
    api_source = API_FILE.read_text(encoding="utf-8")

    for marker in (
        "evidence.load.ready",
        "evidenceStats",
        "EvidenceImportMode",
        "listEvidence(evidenceFilters",
        "importEvidence",
        "pages.evidence.filters.queryPlaceholder",
        "pages.evidence.artifacts.reupload",
        "pages.evidence.sections.detail",
        "pages.evidence.actions.import",
        "pages.evidence.status.ready",
    ):
        assert marker in source

    assert "evidence.import" in api_source
    assert "filters?: EvidenceFilters" in api_source


def test_evidence_native_verifier_is_registered():
    controller = NATIVE_VERIFY_CONTROLLER.read_text(encoding="utf-8")
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    tauri_main = TAURI_MAIN.read_text(encoding="utf-8")

    assert 'evidence: "/evidence"' in controller
    assert package["scripts"]["e2e:evidence"] == "node ./scripts/verify_evidence_native.mjs"
    assert "evidence.load.ready" in script
    assert "validateReadyEvent" in script
    assert "card_count" in script
    assert "artifact_count" in script
    assert '"evidence"' in tauri_main
    assert 'event_name.starts_with("evidence.")' in tauri_main


def test_evidence_i18n_contract_is_complete():
    required_keys = {
        "title",
        "subtitle",
        "listTitle",
        "listCount",
        "artifactFallback",
        "actions",
        "filters",
        "stats",
        "status",
        "score",
        "sections",
        "fields",
        "artifacts",
        "empty",
        "errors",
    }
    required_action_keys = {
        "new",
        "import",
        "refresh",
        "apply",
        "reset",
        "save",
        "saving",
        "delete",
        "deleting",
        "saved",
        "importing",
    }
    required_artifact_keys = {
        "title",
        "empty",
        "sourcePlaceholder",
        "modeCreate",
        "modeAppend",
        "modeReplace",
        "preview",
        "delete",
        "reupload",
        "size",
    }

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        evidence_messages = messages["pages"]["evidence"]
        missing = required_keys.difference(evidence_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"

        missing_actions = required_action_keys.difference(evidence_messages["actions"])
        assert not missing_actions, (
            f"{i18n_file.name} missing action keys: {sorted(missing_actions)}"
        )

        missing_artifacts = required_artifact_keys.difference(
            evidence_messages["artifacts"]
        )
        assert not missing_artifacts, (
            f"{i18n_file.name} missing artifact keys: {sorted(missing_artifacts)}"
        )
