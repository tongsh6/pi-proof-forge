import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.orchestration.pipeline import PipelineFlowConfig, has_llm_env, run_pipeline_flow


def _write_inputs(tmp_dir: str) -> tuple[Path, Path, Path, PipelineFlowConfig]:
    root = Path(tmp_dir)
    policy_path = root / "policy.yaml"
    policy_path.write_text("excluded_companies: []\n", encoding="utf-8")
    job_profile = root / "jp-003.yaml"
    job_profile.write_text(
        "\n".join(
            [
                "target_role: 'Backend Engineer'",
                "company: 'Product Labs'",
                "source_jd: 'https://example.com/jd/3'",
                "",
            ]
        ),
        encoding="utf-8",
    )
    raw_path = root / "raw.txt"
    raw_path.write_text("结果：接口延迟下降 30%\n证据：pr-1\n", encoding="utf-8")
    evidence_dir = root / "evidence"
    evidence_dir.mkdir()
    config = PipelineFlowConfig(
        raw_path=raw_path,
        job_profile_path=job_profile,
        evidence_dir=evidence_dir,
        run_id="test-run-record",
    )
    return policy_path, job_profile, evidence_dir, config


class PipelineFlowTests(unittest.TestCase):
    def test_success_writes_unified_run_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path, job_profile, evidence_dir, config = _write_inputs(tmp_dir)
            cwd = os.getcwd()
            with (
                mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}),
                mock.patch(
                    "tools.orchestration.pipeline.run_matching_flow",
                    return_value=0,
                ) as matching_mock,
                mock.patch(
                    "tools.orchestration.pipeline.run_generation_flow",
                    return_value=0,
                ) as generation_mock,
                mock.patch(
                    "tools.orchestration.pipeline.run_evaluation_flow",
                    return_value=0,
                ) as evaluation_mock,
            ):
                os.chdir(tmp_dir)
                try:
                    code = run_pipeline_flow(config)
                finally:
                    os.chdir(cwd)

            log_path = Path(tmp_dir) / "outputs" / "agent_runs" / "test-run-record" / "run_log.json"
            events = json.loads(log_path.read_text(encoding="utf-8"))
            summary_path = log_path.parent / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            evidence_output = evidence_dir / "ec-test-run-record.yaml"
            evidence_exists = evidence_output.is_file()

        self.assertEqual(code, 0)
        self.assertEqual(matching_mock.call_count, 1)
        self.assertEqual(generation_mock.call_count, 1)
        self.assertEqual(evaluation_mock.call_count, 1)
        self.assertTrue(evidence_exists)
        event_types = [event["event_type"] for event in events]
        self.assertEqual(event_types[0], "PIPELINE_START")
        self.assertEqual(event_types[-1], "PIPELINE_DONE")
        self.assertEqual(event_types.count("PIPELINE_STEP_SUCCESS"), 4)
        steps = [
            event["payload"].get("step")
            for event in events
            if event["event_type"] == "PIPELINE_STEP_SUCCESS"
        ]
        self.assertEqual(
            steps,
            [
                "evidence-extraction-rule",
                "matching-scoring",
                "generation",
                "evaluation",
            ],
        )
        self.assertEqual(summary["status"], "DONE")
        self.assertEqual(summary["exit_code"], 0)
        self.assertEqual(
            summary["artifacts"]["run_record"],
            "outputs/agent_runs/test-run-record/run_log.json",
        )

    def test_returns_2_when_company_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            policy_path = root / "policy.yaml"
            policy_path.write_text(
                "\n".join(["exclusion_list:", "  - 'contains:Outsource'", ""]),
                encoding="utf-8",
            )
            job_profile = root / "jp-001.yaml"
            job_profile.write_text(
                "\n".join(
                    [
                        "target_role: 'Backend Engineer'",
                        "company: 'Outsource Labs'",
                        "source_jd: 'https://example.com/jd'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            raw_path = root / "raw.txt"
            raw_path.write_text("sample", encoding="utf-8")
            evidence_dir = root / "evidence"
            evidence_dir.mkdir()
            config = PipelineFlowConfig(
                raw_path=raw_path,
                job_profile_path=job_profile,
                evidence_dir=evidence_dir,
                run_id="run-excluded",
            )
            cwd = os.getcwd()
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                os.chdir(tmp_dir)
                try:
                    code = run_pipeline_flow(config)
                finally:
                    os.chdir(cwd)
            audit_path = root / "outputs" / "run-excluded" / "run_log.json"
            audit_text = audit_path.read_text(encoding="utf-8")

        self.assertEqual(code, 2)
        self.assertIn("excluded_by_policy", audit_text)

    def test_returns_2_when_legal_entity_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            policy_path = root / "policy.yaml"
            policy_path.write_text(
                "\n".join(
                    [
                        "excluded_legal_entities:",
                        "  - 'Acme Holdings Ltd'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            job_profile = root / "jp-002.yaml"
            job_profile.write_text(
                "\n".join(
                    [
                        "target_role: 'Backend Engineer'",
                        "company: 'Acme Staffing'",
                        "legal_entity: 'Acme Holdings Ltd'",
                        "source_jd: 'https://example.com/jd/2'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            raw_path = root / "raw.txt"
            raw_path.write_text("sample", encoding="utf-8")
            evidence_dir = root / "evidence"
            evidence_dir.mkdir()
            config = PipelineFlowConfig(
                raw_path=raw_path,
                job_profile_path=job_profile,
                evidence_dir=evidence_dir,
                run_id="run-legal-excluded",
            )
            cwd = os.getcwd()
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                os.chdir(tmp_dir)
                try:
                    code = run_pipeline_flow(config)
                finally:
                    os.chdir(cwd)

        self.assertEqual(code, 2)

    def test_fails_when_selected_evidence_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path, _job_profile, evidence_dir, config = _write_inputs(tmp_dir)
            cwd = os.getcwd()
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                os.chdir(tmp_dir)
                try:
                    code = run_pipeline_flow(
                        PipelineFlowConfig(
                            raw_path=config.raw_path,
                            job_profile_path=config.job_profile_path,
                            evidence_dir=evidence_dir,
                            run_id="run-skip",
                            skip_evidence_extraction=True,
                        )
                    )
                finally:
                    os.chdir(cwd)
            summary = json.loads(
                (
                    Path(tmp_dir)
                    / "outputs"
                    / "agent_runs"
                    / "run-skip"
                    / "summary.json"
                ).read_text(encoding="utf-8")
            )

        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "FAILED")
        self.assertEqual(summary["failed_step"], "evidence-selection")


class HasLlmEnvTests(unittest.TestCase):
    def test_keyless_strata_with_model_is_available(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"LLM_PROVIDER": "strata", "LLM_MODEL": "iq3_s"},
            clear=True,
        ):
            self.assertTrue(has_llm_env())

    def test_keyless_lm_studio_with_model_is_available(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"LLM_PROVIDER": "lm_studio", "LLM_MODEL": "local"},
            clear=True,
        ):
            self.assertTrue(has_llm_env())

    def test_online_provider_without_api_key_is_unavailable(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"LLM_PROVIDER": "openai", "LLM_MODEL": "gpt-4"},
            clear=True,
        ):
            self.assertFalse(has_llm_env())

    def test_missing_model_is_unavailable(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"LLM_PROVIDER": "strata"},
            clear=True,
        ):
            self.assertFalse(has_llm_env())

    def test_online_provider_with_api_key_is_available(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "gpt-4",
                "LLM_API_KEY": "sk-test",
            },
            clear=True,
        ):
            self.assertTrue(has_llm_env())


if __name__ == "__main__":
    _ = unittest.main()
