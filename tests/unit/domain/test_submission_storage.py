import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.submission.storage import SubmissionRecorder


class SubmissionStorageTests(unittest.TestCase):
    def test_recorder_persists_browser_channel_to_logs(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume = root / "resume.pdf"
            profile = root / "profile.yaml"
            resume.write_bytes(b"%PDF-1.4\n")
            profile.write_text("id: profile\n", encoding="utf-8")
            recorder = SubmissionRecorder(Path(tmp), platform="liepin", mode="check")
            recorder.set_meta(
                job_url="https://www.liepin.com/job/123.shtml",
                resume_path=str(resume),
                profile_path=str(profile),
                headless=False,
                browser_channel="chrome",
                external_l3_validation_run_id="acceptance_external_l3",
                external_l3_validation_path=(
                    "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
                ),
            )

            recorder.finish("success")

            payload = json.loads(recorder.log_json.read_text(encoding="utf-8"))
            yaml_text = recorder.log_yaml.read_text(encoding="utf-8")

        self.assertEqual(payload["browser_channel"], "chrome")
        self.assertEqual(
            payload["external_l3_validation_run_id"],
            "acceptance_external_l3",
        )
        self.assertEqual(
            payload["external_l3_validation_path"],
            "outputs/acceptance/acceptance_external_l3/external-l3-validation.json",
        )
        input_artifacts = payload["input_artifacts"]
        self.assertEqual(input_artifacts["job_url"]["scheme"], "https")
        self.assertEqual(input_artifacts["job_url"]["hostname"], "www.liepin.com")
        files = {item["id"]: item for item in input_artifacts["files"]}
        self.assertEqual(
            files["resume_pdf"]["sha256"],
            hashlib.sha256(b"%PDF-1.4\n").hexdigest(),
        )
        self.assertEqual(
            files["profile_yaml"]["sha256"],
            hashlib.sha256(b"id: profile\n").hexdigest(),
        )
        self.assertFalse(files["resume_pdf"]["raw_content_persisted"])
        self.assertIn('browser_channel: "chrome"', yaml_text)
        self.assertIn("input_artifacts:", yaml_text)
        self.assertIn('sha256: "', yaml_text)
        self.assertIn(
            'external_l3_validation_run_id: "acceptance_external_l3"',
            yaml_text,
        )
        self.assertIn(
            'external_l3_validation_path: "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"',
            yaml_text,
        )


if __name__ == "__main__":
    unittest.main()
