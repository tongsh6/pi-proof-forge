import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tools.policy.exclusions import is_company_excluded, load_exclusion_list


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


if __name__ == "__main__":
    unittest.main()
