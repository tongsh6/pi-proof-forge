import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.sidecar.handlers.profile import handle_profile_get, handle_profile_update


class ProfileGetTests(unittest.TestCase):
    def test_get_returns_empty_profile_on_first_use(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            profile_path = Path(tmp_dir) / "personal_profile.yaml"
            with patch("tools.sidecar.handlers.profile._PROFILE_PATH", profile_path):
                result = handle_profile_get({"meta": {"correlation_id": "corr_001"}})

        profile = result["profile"]
        self.assertEqual(result["meta"]["correlation_id"], "corr_001")
        self.assertEqual(profile["completeness"], 0)
        self.assertEqual(
            profile["missing_fields"],
            ["name", "phone", "email", "city", "current_position"],
        )
        self.assertEqual(profile["current_position"], "")

    def test_get_returns_profile_with_completeness(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            profile_path = Path(tmp_dir) / "personal_profile.yaml"
            profile_path.write_text(
                "\n".join(
                    [
                        'name: "Zhang San"',
                        'phone: "+86 138 0000 0000"',
                        'email: "zhangsan@example.com"',
                        'city: "Beijing"',
                        'current_position: "Senior Backend Engineer"',
                        'updated_at: "2026-03-07T09:00:00Z"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with patch("tools.sidecar.handlers.profile._PROFILE_PATH", profile_path):
                result = handle_profile_get({"meta": {"correlation_id": "corr_002"}})

        profile = result["profile"]
        self.assertEqual(profile["name"], "Zhang San")
        self.assertEqual(profile["completeness"], 100)
        self.assertEqual(profile["missing_fields"], [])
        self.assertEqual(profile["updated_at"], "2026-03-07T09:00:00Z")


class ProfileUpdateTests(unittest.TestCase):
    def test_update_persists_partial_patch(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            profile_path = Path(tmp_dir) / "personal_profile.yaml"
            profile_path.write_text(
                'name: "Old Name"\nemail: "old@example.com"\n',
                encoding="utf-8",
            )
            with patch("tools.sidecar.handlers.profile._PROFILE_PATH", profile_path):
                result = handle_profile_update(
                    {
                        "meta": {"correlation_id": "corr_003"},
                        "patch": {"city": "Shanghai", "current_position": "Tech Lead"},
                    }
                )
                stored = handle_profile_get({"meta": {"correlation_id": "corr_004"}})

        self.assertTrue(result["saved"])
        self.assertTrue(result["updated_at"].endswith("Z"))
        profile = stored["profile"]
        self.assertEqual(profile["name"], "Old Name")
        self.assertEqual(profile["email"], "old@example.com")
        self.assertEqual(profile["city"], "Shanghai")
        self.assertEqual(profile["current_position"], "Tech Lead")

    def test_update_rejects_invalid_email(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            profile_path = Path(tmp_dir) / "personal_profile.yaml"
            with patch("tools.sidecar.handlers.profile._PROFILE_PATH", profile_path):
                with self.assertRaises(ValueError):
                    handle_profile_update(
                        {
                            "meta": {"correlation_id": "corr_005"},
                            "patch": {"email": "not-an-email"},
                        }
                    )


if __name__ == "__main__":
    unittest.main()
