import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RESUMES_PAGE = ROOT / "ui" / "src" / "pages" / "resumes" / "index.tsx"
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
        "pages.resumes.exportedTo",
        "exportResumePdf",
        "uploadResume",
        "pages.resumes.uploaded.chooseFile",
        "getResumePreview",
        "uploadMaterial",
        "pages.resumes.materials.chooseFile",
        "listMaterials",
        "getMaterialReadiness",
        "pages.resumes.materials.title",
    ):
        assert marker in source


def test_resumes_i18n_contract_is_complete():
    required_keys = {
        "title",
        "subtitle",
        "refresh",
        "upload",
        "exportPdf",
        "exporting",
        "exportedTo",
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
            "chooseFile",
            "selectedFile",
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
            "chooseFile",
            "selectedFile",
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
