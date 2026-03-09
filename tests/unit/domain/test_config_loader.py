import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.config.loader import load_policy_config
from tools.config.validator import validate_policy_config
from tools.errors.exceptions import PolicyError

_VALID_POLICY = """n_pass_required: 2
matching_threshold: 0.6
evaluation_threshold: 0.5
max_rounds: 10
max_deliveries: 3
gate_mode: strict
delivery_mode: auto
batch_review: false
excluded_companies:
  - exact:Acme Inc
excluded_legal_entities:
  - Acme Holdings Ltd
"""


class ConfigLoaderTests(unittest.TestCase):
    def test_load_policy_config(self) -> None:
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(_VALID_POLICY, encoding="utf-8")
            cfg = load_policy_config(str(policy_path))
            self.assertEqual(cfg.n_pass_required, 2)
            self.assertEqual(cfg.delivery_mode, "auto")
            self.assertEqual(cfg.max_deliveries, 3)
            self.assertIn("exact:Acme Inc", cfg.excluded_companies)

    def test_validate_policy_config_success(self) -> None:
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(_VALID_POLICY, encoding="utf-8")
            cfg = load_policy_config(str(policy_path))
            validate_policy_config(cfg)

    def test_validate_policy_config_fails_for_invalid_delivery_mode(self) -> None:
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                _VALID_POLICY.replace("delivery_mode: auto", "delivery_mode: invalid"),
                encoding="utf-8",
            )
            cfg = load_policy_config(str(policy_path))
            with self.assertRaises(PolicyError):
                validate_policy_config(cfg)

    def test_validate_policy_config_fails_for_invalid_exclusion_prefix(self) -> None:
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(
                _VALID_POLICY.replace("exact:Acme Inc", "regex:Acme Inc"),
                encoding="utf-8",
            )
            cfg = load_policy_config(str(policy_path))
            with self.assertRaises(PolicyError):
                validate_policy_config(cfg)


if __name__ == "__main__":
    _ = unittest.main()
