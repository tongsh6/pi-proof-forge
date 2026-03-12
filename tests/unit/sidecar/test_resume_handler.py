import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers.resume import (
    handle_resume_export_pdf,
    handle_resume_get_preview,
    handle_resume_list,
    handle_resume_upload,
)


class ResumeListTests(unittest.TestCase):
    def test_returns_empty_when_no_resumes_exist(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                    result = handle_resume_list(
                        {"meta": {"correlation_id": "corr_001"}}
                    )

        self.assertEqual(result["meta"]["correlation_id"], "corr_001")
        self.assertEqual(result["items"], [])
        self.assertIsNone(result["next_cursor"])

    def test_lists_generated_and_uploaded_resumes(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            outputs_dir.mkdir()
            generated = outputs_dir / "resume_mr-2026-005_A.md"
            generated.write_text("# Zhang San\n\nSummary", encoding="utf-8")

            matching_dir = Path(tmp_dir) / "matching_reports"
            matching_dir.mkdir()
            (matching_dir / "mr-2026-005.yaml").write_text(
                'job_profile_id: "jp-2026-002"\n', encoding="utf-8"
            )

            profiles_dir = Path(tmp_dir) / "job_profiles"
            profiles_dir.mkdir()
            (profiles_dir / "jp-2026-002.yaml").write_text(
                'company: "Acme"\n', encoding="utf-8"
            )

            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            uploaded_dir.mkdir()
            (uploaded_dir / "rv_001.pdf").write_bytes(b"%PDF-fake")
            (uploaded_dir / "rv_001.meta.yaml").write_text(
                "\n".join(
                    [
                        'resume_id: "rv_001"',
                        'label: "My Resume"',
                        'language: "zh"',
                        'resource_id: "res_001"',
                        'uploaded_at: "2026-03-07T10:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                    with patch(
                        "tools.sidecar.handlers.resume._MATCHING_REPORT_DIR",
                        matching_dir,
                    ):
                        with patch(
                            "tools.sidecar.handlers.resume._JOB_PROFILE_DIR",
                            profiles_dir,
                        ):
                            result = handle_resume_list(
                                {"meta": {"correlation_id": "corr_002"}}
                            )

        self.assertEqual(len(result["items"]), 2)
        ids = {item["resume_id"] for item in result["items"]}
        self.assertIn("gen_resume_mr-2026-005_A", ids)
        self.assertIn("rv_001", ids)
        generated_item = next(
            item
            for item in result["items"]
            if item["resume_id"] == "gen_resume_mr-2026-005_A"
        )
        self.assertEqual(generated_item["job_profile_id"], "jp-2026-002")
        self.assertEqual(generated_item["company"], "Acme")

    def test_filters_by_company_for_generated_resume(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            outputs_dir.mkdir()
            (outputs_dir / "resume_mr-2026-005_A.md").write_text(
                "# Zhang San\n\nSummary", encoding="utf-8"
            )

            matching_dir = Path(tmp_dir) / "matching_reports"
            matching_dir.mkdir()
            (matching_dir / "mr-2026-005.yaml").write_text(
                'job_profile_id: "jp-2026-002"\nscore_total: "86"\n',
                encoding="utf-8",
            )

            profiles_dir = Path(tmp_dir) / "job_profiles"
            profiles_dir.mkdir()
            (profiles_dir / "jp-2026-002.yaml").write_text(
                'company: "Acme"\n', encoding="utf-8"
            )

            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            uploaded_dir.mkdir()

            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                    with patch(
                        "tools.sidecar.handlers.resume._MATCHING_REPORT_DIR",
                        matching_dir,
                    ):
                        with patch(
                            "tools.sidecar.handlers.resume._JOB_PROFILE_DIR",
                            profiles_dir,
                        ):
                            result = handle_resume_list(
                                {
                                    "meta": {"correlation_id": "corr_003"},
                                    "cursor": None,
                                    "page_size": 20,
                                    "sort": {
                                        "field": "updated_at",
                                        "order": "desc",
                                    },
                                    "filters": {"company": "Acme"},
                                }
                            )

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["company"], "Acme")

    def test_filters_by_status_and_job_profile(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            outputs_dir.mkdir()
            generated = outputs_dir / "resume_mr-2026-005_A.md"
            generated.write_text("# Zhang San\n\nSummary", encoding="utf-8")

            matching_dir = Path(tmp_dir) / "matching_reports"
            matching_dir.mkdir()
            (matching_dir / "mr-2026-005.yaml").write_text(
                'job_profile_id: "jp-2026-002"\n', encoding="utf-8"
            )

            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            uploaded_dir.mkdir()
            (uploaded_dir / "rv_001.pdf").write_bytes(b"%PDF-fake")
            (uploaded_dir / "rv_001.meta.yaml").write_text(
                "\n".join(
                    [
                        'resume_id: "rv_001"',
                        'label: "My Resume"',
                        'language: "zh"',
                        'resource_id: "res_001"',
                        'uploaded_at: "2026-03-07T10:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                    with patch(
                        "tools.sidecar.handlers.resume._MATCHING_REPORT_DIR",
                        matching_dir,
                    ):
                        result = handle_resume_list(
                            {
                                "meta": {"correlation_id": "corr_010"},
                                "cursor": None,
                                "page_size": 20,
                                "sort": {"field": "updated_at", "order": "desc"},
                                "filters": {
                                    "status": "uploaded",
                                    "job_profile": "jp-2026-002",
                                    "company": None,
                                },
                            }
                        )

        self.assertEqual(result["items"], [])

    def test_sorts_by_score_desc(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            outputs_dir.mkdir()
            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            uploaded_dir.mkdir()
            (uploaded_dir / "rv_001.pdf").write_bytes(b"%PDF-fake")
            (uploaded_dir / "rv_001.meta.yaml").write_text(
                "\n".join(
                    [
                        'resume_id: "rv_001"',
                        'label: "Resume A"',
                        'score: "42"',
                        'uploaded_at: "2026-03-07T10:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (uploaded_dir / "rv_002.pdf").write_bytes(b"%PDF-fake")
            (uploaded_dir / "rv_002.meta.yaml").write_text(
                "\n".join(
                    [
                        'resume_id: "rv_002"',
                        'label: "Resume B"',
                        'score: "84"',
                        'uploaded_at: "2026-03-08T10:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                    result = handle_resume_list(
                        {
                            "meta": {"correlation_id": "corr_011"},
                            "cursor": None,
                            "page_size": 20,
                            "sort": {"field": "score", "order": "desc"},
                            "filters": {},
                        }
                    )

        self.assertEqual(result["items"][0]["resume_id"], "rv_002")


class ResumeUploadTests(unittest.TestCase):
    def test_upload_copies_file_and_writes_metadata(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "my_resume.pdf"
            source.write_bytes(b"%PDF-fake")
            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                result = handle_resume_upload(
                    {
                        "meta": {"correlation_id": "corr_003"},
                        "source_paths": [str(source)],
                        "language": "zh",
                        "label": "简历 2025 版",
                    }
                )
                self.assertEqual(result["meta"]["correlation_id"], "corr_003")
                self.assertTrue(result["resume_id"].startswith("rv_"))
                self.assertEqual(result["label"], "简历 2025 版")
                self.assertEqual(result["language"], "zh")
                self.assertTrue((uploaded_dir / f"{result['resume_id']}.pdf").exists())
                self.assertTrue(
                    (uploaded_dir / f"{result['resume_id']}.meta.yaml").exists()
                )

    def test_upload_rejects_missing_source(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                with self.assertRaises(FileNotFoundError):
                    handle_resume_upload(
                        {
                            "meta": {"correlation_id": "corr_004"},
                            "source_paths": ["/missing/file.pdf"],
                        }
                    )


class ResumePreviewTests(unittest.TestCase):
    def test_uploaded_resume_returns_pending_preview(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            uploaded_dir.mkdir()
            (uploaded_dir / "rv_001.meta.yaml").write_text(
                'resume_id: "rv_001"\nlabel: "Resume"\n', encoding="utf-8"
            )
            with patch(
                "tools.sidecar.handlers.resume._OUTPUTS_DIR", Path(tmp_dir) / "outputs"
            ):
                with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                    result = handle_resume_get_preview(
                        {"meta": {"correlation_id": "corr_005"}, "resume_id": "rv_001"}
                    )

        self.assertEqual(result["resume_id"], "rv_001")
        self.assertIsNone(result["preview"])
        self.assertEqual(result["preview_status"], "pending")

    def test_generated_markdown_returns_structured_preview(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            outputs_dir.mkdir()
            generated = outputs_dir / "resume_mr-2026-005_A.md"
            generated.write_text(
                "\n".join(
                    [
                        "# Resume Version A",
                        "Generated at: 2026-03-07 10:00:00",
                        "Source report: mr-2026-005",
                        "",
                        "## 10-Second Summary",
                        "- 定位：Backend Tech Lead（架构/技术深度）",
                        "- 匹配得分：84/100",
                        "- 核心技术栈：Python, Go, PostgreSQL",
                        "",
                        "## Highlights",
                        "- Reduced p99 latency from 200ms to 40ms；在高并发场景下通过链路治理达成。",
                        "",
                        "## Experience",
                        "### Search Platform Upgrade（2022.01 - 2025.01）",
                        "- 角色与范围：Owner",
                        "- 场景约束：高并发检索服务",
                        "- 关键动作：重构检索链路；引入分层缓存",
                        "- 结果：Built high-throughput search service handling 100k QPS；Reduced p99 latency from 200ms to 40ms",
                        "- 技术栈：Python, Go, PostgreSQL",
                        "",
                        "## Projects",
                        "- Search Platform Upgrade：挑战=高并发检索服务；动作=重构检索链路；结果=Reduced p99 latency from 200ms to 40ms",
                    ]
                ),
                encoding="utf-8",
            )
            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch(
                    "tools.sidecar.handlers.resume._UPLOADED_DIR",
                    Path(tmp_dir) / "uploaded",
                ):
                    result = handle_resume_get_preview(
                        {
                            "meta": {"correlation_id": "corr_006"},
                            "resume_id": "gen_resume_mr-2026-005_A",
                        }
                    )

        preview = result["preview"]
        self.assertEqual(preview["name"], "Resume Version A")
        self.assertIn("定位：Backend Tech Lead（架构/技术深度）", preview["summary"])
        self.assertIn("Python", preview["skills"])
        self.assertEqual(preview["experience"][0]["company"], "Search Platform Upgrade")

    def test_preview_not_found_raises(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            with patch(
                "tools.sidecar.handlers.resume._OUTPUTS_DIR", Path(tmp_dir) / "outputs"
            ):
                with patch(
                    "tools.sidecar.handlers.resume._UPLOADED_DIR",
                    Path(tmp_dir) / "uploaded",
                ):
                    with self.assertRaises(KeyError):
                        handle_resume_get_preview(
                            {
                                "meta": {"correlation_id": "corr_007"},
                                "resume_id": "missing",
                            }
                        )


class ResumeExportPdfTests(unittest.TestCase):
    def test_export_pdf_copies_uploaded_pdf_source(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            outputs_dir.mkdir()
            uploaded_dir = Path(tmp_dir) / "uploaded_resumes"
            uploaded_dir.mkdir()
            source_bytes = b"%PDF-1.7\nreal uploaded resume\n"
            (uploaded_dir / "rv_001.pdf").write_bytes(source_bytes)
            (uploaded_dir / "rv_001.meta.yaml").write_text(
                "\n".join(
                    [
                        'resume_id: "rv_001"',
                        'label: "Uploaded Resume"',
                        'language: "zh"',
                        'resource_id: "res_001"',
                        'uploaded_at: "2026-03-07T10:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            destination = Path(tmp_dir) / "exports" / "resume.pdf"
            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch("tools.sidecar.handlers.resume._UPLOADED_DIR", uploaded_dir):
                    result = handle_resume_export_pdf(
                        {
                            "meta": {"correlation_id": "corr_008"},
                            "resume_id": "rv_001",
                            "destination": str(destination),
                        }
                    )
                    self.assertTrue(result["resource_id"].startswith("pdf_"))
                    self.assertTrue(destination.exists())
                    self.assertEqual(destination.read_bytes(), source_bytes)

    def test_export_pdf_converts_markdown_to_pdf_when_available(self) -> None:
        from tools.infra.export.pdf_exporter import WEASYPRINT_AVAILABLE

        if not WEASYPRINT_AVAILABLE:
            return
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            outputs_dir.mkdir()
            generated = outputs_dir / "resume_mr-2026-005_A.md"
            generated.write_text("# Resume\n\nContent here\n", encoding="utf-8")
            destination = Path(tmp_dir) / "exports" / "resume.pdf"
            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch(
                    "tools.sidecar.handlers.resume._UPLOADED_DIR",
                    Path(tmp_dir) / "uploaded",
                ):
                    result = handle_resume_export_pdf(
                        {
                            "meta": {"correlation_id": "corr_008"},
                            "resume_id": "gen_resume_mr-2026-005_A",
                            "destination": str(destination),
                        }
                    )
                    self.assertTrue(result["resource_id"].startswith("pdf_"))
                    self.assertTrue(destination.exists())
                    self.assertGreater(destination.stat().st_size, 0)

    def test_export_pdf_raises_when_markdown_and_weasyprint_unavailable(self) -> None:
        from tools.infra.export.pdf_exporter import WEASYPRINT_AVAILABLE

        if WEASYPRINT_AVAILABLE:
            return
        with TemporaryDirectory() as tmp_dir:
            outputs_dir = Path(tmp_dir) / "outputs"
            outputs_dir.mkdir()
            generated = outputs_dir / "resume_mr-2026-005_A.md"
            generated.write_text("# Resume\n", encoding="utf-8")
            destination = Path(tmp_dir) / "exports" / "resume.pdf"
            with patch("tools.sidecar.handlers.resume._OUTPUTS_DIR", outputs_dir):
                with patch(
                    "tools.sidecar.handlers.resume._UPLOADED_DIR",
                    Path(tmp_dir) / "uploaded",
                ):
                    with self.assertRaises(RuntimeError) as ctx:
                        handle_resume_export_pdf(
                            {
                                "meta": {"correlation_id": "corr_008"},
                                "resume_id": "gen_resume_mr-2026-005_A",
                                "destination": str(destination),
                            }
                        )
                    self.assertIn("weasyprint", str(ctx.exception).lower())
                    self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
