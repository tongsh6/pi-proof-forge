from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
NATIVE_VERIFY_CONTROLLER = (
    ROOT / "ui" / "src" / "components" / "shell" / "NativeVerifyController.tsx"
)
VERIFY_SCRIPTS = sorted((ROOT / "ui" / "scripts").glob("verify_*_native.mjs"))


def test_native_verify_controller_requires_explicit_verify_flag():
    source = NATIVE_VERIFY_CONTROLLER.read_text(encoding="utf-8")

    assert 'import.meta.env.VITE_NATIVE_VERIFY === "1"' in source
    assert "import.meta.env.VITE_QUICK_RUN_VERIFY_AUTORUN" in source


def test_native_verifiers_do_not_write_vite_env_local():
    assert VERIFY_SCRIPTS

    for script in VERIFY_SCRIPTS:
        source = script.read_text(encoding="utf-8")
        assert 'VITE_NATIVE_VERIFY: "1"' in source, script.name
        assert "writeFileSync(VITE_ENV_LOCAL" not in source, script.name
        assert "readFileSync(VITE_ENV_LOCAL" not in source, script.name
