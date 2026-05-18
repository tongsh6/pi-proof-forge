import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AGENT_RUN_PAGE = ROOT / "ui" / "src" / "pages" / "agent-run" / "index.tsx"
I18N_FILES = [
    ROOT / "ui" / "src" / "i18n" / "en.json",
    ROOT / "ui" / "src" / "i18n" / "zh.json",
]


def test_agent_run_page_uses_run_control_rpc_contract():
    source = AGENT_RUN_PAGE.read_text(encoding="utf-8")

    assert "startAgentRun" in source
    assert "getAgentRun" in source
    assert "stopAgentRun" in source


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


def test_agent_run_i18n_contract_is_complete():
    required_keys = {
        "start",
        "startDryRun",
        "stop",
        "statusMachine",
        "gateTitle",
        "eventStream",
        "runId",
        "startedAt",
        "currentRound",
        "jobProfile",
        "noRun",
        "noEvents",
    }

    for i18n_file in I18N_FILES:
        messages = json.loads(i18n_file.read_text(encoding="utf-8"))
        agent_run_messages = messages["pages"]["agentRun"]
        missing = required_keys.difference(agent_run_messages)
        assert not missing, f"{i18n_file.name} missing keys: {sorted(missing)}"
