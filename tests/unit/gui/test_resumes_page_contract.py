import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESUMES_PAGE = ROOT / "ui" / "src" / "pages" / "resumes" / "index.tsx"
NATIVE_VERIFY_CONTROLLER = (
    ROOT / "ui" / "src" / "components" / "shell" / "NativeVerifyController.tsx"
)
TAURI_MAIN = ROOT / "ui" / "src-tauri" / "src" / "main.rs"
PACKAGE_JSON = ROOT / "ui" / "package.json"
VERIFY_SCRIPT = ROOT / "ui" / "scripts" / "verify_resumes_native.mjs"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_resumes_page_renders_final_design_contract():
    source = RESUMES_PAGE.read_text(encoding="utf-8")

    for marker in (
        "pages.resumes.profile.title",
        "pages.resumes.uploaded.title",
        "pages.resumes.generated.title",
        "pages.resumes.preview.summary",
        "profile_completeness",
        "uploaded_count",
        "generated_count",
        "resume_count",
        "resumes.load.ready",
        "exportResumePdf",
        "uploadResume",
        "getResumePreview",
    ):
        assert marker in source


def test_resumes_native_verifier_is_registered():
    controller = NATIVE_VERIFY_CONTROLLER.read_text(encoding="utf-8")
    tauri_main = TAURI_MAIN.read_text(encoding="utf-8")
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")

    assert 'resumes: "/resumes"' in controller
    assert '"resumes"' in tauri_main
    assert 'event_name.starts_with("resumes.")' in tauri_main
    assert package["scripts"]["e2e:resumes"] == "node ./scripts/verify_resumes_native.mjs"
    assert "resumes.load.ready" in script
    assert "validateReadyEvent" in script


def test_resumes_i18n_contract_is_complete():
    required_keys = {
        "title",
        "subtitle",
        "refresh",
        "upload",
        "exportPdf",
        "exporting",
    }
    nested_keys = {
        "profile": {
            "title",
            "subtitle",
            "save",
            "completeness",
            "updatedAt",
            "missingTitle",
            "noMissing",
            "fields",
        },
        "uploaded": {
            "title",
            "count",
            "empty",
            "sourcePlaceholder",
            "labelPlaceholder",
            "submit",
            "uploading",
        },
        "generated": {"title", "count", "empty", "destinationPlaceholder", "score"},
        "preview": {"label", "summary", "experience", "skills", "pending", "empty"},
        "errors": {"sourcePathRequired", "selectResume", "destinationRequired"},
    }
    profile_fields = {"name", "phone", "email", "city", "current_position"}

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        resumes_messages = messages["pages"]["resumes"]
        missing = required_keys.difference(resumes_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"

        for group, keys in nested_keys.items():
            missing_group = keys.difference(resumes_messages[group])
            assert not missing_group, (
                f"{i18n_file.name} missing {group} keys: {sorted(missing_group)}"
            )

        missing_fields = profile_fields.difference(
            resumes_messages["profile"]["fields"]
        )
        assert not missing_fields, (
            f"{i18n_file.name} missing profile fields: {sorted(missing_fields)}"
        )
