"""C5/C6：证据推断候选 UI、系统设置开关与 RPC 接线合同。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_evidence_page_renders_inference_candidates_with_actions():
    evidence = _source("ui/src/pages/evidence/index.tsx")
    for token in (
        "evidence-inference-run",
        "evidence-inference-batch",
        "evidence-inference-candidate",
        "evidence-inference-show-low",
        "inferEvidenceFields",
        "confirmEvidenceInference",
        "pages.evidence.reconcile.inference.acceptEdited",
        "pages.evidence.reconcile.inference.reject",
        "pages.evidence.reconcile.inference.disabledHint",
    ):
        assert token in evidence, token


def test_settings_page_has_inference_toggle_section():
    settings = _source("ui/src/pages/system-settings/index.tsx")
    for token in (
        "evidenceInference",
        "settings-evidence-inference",
        "evidence-inference-toggle",
        "updateEvidenceInferenceSetting",
        "pages.systemSettings.evidenceInference.enabledHint",
    ):
        assert token in settings, token


def test_api_and_types_expose_inference_contract():
    api = _source("ui/src/lib/sidecar/api.ts")
    for rpc in ('"evidence.inferFields"', '"evidence.confirmInference"', '"settings.update"'):
        assert rpc in api
    assert "section:\"evidence_inference\"" in api or "evidence_inference" in api
    types = _source("ui/src/lib/sidecar/types.ts")
    for token in ("EvidenceInferenceCandidate", "EvidenceInferenceCard", "EvidenceInferenceResult",
                  "EvidenceInferenceConfirmResult", "evidence_inference?"):
        assert token in types, token


def test_inference_i18n_keys_exist_in_both_catalogs():
    required = [
        "run", "running", "disabledHint", "summary", "highConfidence", "lowConfidence", "time", "role",
        "accept", "acceptEdited", "reject", "editLabel", "batchAccept", "batchAccepted", "accepted",
        "rejected", "showLow", "hideLow",
    ]
    for lang in ("zh", "en"):
        catalog = json.loads(_source(f"ui/src/i18n/{lang}.json"))
        inference = catalog["pages"]["evidence"]["reconcile"]["inference"]
        for key in required:
            assert inference.get(key), (lang, key)
        assert catalog["pages"]["systemSettings"]["nav"]["evidenceInference"]
        section = catalog["pages"]["systemSettings"]["evidenceInference"]
        for key in ("title", "subtitle", "enabled", "enabledHint", "note"):
            assert section.get(key), (lang, key)
        assert catalog["toasts"]["settings"]["evidenceInferenceSaved"]
