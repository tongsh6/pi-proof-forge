import json
import unittest
import hashlib
from importlib import import_module
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest

from tools.config.fragments import PolicyConfig
from tools.domain.value_objects import Candidate
from tools.domain.models import ResumeOutput
from tools.domain.result import Err, Ok
from tools.domain.value_objects import DeliveryResult


def _delivery_loop(run_id, channel, store=None):
    return _agent_loop_class()(
        policy=AgentLoopTests()._policy(), run_id=run_id,
        channels=[channel], run_store=store,
    )


def _delivery_candidate():
    return Candidate("candidate-1", "backend", "Example", "https://example.com/job/1", 1.0, "test", ())


def test_legacy_candidate_has_empty_platform_provenance_defaults():
    candidate = _delivery_candidate()
    for field in ("platform", "platform_job_id", "platform_job_type", "job_profile_id", "jd_status", "source_jd_sha256"):
        assert getattr(candidate, field, None) == ""


def test_delivery_hands_current_pdf_to_channel_without_overwriting_prior_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tools.infra.export import pdf_exporter
    # 仅替代浏览器进程边界；HTML、目录隔离、指纹与通道传参使用真实实现。
    monkeypatch.setattr(pdf_exporter, "_render_html_to_pdf", lambda html, pdf: pdf.write_bytes(b"%PDF-1.4\nlocal renderer fixture\n%%EOF\n"))
    (tmp_path / "outputs").mkdir()
    prior = tmp_path / "outputs/v1.md"
    prior.write_text("previous resume")
    channel = Mock(channel_id="test")
    channel.deliver.return_value = Ok(DeliveryResult("test", False, "", "captured locally", outcome="not_submitted"))
    store = _file_run_store_class()(base_dir=str(tmp_path / "runs"))
    loop = _delivery_loop("pdf-delivery", channel, store)
    resume = ResumeOutput("v1", "jp-test", "# 测试候选人\n\n## 核心技能\nJava\n", "markdown")

    candidate = replace(
        _delivery_candidate(), platform="test", platform_job_id="job-123",
        platform_job_type="2", job_profile_id="jp-test", jd_status="complete",
        source_jd_sha256="a" * 64,
    )
    result = loop._run_delivery(candidate, 0, resume)

    assert isinstance(result, Ok)
    request = channel.deliver.call_args.args[0]
    pdf = Path(request.resume_path)
    assert pdf.suffix == ".pdf"
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert pdf.with_suffix(".md").read_text() == resume.content
    assert "测试候选人" in pdf.with_suffix(".html").read_text()
    assert prior.read_text() == "previous resume"
    assert request.channel == "test"
    assert request.metadata["platform"] == "test"
    assert request.metadata["platform_job_id"] == "job-123"
    assert request.metadata["platform_job_type"] == "2"
    assert request.metadata["job_profile_id"] == "jp-test"
    assert request.metadata["jd_status"] == "complete"
    assert request.metadata["source"] == "test"
    assert request.metadata["source_jd_sha256"] == "a" * 64
    assert request.metadata["resume_version"] == "v1"
    assert request.metadata["resume_pdf_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert request.metadata["resume_markdown_sha256"] == hashlib.sha256(resume.content.encode()).hexdigest()
    prepared = [e for e in store.load_events("pdf-delivery") if e.event_type == "resume_exported"]
    assert len(prepared) == 1
    assert prepared[0].payload["resume_pdf_sha256"] == request.metadata["resume_pdf_sha256"]

    original_bytes = pdf.read_bytes()
    loop._run_delivery(candidate, 0, ResumeOutput("v1", "jp-test", "# 另一版\n", "markdown"))
    assert channel.deliver.call_args.args[0].resume_path != str(pdf)
    assert pdf.read_bytes() == original_bytes


@pytest.mark.parametrize("failure", [RuntimeError("PDF_RENDERER_UNAVAILABLE"), OSError("disk unavailable")])
def test_delivery_export_failure_does_not_invoke_any_channel(tmp_path, monkeypatch, failure):
    monkeypatch.chdir(tmp_path)
    from tools.infra.export import pdf_exporter
    renderer = Mock(side_effect=failure)
    monkeypatch.setattr(pdf_exporter, "markdown_to_pdf", renderer)
    channel = Mock(channel_id="test")
    loop = _delivery_loop("failed-export", channel)

    result = loop._run_delivery(replace(_delivery_candidate(), platform="test"), 0, ResumeOutput("v1", "jp-test", "# Test\n", "markdown"))

    assert isinstance(result, Err)
    assert result.error.reason == "resume_pdf_export_failed"
    channel.deliver.assert_not_called()


@pytest.mark.parametrize(("platform", "job_url", "expected_channel"), [
    ("liepin", "https://www.liepin.com/job/123.shtml", "liepin"),
    ("", "https://liepin.com/job/123.shtml", "liepin"),
    ("", "https://www.zhipin.com/job_detail/123.html", "boss"),
    ("", "https://jobs.zhaopin.com/123.htm", "zhilian"),
    ("", "https://jobs.51job.com/shanghai/123.html", "51job"),
    ("", "https://WWW.LIEPIN.COM:443/job/123.shtml", "liepin"),
])
def test_delivery_routes_platform_or_known_https_host_not_business_direction(
    tmp_path, monkeypatch, platform, job_url, expected_channel,
):
    monkeypatch.chdir(tmp_path)
    from tools.infra.export import pdf_exporter
    monkeypatch.setattr(pdf_exporter, "_render_html_to_pdf", lambda html, pdf: pdf.write_bytes(b"%PDF-1.4\n%%EOF\n"))
    channel = Mock(channel_id=expected_channel)
    channel.deliver.return_value = Ok(DeliveryResult(expected_channel, False, "", "本地捕获", outcome="not_submitted"))
    candidate = replace(_delivery_candidate(), platform=platform, job_url=job_url)

    result = _delivery_loop("routing", channel)._run_delivery(
        candidate, 0, ResumeOutput("v1", "jp-test", "# Test\n", "markdown"),
    )

    assert isinstance(result, Ok)
    request = channel.deliver.call_args.args[0]
    assert request.channel == expected_channel
    assert request.metadata["platform"] == expected_channel


@pytest.mark.parametrize(("platform", "job_url", "expected_reason"), [
    ("", "https://example.com/job/1", "unknown_platform"),
    ("", "https://liepin.com.evil.example/job/1", "unknown_platform"),
    ("", "https://notliepin.com/job/1", "unknown_platform"),
    ("", "http://www.liepin.com/job/1", "invalid_job_url"),
    ("", "https://user@liepin.com/job/1", "invalid_job_url"),
    ("", "https://liepin.com:444/job/1", "invalid_job_url"),
    ("", "https://liepin.com:bad/job/1", "invalid_job_url"),
    ("", "https://[bad/job/1", "invalid_job_url"),
    ("", "https://evil.example\\foo.liepin.com/job/1", "invalid_job_url"),
    ("", "https://evil.example foo.liepin.com/job/1", "invalid_job_url"),
    ("", "https://www.lie\npin.com/job/1", "invalid_job_url"),
    ("boss", "https://www.liepin.com/job/1", "platform_url_mismatch"),
    ("liepin", "https://example.com/job/1", "platform_url_mismatch"),
    ("test", "https://www.zhipin.com/job/1", "platform_url_mismatch"),
])
def test_delivery_rejects_unknown_or_conflicting_platform_before_export_or_channel_io(
    tmp_path, monkeypatch, platform, job_url, expected_reason,
):
    monkeypatch.chdir(tmp_path)
    from tools.infra.export import pdf_exporter
    renderer = Mock()
    monkeypatch.setattr(pdf_exporter, "markdown_to_pdf", renderer)
    channel = Mock(channel_id=platform or "backend")
    channel.deliver.return_value = Ok(DeliveryResult(channel.channel_id, True, "", "不应触发"))
    candidate = replace(_delivery_candidate(), platform=platform, job_url=job_url)

    result = _delivery_loop("blocked-route", channel)._run_delivery(
        candidate, 0, ResumeOutput("v1", "jp-test", "# Test\n", "markdown"),
    )

    assert isinstance(result, Err)
    assert result.error.reason == expected_reason
    channel.deliver.assert_not_called()
    renderer.assert_not_called()
    assert not (tmp_path / "outputs").exists()


def test_delivery_without_matching_channel_stops_before_export_or_external_io(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tools.infra.export import pdf_exporter
    renderer = Mock()
    monkeypatch.setattr(pdf_exporter, "markdown_to_pdf", renderer)
    channel = Mock(channel_id="liepin")
    candidate = replace(_delivery_candidate(), platform="boss", job_url="https://www.zhipin.com/job/1")

    result = _delivery_loop("missing-channel", channel)._run_delivery(
        candidate, 0, ResumeOutput("v1", "jp-test", "# Test\n", "markdown"),
    )

    assert isinstance(result, Err)
    assert result.error.reason == "no_channel"
    channel.deliver.assert_not_called()
    renderer.assert_not_called()


def test_official_source_does_not_fall_through_to_legacy_browser_delivery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from tools.infra.export import pdf_exporter
    renderer = Mock()
    monkeypatch.setattr(pdf_exporter, "markdown_to_pdf", renderer)
    channel = Mock(channel_id="liepin")
    candidate = replace(
        _delivery_candidate(), platform="liepin", source="liepin_official",
        job_url="https://www.liepin.com/job/123.shtml", jd_status="complete",
    )

    result = _delivery_loop("official-contract-blocked", channel)._run_delivery(
        candidate, 0, ResumeOutput("v1", "jp-test", "# Test\n", "markdown"),
    )

    assert isinstance(result, Err)
    assert result.error.reason == "official_delivery_contract_unverified"
    channel.deliver.assert_not_called()
    renderer.assert_not_called()


def _agent_loop_class():
    module = import_module("tools.orchestration.agent_loop")
    return module.AgentLoop


def _file_run_store_class():
    module = import_module("tools.infra.persistence.file_run_store")
    return module.FileRunStore


def _rank_candidate_batch():
    module = import_module("tools.orchestration.agent_loop")
    return module._rank_candidate_batch


class AgentLoopTests(unittest.TestCase):
    def _policy(self, max_rounds: int = 2) -> PolicyConfig:
        return PolicyConfig(
            n_pass_required=1,
            matching_threshold=0.6,
            evaluation_threshold=0.6,
            max_rounds=max_rounds,
            gate_mode="simulate",
            delivery_mode="auto",
            batch_review=False,
            excluded_companies=(),
            excluded_legal_entities=(),
        )

    def _policy_with_limits(self, max_rounds: int, max_deliveries: int) -> PolicyConfig:
        return PolicyConfig(
            n_pass_required=1,
            matching_threshold=0.6,
            evaluation_threshold=0.6,
            max_rounds=max_rounds,
            gate_mode="simulate",
            delivery_mode="auto",
            batch_review=False,
            excluded_companies=(),
            excluded_legal_entities=(),
            max_deliveries=max_deliveries,
        )

    def test_dry_run_completes_early(self) -> None:
        with TemporaryDirectory() as tmp:
            store = _file_run_store_class()(base_dir=tmp)
            loop = _agent_loop_class()(
                policy=self._policy(3),
                run_id="run-1",
                dry_run=True,
                run_store=store,
            )
            result = loop.run()
            self.assertEqual(result.status, "DRY_RUN_COMPLETE")
            self.assertEqual(result.rounds_completed, 1)
            replayed = loop.replay_state()
            self.assertEqual(replayed.current_status, "DONE")

    def test_non_dry_run_reaches_max_rounds(self) -> None:
        with TemporaryDirectory() as tmp:
            store = _file_run_store_class()(base_dir=tmp)
            loop = _agent_loop_class()(
                policy=self._policy(2),
                run_id="run-2",
                dry_run=False,
                run_store=store,
            )
            result = loop.run()
            self.assertEqual(result.status, "DONE")
            self.assertEqual(result.rounds_completed, 2)
            events = store.load_events("run-2")
            event_types = [event.event_type for event in events]
            self.assertIn("DELIVER", event_types)

    def test_run_agent_cli_outputs_json(self) -> None:
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                """n_pass_required: 1
matching_threshold: 0.6
evaluation_threshold: 0.6
max_rounds: 2
gate_mode: strict
delivery_mode: auto
batch_review: false
excluded_companies: []
excluded_legal_entities: []
""",
                encoding="utf-8",
            )

            import subprocess

            result = subprocess.run(
                [
                    "python3",
                    "tools/run_agent.py",
                    "--policy",
                    str(policy_path),
                    "--dry-run",
                    "--run-id",
                    "run-test-cli",
                    "--output-dir",
                    str(Path(tmp) / "agent_runs"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            output_lines = [line for line in result.stdout.splitlines() if line.strip()]
            payload = json.loads(output_lines[-1])
            self.assertEqual(payload["run_id"], "run-test-cli")
            self.assertIn(payload["status"], ("DRY_RUN_COMPLETE", "DONE"))
            run_log = Path(tmp) / "agent_runs" / "run-test-cli" / "run_log.json"
            self.assertTrue(run_log.exists())

    def test_simplified_simulation_does_not_consume_real_delivery_limit(self) -> None:
        with TemporaryDirectory() as tmp:
            store = _file_run_store_class()(base_dir=tmp)
            loop = _agent_loop_class()(
                policy=self._policy_with_limits(max_rounds=5, max_deliveries=1),
                run_id="run-max-deliveries",
                dry_run=False,
                run_store=store,
            )
            result = loop.run()
            self.assertEqual(result.status, "DONE")
            self.assertEqual(result.rounds_completed, 5)
            events = store.load_events("run-max-deliveries")
            deliveries = [event for event in events if event.event_type == "DELIVER"]
            self.assertTrue(deliveries)
            self.assertTrue(all(event.payload.get("success") is False for event in deliveries))

    def test_candidate_batch_ranking_is_stable_and_excludes_selected(self) -> None:
        candidates = (
            Candidate(
                candidate_id="cand-b",
                direction="backend",
                company="B",
                job_url="https://example.com/b",
                confidence=0.9,
                source="job_leads",
                merged_sources=("job_leads",),
            ),
            Candidate(
                candidate_id="cand-a",
                direction="backend",
                company="A",
                job_url="https://example.com/a",
                confidence=0.9,
                source="job_leads",
                merged_sources=("job_leads",),
            ),
            Candidate(
                candidate_id="cand-c",
                direction="backend",
                company="C",
                job_url="https://example.com/c",
                confidence=0.7,
                source="job_leads",
                merged_sources=("job_leads",),
            ),
        )

        ranked = _rank_candidate_batch()(candidates, {"cand-a"})

        self.assertEqual([candidate.candidate_id for candidate in ranked], ["cand-b", "cand-c"])


if __name__ == "__main__":
    _ = unittest.main()
