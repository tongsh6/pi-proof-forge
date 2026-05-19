import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.config.fragments import PolicyConfig
from tools.domain.value_objects import Candidate
from tools.engines.discovery.job_leads_loader import (
    discover_candidates,
    load_candidates_from_job_leads,
)


def _discovery_engine_class():
    module = import_module("tools.engines.discovery.discovery_engine")
    return module.DiscoveryEngine


def _policy(
    excluded_companies: tuple[str, ...] = (),
    excluded_legal_entities: tuple[str, ...] = (),
) -> PolicyConfig:
    return PolicyConfig(
        n_pass_required=1,
        matching_threshold=0.6,
        evaluation_threshold=0.6,
        max_rounds=5,
        gate_mode="strict",
        delivery_mode="auto",
        batch_review=False,
        excluded_companies=excluded_companies,
        excluded_legal_entities=excluded_legal_entities,
    )


def _candidate(company: str, legal_entity: str = "") -> Candidate:
    return Candidate(
        candidate_id=f"cand-{company}",
        direction="backend",
        company=company,
        job_url="https://example.com/job",
        confidence=0.8,
        source="job_leads",
        merged_sources=("job_leads",),
        legal_entity=legal_entity,
    )


class DiscoveryEngineTests(unittest.TestCase):
    def test_filter_keeps_non_excluded_candidates(self) -> None:
        engine = _discovery_engine_class()(_policy())
        result = engine.discover([_candidate("Acme")])
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(len(result.excluded), 0)

    def test_filter_excludes_by_exact_company(self) -> None:
        engine = _discovery_engine_class()(_policy(excluded_companies=("exact:Acme",)))
        result = engine.discover([_candidate("Acme")])
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(len(result.excluded), 1)
        self.assertEqual(result.excluded[0].reason, "excluded_by_policy")

    def test_filter_excludes_by_contains_company(self) -> None:
        engine = _discovery_engine_class()(
            _policy(excluded_companies=("contains:outsource",))
        )
        result = engine.discover([_candidate("Acme Outsource Ltd")])
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(len(result.excluded), 1)

    def test_filter_excludes_by_legal_entity(self) -> None:
        engine = _discovery_engine_class()(
            _policy(excluded_legal_entities=("Acme Legal Entity",))
        )
        result = engine.discover(
            [_candidate("Acme", legal_entity="Acme Legal Entity")]
        )
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(len(result.excluded), 1)

    def test_candidate_fallback_does_not_search_liepin_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            leads_dir = root / "job_leads"
            jd_dir = root / "jd_inputs"
            jp_dir = root / "job_profiles"
            leads_dir.mkdir()
            jd_dir.mkdir()
            jp_dir.mkdir()
            (jp_dir / "jp-test.yaml").write_text(
                "target_role: Backend Engineer\n"
                "keywords:\n"
                "  - Java\n"
                "  - Redis\n",
                encoding="utf-8",
            )

            with patch(
                "tools.engines.discovery.liepin_search.discover_and_filter",
                return_value=[
                    {
                        "job_url": "https://www.liepin.com/job/1.shtml",
                        "company": "Live Search Co",
                        "position": "Backend Engineer",
                    }
                ],
            ) as search:
                candidates = discover_candidates(
                    base_dir=leads_dir,
                    base_jd_dir=jd_dir,
                    base_jp_dir=jp_dir,
                )

            search.assert_not_called()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].source, "job_profiles:jp-test")

    def test_candidate_fallback_does_not_search_boss_agent_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            leads_dir = root / "job_leads"
            jd_dir = root / "jd_inputs"
            jp_dir = root / "job_profiles"
            leads_dir.mkdir()
            jd_dir.mkdir()
            jp_dir.mkdir()
            (jp_dir / "jp-test.yaml").write_text(
                "target_role: Backend Engineer\n"
                "keywords:\n"
                "  - Java\n"
                "  - Redis\n",
                encoding="utf-8",
            )

            with patch(
                "tools.infra.discovery.boss_agent_cli.search_jobs",
                return_value=[
                    {
                        "job_url": "https://www.zhipin.com/job_detail/abc.html",
                        "company": "Boss Search Co",
                        "position": "Backend Engineer",
                        "platform": "boss",
                    }
                ],
            ) as search:
                candidates = discover_candidates(
                    base_dir=leads_dir,
                    base_jd_dir=jd_dir,
                    base_jp_dir=jp_dir,
                )

            search.assert_not_called()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].source, "job_profiles:jp-test")

    def test_enabled_boss_agent_search_maps_results_to_candidates(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            leads_dir = root / "job_leads"
            jd_dir = root / "jd_inputs"
            jp_dir = root / "job_profiles"
            leads_dir.mkdir()
            jd_dir.mkdir()
            jp_dir.mkdir()

            with patch(
                "tools.infra.discovery.boss_agent_cli.search_jobs",
                return_value=[
                    {
                        "url": "https://www.zhipin.com/job_detail/backend.html",
                        "company_name": "Example Boss",
                        "title": "Java Backend Engineer",
                        "platform": "boss",
                        "confidence": 0.81,
                    },
                    {
                        "job_url": "https://sou.zhaopin.com/job/123",
                        "company": "Example Zhilian",
                        "position": "后端开发",
                        "platform": "zhilian",
                    },
                ],
            ) as search:
                candidates = discover_candidates(
                    base_dir=leads_dir,
                    base_jd_dir=jd_dir,
                    base_jp_dir=jp_dir,
                    enable_boss_agent_search=True,
                    search_keywords=["Java", "Redis"],
                    search_city="北京",
                    boss_agent_platforms=("boss", "zhilian"),
                )

            search.assert_called_once_with(
                ["Java", "Redis"],
                city="北京",
                platforms=("boss", "zhilian"),
                limit=5,
            )
            self.assertEqual(len(candidates), 2)
            self.assertEqual(candidates[0].company, "Example Boss")
            self.assertEqual(candidates[0].job_url, "https://www.zhipin.com/job_detail/backend.html")
            self.assertEqual(candidates[0].confidence, 0.81)
            self.assertEqual(candidates[0].source, "boss_agent:boss")
            self.assertEqual(candidates[1].source, "boss_agent:zhilian")

    def test_loads_structured_job_leads_with_urls(self) -> None:
        with TemporaryDirectory() as tmp:
            leads_dir = Path(tmp)
            (leads_dir / "jl-captured.yaml").write_text(
                'generated_at: "2026-05-08T18:18:46Z"\n'
                "items:\n"
                '  - job_url: "https://www.liepin.com/job/1971416782.shtml"\n'
                '    position: "架构师"\n'
                '    company_name: "Example Tech"\n'
                "    direction: backend\n"
                "    confidence: 0.85\n",
                encoding="utf-8",
            )

            candidates = load_candidates_from_job_leads(leads_dir)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0].job_url,
            "https://www.liepin.com/job/1971416782.shtml",
        )
        self.assertEqual(candidates[0].company, "Example Tech")
        self.assertEqual(candidates[0].confidence, 0.85)


if __name__ == "__main__":
    _ = unittest.main()
