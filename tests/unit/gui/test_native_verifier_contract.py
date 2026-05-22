from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
NATIVE_VERIFY_CONTROLLER = (
    ROOT / "ui" / "src" / "components" / "shell" / ("NativeVerify" + "Controller.tsx")
)
APP_SHELL = ROOT / "ui" / "src" / "components" / "shell" / "AppShell.tsx"
VERIFY_GLOB = "ver" + "ify_*" + "_native.mjs"
VERIFY_SCRIPTS = sorted((ROOT / "ui" / "scripts").glob(VERIFY_GLOB))
PACKAGE_JSON = ROOT / "ui" / "package.json"
RUNTIME_PATHS = [
    ROOT / "ui" / "src",
    ROOT / "ui" / "src-tauri" / "src",
]
FORBIDDEN_EMBEDDED_HOOKS = (
    "NativeVerify" + "Controller",
    "quick_run" + "_verify_event",
    "VI" + "TE_NATIVE" + "_" + "VER" + "IFY",
    "VI" + "TE_QUICK_RUN" + "_" + "VER" + "IFY_AUTORUN",
    "QUICK_RUN" + "_" + "VER" + "IFY_AUTORUN",
    "recordVerify" + "Event",
    "verify" + "Scenario",
    "system_settings.llm.deep_verify",
    "evidence.deep_verify",
    "jobs.deep_verify",
)


def test_native_verify_controller_is_removed_from_runtime_shell():
    assert not NATIVE_VERIFY_CONTROLLER.exists()

    app_shell = APP_SHELL.read_text(encoding="utf-8")
    assert ("NativeVerify" + "Controller") not in app_shell


def test_runtime_code_does_not_embed_acceptance_hooks():
    for path in RUNTIME_PATHS:
        for source_file in path.rglob("*"):
            if not source_file.is_file():
                continue
            if source_file.suffix not in {".ts", ".tsx", ".rs"}:
                continue
            source = source_file.read_text(encoding="utf-8")
            for marker in FORBIDDEN_EMBEDDED_HOOKS:
                assert marker not in source, f"{marker} leaked into {source_file}"


def test_embedded_gui_acceptance_entrypoints_are_removed():
    assert VERIFY_SCRIPTS == []

    package_json = PACKAGE_JSON.read_text(encoding="utf-8")
    assert ("e2e" + ":") not in package_json
    assert "verify_quick_run" not in package_json
    assert "verify_agent_run" not in package_json
    assert "verify_submissions" not in package_json
