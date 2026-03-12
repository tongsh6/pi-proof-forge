import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from typing import Any

from tools.sidecar.handlers.evidence import (
    handle_evidence_create,
    handle_evidence_delete,
    handle_evidence_get,
    handle_evidence_import,
    handle_evidence_list,
    handle_evidence_update,
)


SAMPLE_YAML = """\
id: "ec-2026-001"
title: "Order stability"
time_range: "2025-10 ~ 2026-01"
context: "Peak 5k QPS"
role_scope: "Owner"
actions:
  - "Refactored circuit breaker"
results:
  - "Failure rate dropped 43%"
stack:
  - "Java"
  - "Redis"
artifacts:
  - "postmortem.pdf"
tags:
  - "stability"
"""


class EvidenceListTests(unittest.TestCase):
    def _write_card(
        self,
        directory: Path,
        name: str,
        *,
        title: str,
        status: str,
        role_scope: str,
        tags: list[str],
        updated_at: str,
        score: str,
    ) -> None:
        lines = [
            f'id: "{name}"',
            f'title: "{title}"',
            'time_range: "2024.01 - 2024.12"',
            f'role_scope: "{role_scope}"',
            f'status: "{status}"',
            f'updated_at: "{updated_at}"',
            f'score: "{score}"',
            "tags:",
        ]
        lines.extend([f'  - "{tag}"' for tag in tags])
        path = directory / f"{name}.yaml"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @patch("tools.sidecar.handlers.evidence._load_evidence_cards")
    def test_list_returns_items_with_contract_fields(self, mock_load: Any) -> None:
        mock_load.return_value = [
            {
                "evidence_id": "ec-2026-001",
                "title": "Order stability",
                "time_range": "2025-10 ~ 2026-01",
                "role_scope": "Owner",
                "score": 0,
                "status": "ready",
                "updated_at": "2026-03-07T10:00:00Z",
            }
        ]
        params = {
            "meta": {"correlation_id": "corr_001"},
            "cursor": None,
            "page_size": 20,
            "sort": {"field": "updated_at", "order": "desc"},
            "filters": {},
        }
        result = handle_evidence_list(params)
        self.assertEqual(result["meta"]["correlation_id"], "corr_001")
        self.assertIn("items", result)
        self.assertIn("next_cursor", result)
        item = result["items"][0]
        self.assertEqual(item["evidence_id"], "ec-2026-001")
        self.assertIn("title", item)
        self.assertIn("time_range", item)
        self.assertIn("role_scope", item)
        self.assertIn("status", item)
        self.assertIn("updated_at", item)

    @patch("tools.sidecar.handlers.evidence._load_evidence_cards")
    def test_list_respects_page_size(self, mock_load: Any) -> None:
        mock_load.return_value = [
            {
                "evidence_id": f"ec-{i}",
                "title": f"Card {i}",
                "time_range": "",
                "role_scope": "",
                "score": 0,
                "status": "ready",
                "updated_at": "",
            }
            for i in range(5)
        ]
        params = {
            "meta": {"correlation_id": "corr_002"},
            "cursor": None,
            "page_size": 2,
            "sort": {"field": "updated_at", "order": "desc"},
            "filters": {},
        }
        result = handle_evidence_list(params)
        self.assertEqual(len(result["items"]), 2)
        self.assertIsNotNone(result["next_cursor"])

    def test_list_filters_by_tags(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            self._write_card(
                evidence_dir,
                "ec_001",
                title="Search platform",
                status="ready",
                role_scope="Owner",
                tags=["search", "infra"],
                updated_at="2026-03-07T10:00:00Z",
                score="20",
            )
            self._write_card(
                evidence_dir,
                "ec_002",
                title="Billing rewrite",
                status="ready",
                role_scope="Engineer",
                tags=["billing"],
                updated_at="2026-03-08T10:00:00Z",
                score="80",
            )
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                result = handle_evidence_list(
                    {
                        "meta": {"correlation_id": "corr_011"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "updated_at", "order": "desc"},
                        "filters": {"tags": ["search"]},
                    }
                )

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["evidence_id"], "ec_001")

    def test_list_sorts_by_score_desc(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            self._write_card(
                evidence_dir,
                "ec_001",
                title="Low score",
                status="ready",
                role_scope="Owner",
                tags=["search"],
                updated_at="2026-03-07T10:00:00Z",
                score="10",
            )
            self._write_card(
                evidence_dir,
                "ec_002",
                title="High score",
                status="ready",
                role_scope="Owner",
                tags=["search"],
                updated_at="2026-03-08T10:00:00Z",
                score="90",
            )
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                result = handle_evidence_list(
                    {
                        "meta": {"correlation_id": "corr_012"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "score", "order": "desc"},
                        "filters": {},
                    }
                )

        self.assertEqual(result["items"][0]["evidence_id"], "ec_002")

    def test_list_filters_by_query_and_date_range(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            self._write_card(
                evidence_dir,
                "ec_001",
                title="Platform stability",
                status="ready",
                role_scope="Owner",
                tags=["infra"],
                updated_at="2026-03-01T10:00:00Z",
                score="10",
            )
            self._write_card(
                evidence_dir,
                "ec_002",
                title="Billing API",
                status="ready",
                role_scope="Engineer",
                tags=["billing"],
                updated_at="2026-03-10T10:00:00Z",
                score="20",
            )
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                result = handle_evidence_list(
                    {
                        "meta": {"correlation_id": "corr_013"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "updated_at", "order": "desc"},
                        "filters": {
                            "query": "platform",
                            "date_range": {
                                "start": "2026-03-01T00:00:00Z",
                                "end": "2026-03-05T23:59:59Z",
                            },
                        },
                    }
                )

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["evidence_id"], "ec_001")

    def test_list_filters_by_role_case_insensitive(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            self._write_card(
                evidence_dir,
                "ec_001",
                title="Platform stability",
                status="ready",
                role_scope="Senior Backend Engineer",
                tags=["infra"],
                updated_at="2026-03-01T10:00:00Z",
                score="10",
            )
            self._write_card(
                evidence_dir,
                "ec_002",
                title="Frontend optimization",
                status="ready",
                role_scope="Frontend Developer",
                tags=["frontend"],
                updated_at="2026-03-10T10:00:00Z",
                score="20",
            )
            self._write_card(
                evidence_dir,
                "ec_003",
                title="DevOps pipeline",
                status="ready",
                role_scope="DevOps Engineer",
                tags=["devops"],
                updated_at="2026-03-15T10:00:00Z",
                score="30",
            )
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                # 测试大小写不敏感的包含匹配
                result = handle_evidence_list(
                    {
                        "meta": {"correlation_id": "corr_014"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "updated_at", "order": "desc"},
                        "filters": {"role": "engineer"},
                    }
                )

        # 应该匹配"Senior Backend Engineer"和"DevOps Engineer"，但不匹配"Frontend Developer"
        self.assertEqual(len(result["items"]), 2)
        evidence_ids = {item["evidence_id"] for item in result["items"]}
        self.assertIn("ec_001", evidence_ids)
        self.assertIn("ec_003", evidence_ids)
        self.assertNotIn("ec_002", evidence_ids)

    def test_list_filters_by_role_exact_match(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            self._write_card(
                evidence_dir,
                "ec_001",
                title="Platform stability",
                status="ready",
                role_scope="Backend Engineer",
                tags=["infra"],
                updated_at="2026-03-01T10:00:00Z",
                score="10",
            )
            self._write_card(
                evidence_dir,
                "ec_002",
                title="Senior platform",
                status="ready",
                role_scope="Senior Backend Engineer",
                tags=["infra"],
                updated_at="2026-03-10T10:00:00Z",
                score="20",
            )
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                # 测试部分匹配
                result = handle_evidence_list(
                    {
                        "meta": {"correlation_id": "corr_015"},
                        "cursor": None,
                        "page_size": 20,
                        "sort": {"field": "updated_at", "order": "desc"},
                        "filters": {"role": "Backend"},
                    }
                )

        # 应该匹配两个都包含"Backend"的卡片
        self.assertEqual(len(result["items"]), 2)
        evidence_ids = {item["evidence_id"] for item in result["items"]}
        self.assertIn("ec_001", evidence_ids)
        self.assertIn("ec_002", evidence_ids)


class EvidenceGetTests(unittest.TestCase):
    @patch("tools.sidecar.handlers.evidence._load_evidence_detail")
    def test_get_returns_full_evidence(self, mock_load: Any) -> None:
        mock_load.return_value = {
            "evidence_id": "ec-2026-001",
            "title": "Order stability",
            "time_range": "2025-10 ~ 2026-01",
            "context": "Peak 5k QPS",
            "role_scope": "Owner",
            "actions": "Refactored circuit breaker",
            "results": "Failure rate dropped 43%",
            "stack": ["Java", "Redis"],
            "tags": ["stability"],
            "artifacts": [],
        }
        params = {
            "meta": {"correlation_id": "corr_003"},
            "evidence_id": "ec-2026-001",
        }
        result = handle_evidence_get(params)
        self.assertEqual(result["meta"]["correlation_id"], "corr_003")
        evidence = result["evidence"]
        self.assertEqual(evidence["evidence_id"], "ec-2026-001")
        self.assertIn("title", evidence)
        self.assertIn("context", evidence)
        self.assertIn("stack", evidence)
        self.assertIn("artifacts", evidence)

    @patch("tools.sidecar.handlers.evidence._load_evidence_detail")
    def test_get_not_found_raises(self, mock_load: Any) -> None:
        mock_load.return_value = None
        params = {
            "meta": {"correlation_id": "corr_004"},
            "evidence_id": "ec-nonexistent",
        }
        with self.assertRaises(KeyError):
            handle_evidence_get(params)

    def test_get_returns_complete_artifact_shape_without_meta(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            evidence_dir = base_dir / "evidence_cards"
            evidence_dir.mkdir()
            (evidence_dir / "ec_001.yaml").write_text(
                "\n".join(
                    [
                        'id: "ec_001"',
                        'title: "Artifact fallback"',
                        'time_range: ""',
                        'context: ""',
                        'role_scope: ""',
                        'status: "draft"',
                        'created_at: "2026-03-07T10:00:00Z"',
                        'updated_at: "2026-03-07T10:00:00Z"',
                        "actions:",
                        "results:",
                        "stack:",
                        "artifacts:",
                        '  - "res_legacy"',
                        "tags:",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with (
                patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir),
                patch(
                    "tools.sidecar.handlers.evidence._APP_DATA_DIR",
                    base_dir / "app-data",
                ),
            ):
                result = handle_evidence_get(
                    {
                        "meta": {"correlation_id": "corr_004b"},
                        "evidence_id": "ec_001",
                    }
                )

        artifact = result["evidence"]["artifacts"][0]
        self.assertEqual(artifact["resource_id"], "res_legacy")
        self.assertEqual(artifact["filename"], "res_legacy")
        self.assertEqual(artifact["mime_type"], "")
        self.assertEqual(artifact["size_bytes"], 0)
        self.assertEqual(artifact["created_at"], "")


class EvidenceCreateTests(unittest.TestCase):
    def test_create_returns_id_status_and_timestamp(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", Path(tmp_dir)):
                result = handle_evidence_create(
                    {
                        "meta": {"correlation_id": "corr_005"},
                        "title": "New evidence",
                        "time_range": "2024.01 - 2024.12",
                        "context": "",
                        "role_scope": "Backend Engineer",
                        "actions": "Action 1",
                        "results": "Result 1",
                        "stack": ["Python"],
                        "tags": ["search"],
                    }
                )

        self.assertEqual(result["meta"]["correlation_id"], "corr_005")
        self.assertTrue(result["evidence_id"].startswith("ec_"))
        self.assertEqual(result["status"], "draft")
        self.assertTrue(result["created_at"].endswith("Z"))

    def test_create_persists_yaml_file(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", Path(tmp_dir)):
                result = handle_evidence_create(
                    {
                        "meta": {"correlation_id": "corr_006"},
                        "title": "Persisted evidence",
                        "time_range": "2024.01 - 2024.12",
                        "context": "Context",
                        "role_scope": "Engineer",
                        "actions": "Action 1\nAction 2",
                        "results": "Result 1",
                        "stack": ["Python", "Redis"],
                        "tags": ["stability"],
                    }
                )
                detail = handle_evidence_get(
                    {
                        "meta": {"correlation_id": "corr_007"},
                        "evidence_id": result["evidence_id"],
                    }
                )

        evidence = detail["evidence"]
        self.assertEqual(evidence["title"], "Persisted evidence")
        self.assertEqual(evidence["actions"], "Action 1\nAction 2")
        self.assertEqual(evidence["stack"], ["Python", "Redis"])
        self.assertEqual(evidence["tags"], ["stability"])

    def test_create_rejects_empty_title(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_008"},
            "title": "",
            "time_range": "",
            "context": "",
            "role_scope": "",
            "actions": "",
            "results": "",
            "stack": [],
            "tags": [],
        }
        with self.assertRaises(ValueError):
            handle_evidence_create(params)


class EvidenceUpdateTests(unittest.TestCase):
    def test_update_persists_patch_fields(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            (evidence_dir / "ec_001.yaml").write_text(SAMPLE_YAML, encoding="utf-8")
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                result = handle_evidence_update(
                    {
                        "meta": {"correlation_id": "corr_009"},
                        "evidence_id": "ec-2026-001",
                        "patch": {
                            "title": "Updated title",
                            "actions": "Updated action",
                            "stack": ["Go"],
                        },
                    }
                )
                detail = handle_evidence_get(
                    {
                        "meta": {"correlation_id": "corr_010"},
                        "evidence_id": "ec-2026-001",
                    }
                )

        self.assertEqual(result["meta"]["correlation_id"], "corr_009")
        self.assertEqual(result["evidence_id"], "ec-2026-001")
        self.assertTrue(result["updated_at"].endswith("Z"))
        evidence = detail["evidence"]
        self.assertEqual(evidence["title"], "Updated title")
        self.assertEqual(evidence["actions"], "Updated action")
        self.assertEqual(evidence["stack"], ["Go"])
        self.assertEqual(evidence["results"], "Failure rate dropped 43%")

    def test_update_not_found_raises(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", Path(tmp_dir)):
                with self.assertRaises(KeyError):
                    handle_evidence_update(
                        {
                            "meta": {"correlation_id": "corr_011"},
                            "evidence_id": "missing",
                            "patch": {"title": "Updated title"},
                        }
                    )

    def test_update_rejects_empty_title(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            (evidence_dir / "ec_001.yaml").write_text(SAMPLE_YAML, encoding="utf-8")
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                with self.assertRaises(ValueError):
                    handle_evidence_update(
                        {
                            "meta": {"correlation_id": "corr_012"},
                            "evidence_id": "ec-2026-001",
                            "patch": {"title": ""},
                        }
                    )

    def test_update_preserves_existing_folded_context_when_patching_title(self) -> None:
        text = """\
id: "ec-2026-001"
title: "Order stability"
time_range: "2025-10 ~ 2026-01"
context: >
  first context line
  second context line
role_scope: "Owner"
status: "ready"
created_at: "2026-03-01T00:00:00Z"
updated_at: "2026-03-02T00:00:00Z"
actions:
  - "Refactored circuit breaker"
results:
  - "Failure rate dropped 43%"
stack:
  - "Java"
artifacts:
tags:
  - "stability"
"""
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            path = evidence_dir / "ec_001.yaml"
            path.write_text(text, encoding="utf-8")
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                handle_evidence_update(
                    {
                        "meta": {"correlation_id": "corr_012b"},
                        "evidence_id": "ec-2026-001",
                        "patch": {"title": "Updated title"},
                    }
                )
                detail = handle_evidence_get(
                    {
                        "meta": {"correlation_id": "corr_012c"},
                        "evidence_id": "ec-2026-001",
                    }
                )

        self.assertEqual(detail["evidence"]["title"], "Updated title")
        self.assertEqual(
            detail["evidence"]["context"],
            "first context line second context line",
        )


class EvidenceImportTests(unittest.TestCase):
    def test_import_creates_evidence_and_artifact(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            source = base_dir / "brief.pdf"
            source.write_bytes(b"%PDF-1.4")
            evidence_dir = base_dir / "evidence_cards"
            app_data = base_dir / "app-data"
            with (
                patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir),
                patch("tools.sidecar.handlers.evidence._APP_DATA_DIR", app_data),
            ):
                result = handle_evidence_import(
                    {
                        "meta": {"correlation_id": "corr_020"},
                        "source_paths": [str(source)],
                        "target_evidence_id": None,
                        "mode": "create",
                    }
                )
                detail = handle_evidence_get(
                    {
                        "meta": {"correlation_id": "corr_021"},
                        "evidence_id": result["evidence_id"],
                    }
                )

        self.assertEqual(result["meta"]["correlation_id"], "corr_020")
        self.assertTrue(result["evidence_id"].startswith("ec_"))
        self.assertEqual(len(result["imported_resources"]), 1)
        artifacts = detail["evidence"]["artifacts"]
        self.assertEqual(artifacts[0]["filename"], "brief.pdf")

    def test_update_preserves_artifacts_and_unknown_sections(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            path = evidence_dir / "ec_001.yaml"
            path.write_text(
                SAMPLE_YAML + 'interview_hooks:\n  - "Why this rollback strategy?"\n',
                encoding="utf-8",
            )
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                _ = handle_evidence_update(
                    {
                        "meta": {"correlation_id": "corr_012a"},
                        "evidence_id": "ec-2026-001",
                        "patch": {"title": "Updated title"},
                    }
                )
                updated_text = path.read_text(encoding="utf-8")

        self.assertIn("artifacts:", updated_text)
        self.assertIn('  - "postmortem.pdf"', updated_text)
        self.assertIn("interview_hooks:", updated_text)
        self.assertIn('  - "Why this rollback strategy?"', updated_text)

    def test_import_append_preserves_existing_artifacts(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            # 创建现有证据卡
            evidence_dir = base_dir / "evidence_cards"
            evidence_dir.mkdir()
            path = evidence_dir / "ec_existing.yaml"
            path.write_text(
                "\n".join(
                    [
                        'id: "ec_existing"',
                        'title: "Existing evidence"',
                        'time_range: ""',
                        'context: ""',
                        'role_scope: ""',
                        'status: "draft"',
                        'created_at: "2026-03-07T10:00:00Z"',
                        'updated_at: "2026-03-07T10:00:00Z"',
                        "actions:",
                        "results:",
                        "stack:",
                        "artifacts:",
                        '  - "existing_artifact.pdf"',
                        "tags:",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            # 创建新文件用于导入
            source = base_dir / "new_file.pdf"
            source.write_bytes(b"%PDF-1.4")
            app_data = base_dir / "app-data"

            with (
                patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir),
                patch("tools.sidecar.handlers.evidence._APP_DATA_DIR", app_data),
            ):
                result = handle_evidence_import(
                    {
                        "meta": {"correlation_id": "corr_022"},
                        "source_paths": [str(source)],
                        "target_evidence_id": "ec_existing",
                        "mode": "append",
                    }
                )
                detail = handle_evidence_get(
                    {
                        "meta": {"correlation_id": "corr_023"},
                        "evidence_id": "ec_existing",
                    }
                )

        self.assertEqual(result["meta"]["correlation_id"], "corr_022")
        self.assertEqual(result["evidence_id"], "ec_existing")
        self.assertEqual(len(result["imported_resources"]), 1)
        artifacts = detail["evidence"]["artifacts"]
        self.assertEqual(len(artifacts), 2)
        artifact_filenames = [a["filename"] for a in artifacts]
        self.assertIn("existing_artifact.pdf", artifact_filenames)
        self.assertIn("new_file.pdf", artifact_filenames)

    def test_import_replace_discards_existing_artifacts(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            # 创建现有证据卡
            evidence_dir = base_dir / "evidence_cards"
            evidence_dir.mkdir()
            path = evidence_dir / "ec_existing.yaml"
            path.write_text(
                "\n".join(
                    [
                        'id: "ec_existing"',
                        'title: "Existing evidence"',
                        'time_range: ""',
                        'context: ""',
                        'role_scope: ""',
                        'status: "draft"',
                        'created_at: "2026-03-07T10:00:00Z"',
                        'updated_at: "2026-03-07T10:00:00Z"',
                        "actions:",
                        "results:",
                        "stack:",
                        "artifacts:",
                        '  - "old_artifact.pdf"',
                        '  - "another_old.pdf"',
                        "tags:",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            # 创建新文件用于导入
            source = base_dir / "replacement.pdf"
            source.write_bytes(b"%PDF-1.4")
            app_data = base_dir / "app-data"

            with (
                patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir),
                patch("tools.sidecar.handlers.evidence._APP_DATA_DIR", app_data),
            ):
                result = handle_evidence_import(
                    {
                        "meta": {"correlation_id": "corr_024"},
                        "source_paths": [str(source)],
                        "target_evidence_id": "ec_existing",
                        "mode": "replace",
                    }
                )
                detail = handle_evidence_get(
                    {
                        "meta": {"correlation_id": "corr_025"},
                        "evidence_id": "ec_existing",
                    }
                )

        self.assertEqual(result["meta"]["correlation_id"], "corr_024")
        self.assertEqual(result["evidence_id"], "ec_existing")
        self.assertEqual(len(result["imported_resources"]), 1)
        artifacts = detail["evidence"]["artifacts"]
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["filename"], "replacement.pdf")


class EvidenceDeleteTests(unittest.TestCase):
    def test_delete_soft_deletes_file(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            evidence_dir = Path(tmp_dir)
            original_path = evidence_dir / "ec_001.yaml"
            original_path.write_text(SAMPLE_YAML, encoding="utf-8")
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", evidence_dir):
                result = handle_evidence_delete(
                    {
                        "meta": {"correlation_id": "corr_013"},
                        "evidence_id": "ec-2026-001",
                    }
                )
                self.assertEqual(result["meta"]["correlation_id"], "corr_013")
                self.assertTrue(result["deleted"])
                self.assertFalse(original_path.exists())
                self.assertTrue((evidence_dir / "ec_001.yaml.deleted").exists())

    def test_delete_not_found_raises(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            with patch("tools.sidecar.handlers.evidence._EVIDENCE_DIR", Path(tmp_dir)):
                with self.assertRaises(KeyError):
                    handle_evidence_delete(
                        {
                            "meta": {"correlation_id": "corr_014"},
                            "evidence_id": "missing",
                        }
                    )


if __name__ == "__main__":
    unittest.main()
