import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.submission.storage import SubmissionRecorder


class SubmissionStorageTests(unittest.TestCase):
    def test_recorder_persists_browser_channel_to_logs(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = SubmissionRecorder(Path(tmp), platform="liepin", mode="check")
            recorder.set_meta(
                job_url="https://www.liepin.com/job/123.shtml",
                resume_path="outputs/v1.md",
                profile_path="profiles/candidate_profile.yaml",
                headless=False,
                browser_channel="chrome",
            )

            recorder.finish("success")

            payload = json.loads(recorder.log_json.read_text(encoding="utf-8"))
            yaml_text = recorder.log_yaml.read_text(encoding="utf-8")

        self.assertEqual(payload["browser_channel"], "chrome")
        self.assertIn('browser_channel: "chrome"', yaml_text)


if __name__ == "__main__":
    unittest.main()
