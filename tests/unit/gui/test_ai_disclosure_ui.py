"""AI 投递声明：系统开关、投递链路、双语文案与运行时接线合同。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_settings_page_has_ai_disclosure_toggle_section():
    settings = _source("ui/src/pages/system-settings/index.tsx")
    for token in (
        "aiDisclosure",
        "settings-ai-disclosure",
        "ai-disclosure-toggle",
        "ai-disclosure-preview",
        "updateAiDisclosureSetting",
        "pages.systemSettings.aiDisclosure.enabledHint",
    ):
        assert token in settings, token


def test_api_and_types_expose_ai_disclosure_contract():
    api = _source("ui/src/lib/sidecar/api.ts")
    assert 'section:"ai_disclosure"' in api
    assert "ai_disclosure_enabled" in api
    types = _source("ui/src/lib/sidecar/types.ts")
    for token in ("ai_disclosure?: { enabled: boolean; text: string }", "ai_disclosure"):
        assert token in types, token


def test_submissions_shows_disclosure_state_before_send():
    page = _source("ui/src/pages/submissions/index.tsx")
    for token in ("native-pdf-ai-disclosure", "aiDisclosureSent", "aiDisclosurePending",
                  "nativePdf.ai_disclosure_enabled"):
        assert token in page, token


def test_i18n_keys_exist_in_both_catalogs():
    for lang in ("zh", "en"):
        catalog = json.loads(_source(f"ui/src/i18n/{lang}.json"))
        assert catalog["pages"]["systemSettings"]["nav"]["aiDisclosure"]
        section = catalog["pages"]["systemSettings"]["aiDisclosure"]
        for key in ("title", "subtitle", "enabled", "enabledHint", "previewLabel", "previewFallback", "note"):
            assert section.get(key), (lang, key)
        assert catalog["toasts"]["settings"]["aiDisclosureSaved"]
        native = catalog["pages"]["submissions"]["nativePdf"]
        assert native["aiDisclosureSent"]
        assert native["aiDisclosurePending"]


def test_statement_is_fixed_short_and_discloses_automation():
    from tools.infra.ai_disclosure import AI_DISCLOSURE_TEXT, disclosure_sha256

    assert "AI" in AI_DISCLOSURE_TEXT
    assert "投递" in AI_DISCLOSURE_TEXT
    assert len(AI_DISCLOSURE_TEXT) <= 200
    assert len(disclosure_sha256()) == 64
    source = _source("tools/infra/ai_disclosure.py")
    assert "投递操作均由 AI 自动化执行" in source
    assert "人工" not in AI_DISCLOSURE_TEXT


def test_delivery_flow_requires_and_records_disclosure_before_send():
    flow = _source("tools/sidecar/handlers/native_pdf.py")
    for token in (
        "requires_ai_disclosure",
        "def _disclosure_observation_matches",
        "def _disclosure_recorded",
        "'ai_disclosure'",
        "recorder.add_step('ai_disclosure','success'",
    ):
        assert token in flow, token
    assert "requires_ai_disclosure" in _source("ui/src-tauri/src/liepin_webview.rs")
    assert "ai_disclosure_not_confirmed" in _source("ui/src-tauri/src/liepin_webview.rs")
    assert "liepin_native_ai_disclosure.js" in _source("ui/src-tauri/src/liepin_webview.rs")
    assert "probeAiDisclosureDryRun" in _source("ui/src-tauri/src/main.rs")
    assert "AI 投递声明" in _source("ui/design/DESIGN.md")
