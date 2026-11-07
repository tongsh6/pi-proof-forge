import unittest

from tools.domain.invariants import check_evidence_eligible, check_no_fabrication
from tools.domain.models import EvidenceCard
from tools.errors.exceptions import FabricationGuardError


def _card(
    results: tuple[str, ...] = ("latency reduced by 30%",),
    artifacts: tuple[str, ...] = ("pr-123",),
) -> EvidenceCard:
    return EvidenceCard(
        id="ec-1",
        title="Perf optimization",
        raw_source="raw.txt",
        results=results,
        artifacts=artifacts,
    )


class InvariantsTests(unittest.TestCase):
    def test_evidence_eligible_when_results_and_artifacts_exist(self) -> None:
        self.assertTrue(check_evidence_eligible(_card()))

    def test_evidence_not_eligible_when_results_missing(self) -> None:
        self.assertFalse(check_evidence_eligible(_card(results=())))

    def test_evidence_not_eligible_when_artifacts_missing(self) -> None:
        self.assertFalse(check_evidence_eligible(_card(artifacts=())))

    def test_no_fabrication_allows_traceable_content(self) -> None:
        check_no_fabrication("This card delivered latency reduced by 30%.", [_card()])

    def test_no_fabrication_raises_when_untraceable(self) -> None:
        with self.assertRaises(FabricationGuardError):
            check_no_fabrication("This claim has no source.", [_card()])


if __name__ == "__main__":
    _ = unittest.main()
