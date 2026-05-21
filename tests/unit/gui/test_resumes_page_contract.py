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
        "uploadMaterial",
        "listMaterials",
        "getMaterialReadiness",
        "material_count",
        "material_readiness",
        "pages.resumes.materials.title",
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
    assert "material_count" in script
    assert "material_readiness" in script


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
        "materials": {
            "title",
            "count",
            "empty",
            "upload",
            "sourcePlaceholder",
            "labelPlaceholder",
            "submit",
            "uploading",
            "readiness",
            "ready",
            "incomplete",
            "noMissing",
            "noPreview",
            "missing",
        },
        "generated": {"title", "count", "empty", "destinationPlaceholder", "score"},
        "preview": {"label", "summary", "experience", "skills", "pending", "empty"},
        "errors": {
            "sourcePathRequired",
            "materialSourcePathRequired",
            "selectResume",
            "destinationRequired",
        },
    }
    profile_fields = {"name", "phone", "email", "city", "current_position"}
    material_missing_keys = {
        "missing_personal_profile",
        "missing_uploaded_resume",
        "missing_raw_work_material",
    }

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
        missing_materials = material_missing_keys.difference(
            resumes_messages["materials"]["missing"]
        )
        assert not missing_materials, (
            f"{i18n_file.name} missing material readiness keys: {sorted(missing_materials)}"
        )
