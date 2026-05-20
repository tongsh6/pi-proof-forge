import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AGENT_RUN_PAGE = ROOT / "ui" / "src" / "pages" / "agent-run" / "index.tsx"
NATIVE_VERIFY_CONTROLLER = (
    ROOT / "ui" / "src" / "components" / "shell" / "NativeVerifyController.tsx"
)
PACKAGE_JSON = ROOT / "ui" / "package.json"
VERIFY_SCRIPT = ROOT / "ui" / "scripts" / "verify_agent_run_native.mjs"
TAURI_MAIN = ROOT / "ui" / "src-tauri" / "src" / "main.rs"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_agent_run_page_uses_run_control_rpc_contract():
    source = AGENT_RUN_PAGE.read_text(encoding="utf-8")

    assert "startAgentRun" in source
    assert "getAgentRun" in source
    assert "getSettings" in source
    assert "LlmConfig" in source
    assert "providerSummary" in source
    assert "stopAgentRun" in source
    assert "agent_run.load.ready" in source
    assert "agentStateLabel" in source
    assert "runStatusLabel" in source
    assert "pages.agentRun.providerSummary" in source
    assert "api_key.value" not in source
    assert "api_key.secret" not in source


def test_agent_run_page_renders_full_state_machine_contract():
    source = AGENT_RUN_PAGE.read_text(encoding="utf-8")

    for state in (
        "INIT",
        "DISCOVER",
        "SCORE",
        "GENERATE",
        "EVALUATE",
        "GATE",
        "REVIEW",
        "DELIVER",
        "LEARN",
        "DONE",
    ):
        assert state in source


def test_agent_run_native_verifier_is_registered():
    controller = NATIVE_VERIFY_CONTROLLER.read_text(encoding="utf-8")
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    script = VERIFY_SCRIPT.read_text(encoding="utf-8")
    tauri_main = TAURI_MAIN.read_text(encoding="utf-8")

    assert '"agent-run": "/agent-run"' in controller
    assert (
        package["scripts"]["e2e:agent-run"]
        == "node ./scripts/verify_agent_run_native.mjs"
    )
    assert "agent_run.load.ready" in script
    assert "validateReadyEvent" in script
    assert "profile_count" in script
    assert '"agent-run"' in tauri_main
    assert 'event_name.starts_with("agent_run.")' in tauri_main


def test_agent_run_i18n_contract_is_complete():
    required_keys = {
        "start",
        "startDryRun",
        "stop",
        "statusMachine",
        "gateTitle",
        "eventStream",
        "eventFallback",
        "runId",
        "startedAt",
        "currentRound",
        "jobProfile",
        "noRun",
        "noEvents",
        "providerSummary",
        "provider",
        "model",
        "baseUrl",
        "secretStatus",
    }
    required_state_keys = {
        "INIT",
        "DISCOVER",
        "SCORE",
        "GENERATE",
        "EVALUATE",
        "GATE",
        "REVIEW",
        "DELIVER",
        "LEARN",
        "DONE",
    }
    required_run_status_keys = {
        "idle",
        "running",
        "done",
        "dryRunComplete",
        "reviewPending",
        "failed",
        "stopped",
    }

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        agent_run_messages = messages["pages"]["agentRun"]
        missing = required_keys.difference(agent_run_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"

        missing_states = required_state_keys.difference(agent_run_messages["states"])
        assert not missing_states, (
            f"{i18n_file.name} missing state keys: {sorted(missing_states)}"
        )

        missing_statuses = required_run_status_keys.difference(
            agent_run_messages["runStatuses"]
        )
        assert not missing_statuses, (
            f"{i18n_file.name} missing run status keys: {sorted(missing_statuses)}"
        )
