import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.policy.exclusions import (
    PolicyExclusions,
    is_company_excluded,
    load_exclusion_list,
    load_exclusion_policy,
    load_legal_entity_exclusion_list,
    match_exclusion,
)


class ExclusionPolicyTests(unittest.TestCase):
    def test_load_exclusion_list_from_env_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            policy_path.write_text(
                "excluded_companies:\n  - 'exact:Acme Inc'\n  - 'contains:外包'\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                exclusions = load_exclusion_list()
        self.assertEqual(exclusions, ["exact:Acme Inc", "contains:外包"])

    def test_company_exact_match(self) -> None:
        exclusions = ["Acme Inc"]
        self.assertTrue(is_company_excluded("Acme Inc", exclusions))
        self.assertTrue(is_company_excluded("acmeinc", exclusions))
        self.assertFalse(is_company_excluded("Acme Labs", exclusions))

    def test_company_contains_match(self) -> None:
        exclusions = ["contains:外包", "contains:Consulting"]
        self.assertTrue(is_company_excluded("某某外包服务", exclusions))
        self.assertTrue(is_company_excluded("Tech Consulting LLC", exclusions))
        self.assertFalse(is_company_excluded("Tech Labs", exclusions))

    def test_company_exact_prefix_match(self) -> None:
        exclusions = ["exact:Acme Inc"]
        self.assertTrue(is_company_excluded("Acme Inc", exclusions))
        self.assertFalse(is_company_excluded("Acme Incorporated", exclusions))

    def test_load_exclusion_policy_merges_legacy_and_new_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            policy_path.write_text(
                "\n".join(
                    [
                        "exclusion_list:",
                        "  - 'contains:Vendor'",
                        "excluded_companies:",
                        "  - 'exact:Acme Inc'",
                        "excluded_legal_entities:",
                        "  - 'Acme Holdings Ltd'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                policy = load_exclusion_policy()
        self.assertEqual(
            list(policy.company_rules), ["contains:Vendor", "exact:Acme Inc"]
        )
        self.assertEqual(list(policy.legal_entities), ["Acme Holdings Ltd"])

    def test_load_exclusion_policy_supports_nested_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            policy_path.write_text(
                "\n".join(
                    [
                        "filters:",
                        "  excluded_companies:",
                        "    - match: exact",
                        '      value: "Example Tech Co"',
                        "    - match: contains",
                        '      value: "外包"',
                        "  excluded_legal_entities:",
                        '    - "Example Holdings Ltd"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                exclusions = load_exclusion_list()
                legal_entities = load_legal_entity_exclusion_list()
        self.assertEqual(exclusions, ["exact:Example Tech Co", "contains:外包"])
        self.assertEqual(legal_entities, ["Example Holdings Ltd"])

    def test_match_exclusion_prefers_legal_entity(self) -> None:
        policy = PolicyExclusions(
            company_rules=("contains:Outsource",),
            legal_entities=("Acme Holdings Ltd",),
        )
        reason = match_exclusion(
            company="Outsource Labs",
            legal_entity="Acme Holdings Ltd",
            policy=policy,
        )
        self.assertEqual(reason, "excluded_legal_entity")


if __name__ == "__main__":
    unittest.main()
