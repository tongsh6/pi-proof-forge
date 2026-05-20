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
from tools.sidecar.handlers.materials import (
    handle_evidence_list_material_sources,
    handle_material_readiness,
    handle_material_upload,
)
from tools.sidecar.handlers.profile import handle_profile_get, handle_profile_update
from tools.sidecar.handlers.resume import handle_resume_get_preview, handle_resume_upload


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"


def test_setup_profile_and_material_library_l1_acceptance_writes_report(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "personal_profile.yaml"
    uploaded_dir = tmp_path / "uploaded_resumes"
    materials_dir = tmp_path / "materials"
    resume_source = tmp_path / "baseline_resume.md"
    material_source = tmp_path / "checkout_work_log.md"
    unsupported_source = tmp_path / "screenshot.png"
    resume_source.write_text(
        "# Zhang San\n\n## 10-Second Summary\n- Staff backend engineer.",
        encoding="utf-8",
    )
    material_source.write_text(
        "# Checkout Reliability\n\nReduced payment failure rate by 43%.",
        encoding="utf-8",
    )
    unsupported_source.write_bytes(b"png")

    with (
        patch("tools.sidecar.handlers.profile._PROFILE_PATH", profile_path),
        patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir),
        patch("tools.sidecar.handlers.materials._PROFILE_PATH", profile_path),
        patch("tools.sidecar.handlers.materials._UPLOADED_RESUMES_DIR", uploaded_dir),
        patch("tools.sidecar.handlers.materials._MATERIALS_DIR", materials_dir),
    ):
        profile_update = handle_profile_update(
            {
                "meta": {"correlation_id": "corr_profile_update"},
                "patch": {
                    "name": "Zhang San",
                    "email": "zhangsan@example.com",
                    "phone": "+86 138 0000 0000",
                    "city": "Shanghai",
                    "current_position": "Staff Backend Engineer",
                },
            }
        )
        profile = handle_profile_get({"meta": {"correlation_id": "corr_profile_get"}})
        uploaded_resume = handle_resume_upload(
            {
                "meta": {"correlation_id": "corr_resume_upload"},
                "source_paths": [str(resume_source)],
                "language": "en",
                "label": "Baseline Markdown Resume",
            }
        )
        resume_preview = handle_resume_get_preview(
            {
                "meta": {"correlation_id": "corr_resume_preview"},
                "resume_id": uploaded_resume["resume_id"],
            }
        )
        uploaded_material = handle_material_upload(
            {
                "meta": {"correlation_id": "corr_material_upload"},
                "source_paths": [str(material_source)],
                "label": "Checkout Work Log",
            }
        )
        unsupported_rejected = False
        try:
            handle_material_upload(
                {
                    "meta": {"correlation_id": "corr_material_bad"},
                    "source_paths": [str(unsupported_source)],
                }
            )
        except ValueError:
            unsupported_rejected = True
        readiness = handle_material_readiness(
            {"meta": {"correlation_id": "corr_material_readiness"}}
        )
        material_sources = handle_evidence_list_material_sources(
            {"meta": {"correlation_id": "corr_material_sources"}}
        )

    assert profile_update["saved"] is True
    assert profile["profile"]["completeness"] == 100
    assert uploaded_resume["resume_id"].startswith("rv_")
    assert resume_preview["preview_status"] == "available"
    assert "Staff backend engineer" in resume_preview["preview"]["summary"]
    assert uploaded_material["material_id"].startswith("mat_")
    assert "Reduced payment failure rate" in uploaded_material["preview"]
    assert unsupported_rejected is True
    assert readiness["status"] == "ready"
    assert readiness["missing_items"] == []
    assert material_sources["items"][0]["material_id"] == uploaded_material["material_id"]

    contract = load_journey_contract(CONTRACT_PATH)
    report = build_journey_report(
        contract,
        run_id="setup_profile_and_material_library_l1",
        generated_at="2026-05-21T00:00:00Z",
        results={
            "profile_and_materials_persisted": JourneyStepResult(
                status="pass",
                evidence=str(tmp_path),
                message=(
                    "Profile, markdown resume metadata/preview, raw markdown material, "
                    "readiness feedback, unsupported type rejection, and evidence material "
                    "source listing are validated."
                ),
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["pass"] == 1
    assert "setup_profile_and_material_library" in markdown_path.read_text(
        encoding="utf-8"
    )
