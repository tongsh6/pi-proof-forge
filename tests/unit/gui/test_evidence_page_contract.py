import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_PAGE = ROOT / "ui" / "src" / "pages" / "evidence" / "index.tsx"
API_FILE = ROOT / "ui" / "src" / "lib" / "sidecar" / "api.ts"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_evidence_page_matches_product_card_contract():
    source = EVIDENCE_PAGE.read_text(encoding="utf-8")
    api_source = API_FILE.read_text(encoding="utf-8")

    for marker in (
        "evidenceStats",
        "EvidenceImportMode",
        "listEvidence(evidenceFilters",
        "importEvidence",
        "pages.evidence.filters.queryPlaceholder",
        "pages.evidence.artifacts.reupload",
        "pages.evidence.sections.detail",
        "pages.evidence.actions.import",
        "pages.evidence.status.ready",
        "listEvidenceMaterialSources",
        "generateEvidenceDraft",
        "saveEvidenceDraft",
        "materialSources",
        "pages.evidence.materialSources.title",
        "pages.evidence.actions.generateDraft",
        "pages.evidence.review.title",
    ):
        assert marker in source

    assert "evidence.import" in api_source
    assert "evidence.listMaterialSources" in api_source
    assert "evidence.generateDraft" in api_source
    assert "evidence.saveDraft" in api_source
    assert "filters?: EvidenceFilters" in api_source


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
        "materialSources",
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
        "generateDraft",
        "generatingDraft",
        "saveIncomplete",
        "saveEligible",
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
    required_material_source_keys = {
        "title",
        "count",
        "source",
        "empty",
        "noPreview",
        "selectPlaceholder",
        "select",
    }
    required_review_keys = {
        "title",
        "source",
        "missing",
        "eligible",
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
        missing_material_sources = required_material_source_keys.difference(
            evidence_messages["materialSources"]
        )
        assert not missing_material_sources, (
            f"{i18n_file.name} missing material source keys: {sorted(missing_material_sources)}"
        )
        missing_review = required_review_keys.difference(evidence_messages["review"])
        assert not missing_review, (
            f"{i18n_file.name} missing review keys: {sorted(missing_review)}"
        )
