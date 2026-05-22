from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tools.acceptance.journey_contract import load_journey_contract
from tools.acceptance.journey_report import (
    JourneyStepResult,
    build_journey_report,
    write_journey_report,
)
from tools.sidecar.handlers.evidence import (
    handle_evidence_generate_draft,
    handle_evidence_get,
    handle_evidence_save_draft,
)
from tools.sidecar.handlers.materials import handle_evidence_list_material_sources


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"


def _write_uploaded_markdown_material(materials_dir: Path) -> None:
    materials_dir.mkdir(parents=True, exist_ok=True)
    (materials_dir / "mat_checkout.md").write_text(
        "# Checkout Reliability\n\n"
        "I improved payment retry handling and reduced payment failure rate by 43%.\n",
        encoding="utf-8",
    )
    (materials_dir / "mat_checkout.meta.yaml").write_text(
        "\n".join(
            [
                'material_id: "mat_checkout"',
                'resource_id: "res_checkout"',
                'label: "Checkout Work Log"',
                'kind: "raw_work_material"',
                'filename: "mat_checkout.md"',
                'extension: ".md"',
                'uploaded_at: "2026-05-21T00:00:00Z"',
                'preview: "I improved payment retry handling and reduced payment failure rate by 43%."',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _llm_response(content: object) -> dict[str, object]:
    return {"choices": [{"message": {"content": json.dumps(content)}}]}


def test_generate_review_and_complete_evidence_card_l1_acceptance_writes_report(
    tmp_path: Path,
) -> None:
    materials_dir = tmp_path / "materials"
    evidence_dir = tmp_path / "evidence_cards"
    policy_path = tmp_path / "policy.yaml"
    _write_uploaded_markdown_material(materials_dir)
    policy_path.write_text(
        "\n".join(
            [
                'llm_provider: "lm_studio"',
                'llm_model: "local-model"',
                'llm_base_url: "http://127.0.0.1:1234/v1"',
                'llm_timeout: "60"',
                'llm_temperature: "0.2"',
                'llm_api_key_configured: "true"',
                'llm_api_key_placeholder: "lm-studio"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    complete_llm_payload = {
        "source_material_ids": ["mat_checkout"],
        "title": "Checkout reliability",
        "context": "Checkout incident follow-up",
        "actions": ["Improved payment retry handling"],
        "results": ["reduced payment failure rate by 43%"],
        "artifacts": [
            {
                "type": "markdown_document",
                "ref": "mat_checkout",
                "label": "Checkout work log",
            }
        ],
        "stack": ["Python"],
        "tags": ["reliability"],
    }

    with (
        patch("tools.sidecar.handlers.materials._MATERIALS_DIR", materials_dir),
        patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir),
        patch(
            "tools.sidecar.handlers.settings._resolve_policy_path",
            return_value=policy_path,
        ),
        patch(
            "tools.sidecar.handlers.evidence.LLMClient.post_json",
            return_value=_llm_response(complete_llm_payload),
        ) as post_json,
    ):
        material_sources = handle_evidence_list_material_sources(
            {"meta": {"correlation_id": "corr_material_sources"}}
        )
        generated = handle_evidence_generate_draft(
            {
                "meta": {"correlation_id": "corr_generate_draft"},
                "material_ids": ["mat_checkout"],
            }
        )
        invalid_json_result = None
        with patch(
            "tools.sidecar.handlers.evidence.LLMClient.post_json",
            return_value={"choices": [{"message": {"content": "not-json"}}]},
        ):
            invalid_json_result = handle_evidence_generate_draft(
                {
                    "meta": {"correlation_id": "corr_invalid_json"},
                    "material_ids": ["mat_checkout"],
                }
            )

        incomplete_draft = dict(generated["draft"])
        incomplete_draft["results"] = ""
        incomplete_draft["artifacts"] = []
        no_review_rejected = False
        try:
            handle_evidence_save_draft(
                {
                    "meta": {"correlation_id": "corr_save_no_review"},
                    "draft": incomplete_draft,
                    "save_mode": "incomplete",
                }
            )
        except ValueError:
            no_review_rejected = True
        incomplete = handle_evidence_save_draft(
            {
                "meta": {"correlation_id": "corr_save_incomplete"},
                "draft": incomplete_draft,
                "review": {
                    "decision": "approved",
                    "reviewed_at": "2026-05-21T00:00:00Z",
                },
                "save_mode": "incomplete",
            }
        )
        eligible = handle_evidence_save_draft(
            {
                "meta": {"correlation_id": "corr_save_eligible"},
                "draft": generated["draft"],
                "review": {
                    "decision": "approved",
                    "reviewed_at": "2026-05-21T00:00:00Z",
                },
                "save_mode": "eligible",
            }
        )
        eligible_detail = handle_evidence_get(
            {
                "meta": {"correlation_id": "corr_eligible_detail"},
                "evidence_id": eligible["evidence_id"],
            }
        )

    assert material_sources["items"][0]["material_id"] == "mat_checkout"
    assert post_json.call_count == 1
    assert generated["status"] == "draft_ready_for_review"
    assert generated["candidate_pool_eligible"] is False
    assert invalid_json_result["status"] == "llm_output_invalid"
    assert no_review_rejected is True
    assert incomplete["status"] == "saved_incomplete"
    assert incomplete["candidate_pool_eligible"] is False
    assert "missing_results" in incomplete["missing_items"]
    assert eligible["status"] == "saved_eligible"
    assert eligible["candidate_pool_eligible"] is True
    assert eligible_detail["evidence"]["source_material_ids"] == ["mat_checkout"]
    assert eligible_detail["evidence"]["raw_source"] == "materials:mat_checkout"
    assert eligible_detail["evidence"]["candidate_pool_eligible"] is True

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="generate_review_and_complete_evidence_card_l1",
        generated_at="2026-05-21T00:00:00Z",
        results={
            "evidence_card_requires_review": JourneyStepResult(
                status="pass",
                evidence=str(tmp_path),
                message=(
                    "Markdown material selection, strict JSON draft generation, invalid "
                    "JSON rejection, review-required save, incomplete exclusion, eligible "
                    "candidate promotion, source_material_ids, and raw_source traceability "
                    "are validated."
                ),
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["pass"] == 1
    assert "evidence_card_requires_review" in markdown_path.read_text(
        encoding="utf-8"
    )
