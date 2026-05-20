import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers.materials import (
    handle_evidence_list_material_sources,
    handle_material_list,
    handle_material_readiness,
    handle_material_upload,
)


class MaterialHandlerTests(unittest.TestCase):
    def test_upload_markdown_material_persists_metadata_and_preview(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "work-log.md"
            source.write_text(
                "# Checkout Reliability\n\nReduced failure rate by 43%.",
                encoding="utf-8",
            )
            materials_dir = root / "materials"
            with patch("tools.sidecar.handlers.materials._MATERIALS_DIR", materials_dir):
                uploaded = handle_material_upload(
                    {
                        "meta": {"correlation_id": "corr_mat_upload"},
                        "source_paths": [str(source)],
                        "label": "Checkout work log",
                    }
                )
                listed = handle_material_list(
                    {"meta": {"correlation_id": "corr_mat_list"}}
                )
                stored_exists = (materials_dir / f"{uploaded['material_id']}.md").exists()

        self.assertEqual(uploaded["label"], "Checkout work log")
        self.assertEqual(uploaded["extension"], ".md")
        self.assertIn("Reduced failure rate", uploaded["preview"])
        self.assertTrue(stored_exists)
        self.assertEqual(listed["items"][0]["material_id"], uploaded["material_id"])

    def test_upload_rejects_unsupported_file_type(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "screenshot.png"
            source.write_bytes(b"png")
            with patch("tools.sidecar.handlers.materials._MATERIALS_DIR", root / "materials"):
                with self.assertRaises(ValueError):
                    handle_material_upload(
                        {
                            "meta": {"correlation_id": "corr_mat_bad"},
                            "source_paths": [str(source)],
                        }
                    )

    def test_readiness_reports_missing_and_ready_states(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            profile_path = root / "personal_profile.yaml"
            uploaded_dir = root / "uploaded_resumes"
            materials_dir = root / "materials"
            with (
                patch("tools.sidecar.handlers.materials._PROFILE_PATH", profile_path),
                patch(
                    "tools.sidecar.handlers.materials._UPLOADED_RESUMES_DIR",
                    uploaded_dir,
                ),
                patch("tools.sidecar.handlers.materials._MATERIALS_DIR", materials_dir),
            ):
                incomplete = handle_material_readiness(
                    {"meta": {"correlation_id": "corr_ready_1"}}
                )

                profile_path.write_text(
                    "\n".join(
                        [
                            'name: "Zhang San"',
                            'phone: "+86 138 0000 0000"',
                            'email: "zhangsan@example.com"',
                            'city: "Shanghai"',
                            'current_position: "Staff Engineer"',
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                uploaded_dir.mkdir()
                (uploaded_dir / "rv_001.meta.yaml").write_text(
                    'resume_id: "rv_001"\nlabel: "Resume"\n', encoding="utf-8"
                )
                materials_dir.mkdir()
                (materials_dir / "mat_001.md").write_text("work", encoding="utf-8")
                (materials_dir / "mat_001.meta.yaml").write_text(
                    "\n".join(
                        [
                            'material_id: "mat_001"',
                            'resource_id: "res_001"',
                            'label: "Work"',
                            'kind: "raw_work_material"',
                            'filename: "mat_001.md"',
                            'extension: ".md"',
                            'uploaded_at: "2026-05-21T00:00:00Z"',
                            'preview: "work"',
                        ]
                    )
                    + "\n",
                    encoding="utf-8",
                )
                ready = handle_material_readiness(
                    {"meta": {"correlation_id": "corr_ready_2"}}
                )

        self.assertEqual(incomplete["status"], "incomplete")
        self.assertEqual(
            incomplete["missing_items"],
            [
                "missing_personal_profile",
                "missing_uploaded_resume",
                "missing_raw_work_material",
            ],
        )
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["missing_items"], [])

    def test_evidence_can_list_material_sources(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            materials_dir = Path(tmp_dir) / "materials"
            materials_dir.mkdir()
            (materials_dir / "mat_001.txt").write_text("raw material", encoding="utf-8")
            (materials_dir / "mat_001.meta.yaml").write_text(
                "\n".join(
                    [
                        'material_id: "mat_001"',
                        'resource_id: "res_001"',
                        'label: "Raw material"',
                        'kind: "raw_work_material"',
                        'filename: "mat_001.txt"',
                        'extension: ".txt"',
                        'uploaded_at: "2026-05-21T00:00:00Z"',
                        'preview: "raw material"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with patch("tools.sidecar.handlers.materials._MATERIALS_DIR", materials_dir):
                result = handle_evidence_list_material_sources(
                    {"meta": {"correlation_id": "corr_sources"}}
                )

        self.assertEqual(result["items"][0]["material_id"], "mat_001")
        self.assertEqual(result["items"][0]["kind"], "raw_work_material")


if __name__ == "__main__":
    unittest.main()
