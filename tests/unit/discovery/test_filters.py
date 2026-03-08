import unittest

from tools.discovery.filters import filter_candidates_by_policy
from tools.domain.value_objects import Candidate


class DiscoveryFilterTests(unittest.TestCase):
    def test_filters_excluded_candidates(self) -> None:
        candidates = [
            Candidate(
                candidate_id="cand-001",
                direction="backend",
                company="Outsource Labs",
                job_url="https://example.com/job/1",
                confidence=0.7,
                source="job_leads",
                merged_sources=("job_leads",),
            ),
            Candidate(
                candidate_id="cand-002",
                direction="backend",
                company="Acme Inc",
                job_url="https://example.com/job/2",
                confidence=0.8,
                source="job_leads",
                merged_sources=("job_leads",),
            ),
        ]
        kept, excluded = filter_candidates_by_policy(candidates, ["contains:outsource"])
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(kept[0].company, "Acme Inc")

    def test_no_exclusions_keeps_all(self) -> None:
        candidates = [
            Candidate(
                candidate_id="cand-003",
                direction="backend",
                company="Acme Inc",
                job_url="https://example.com/job/3",
                confidence=0.5,
                source="job_profiles",
                merged_sources=("job_profiles",),
            )
        ]
        kept, excluded = filter_candidates_by_policy(candidates, [])
        self.assertEqual(len(kept), 1)
        self.assertEqual(len(excluded), 0)

    def test_filters_by_legal_entity(self) -> None:
        candidates = [
            Candidate(
                candidate_id="cand-004",
                direction="backend",
                company="Acme Staffing",
                job_url="https://example.com/job/4",
                confidence=0.6,
                source="job_profiles",
                merged_sources=("job_profiles",),
                legal_entity="Acme Holdings Ltd",
            )
        ]
        kept, excluded = filter_candidates_by_policy(
            candidates,
            [],
            ["Acme Holdings Ltd"],
        )
        self.assertEqual(len(kept), 0)
        self.assertEqual(len(excluded), 1)


if __name__ == "__main__":
    unittest.main()
