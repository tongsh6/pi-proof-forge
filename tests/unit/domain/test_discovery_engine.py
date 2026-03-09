import unittest
from importlib import import_module

from tools.config.fragments import PolicyConfig
from tools.domain.value_objects import Candidate


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
        result = engine.filter_candidates([_candidate("Acme")])
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(len(result.excluded), 0)

    def test_filter_excludes_by_exact_company(self) -> None:
        engine = _discovery_engine_class()(_policy(excluded_companies=("exact:Acme",)))
        result = engine.filter_candidates([_candidate("Acme")])
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(len(result.excluded), 1)
        self.assertEqual(result.excluded[0].reason, "excluded_by_policy")

    def test_filter_excludes_by_contains_company(self) -> None:
        engine = _discovery_engine_class()(
            _policy(excluded_companies=("contains:outsource",))
        )
        result = engine.filter_candidates([_candidate("Acme Outsource Ltd")])
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(len(result.excluded), 1)

    def test_filter_excludes_by_legal_entity(self) -> None:
        engine = _discovery_engine_class()(
            _policy(excluded_legal_entities=("Acme Legal Entity",))
        )
        result = engine.filter_candidates(
            [_candidate("Acme", legal_entity="Acme Legal Entity")]
        )
        self.assertEqual(len(result.accepted), 0)
        self.assertEqual(len(result.excluded), 1)


if __name__ == "__main__":
    _ = unittest.main()
