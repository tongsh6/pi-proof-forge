from __future__ import annotations

from pathlib import Path


def test_gui_defaults_to_chinese() -> None:
    i18n_file = Path("ui/src/i18n/index.ts")
    app_shell_store = Path("ui/src/state/app-shell-store.ts")
    source = i18n_file.read_text(encoding="utf-8")
    store_source = app_shell_store.read_text(encoding="utf-8")

    assert 'export const DEFAULT_LANGUAGE = "zh";' in source
    assert "lng: DEFAULT_LANGUAGE" in source
    assert "fallbackLng: DEFAULT_LANGUAGE" in source
    assert 'language: "zh"' in store_source
