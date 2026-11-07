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
        self.assertEqual(payload["job_url"], "<redacted>")
        self.assertEqual(payload["resume_path"], "<redacted>")
        self.assertEqual(payload["profile_path"], "<redacted>")
        self.assertTrue(payload["live_inputs_redacted"])
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
        self.assertEqual(files["resume_pdf"]["basename"], "<redacted>")
        self.assertFalse(files["resume_pdf"]["basename_persisted"])
        self.assertEqual(
            files["resume_pdf"]["sha256"],
            hashlib.sha256(b"%PDF-1.4\n").hexdigest(),
        )
        self.assertEqual(files["profile_yaml"]["basename"], "<redacted>")
        self.assertFalse(files["profile_yaml"]["basename_persisted"])
        self.assertEqual(
            files["profile_yaml"]["sha256"],
            hashlib.sha256(b"id: profile\n").hexdigest(),
        )
        self.assertFalse(files["resume_pdf"]["raw_content_persisted"])
        self.assertIn('browser_channel: "chrome"', yaml_text)
        self.assertIn('job_url: "<redacted>"', yaml_text)
        self.assertIn('resume_path: "<redacted>"', yaml_text)
        self.assertIn('profile_path: "<redacted>"', yaml_text)
        self.assertIn("live_inputs_redacted: true", yaml_text)
        self.assertIn("input_artifacts:", yaml_text)
        self.assertIn('basename: "<redacted>"', yaml_text)
        self.assertIn("basename_persisted: false", yaml_text)
        self.assertNotIn("resume.pdf", yaml_text)
        self.assertNotIn("profile.yaml", yaml_text)
        self.assertIn('sha256: "', yaml_text)
        self.assertIn(
            'external_l3_validation_run_id: "acceptance_external_l3"',
            yaml_text,
        )
        self.assertIn(
            'external_l3_validation_path: "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"',
            yaml_text,
        )

    def test_recorder_keeps_raw_inputs_for_non_external_l3_logs(self) -> None:
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
            )

            recorder.finish("success")

            payload = json.loads(recorder.log_json.read_text(encoding="utf-8"))
            yaml_text = recorder.log_yaml.read_text(encoding="utf-8")

        self.assertEqual(payload["job_url"], "https://www.liepin.com/job/123.shtml")
        self.assertEqual(payload["resume_path"], str(resume))
        self.assertEqual(payload["profile_path"], str(profile))
        self.assertFalse(payload["live_inputs_redacted"])
        input_artifacts = payload["input_artifacts"]
        files = {item["id"]: item for item in input_artifacts["files"]}
        self.assertEqual(files["resume_pdf"]["basename"], "resume.pdf")
        self.assertTrue(files["resume_pdf"]["basename_persisted"])
        self.assertEqual(files["profile_yaml"]["basename"], "profile.yaml")
        self.assertTrue(files["profile_yaml"]["basename_persisted"])
        self.assertIn('job_url: "https://www.liepin.com/job/123.shtml"', yaml_text)
        self.assertIn('basename: "resume.pdf"', yaml_text)
        self.assertIn("basename_persisted: true", yaml_text)
        self.assertIn("live_inputs_redacted: false", yaml_text)

    def test_recorder_redacts_external_l3_step_details_and_errors(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume = root / "resume.pdf"
            profile = root / "profile.yaml"
            resume.write_bytes(b"%PDF-1.4\n")
            profile.write_text("id: profile\n", encoding="utf-8")
            recorder = SubmissionRecorder(Path(tmp), platform="liepin", mode="submit")
            recorder.set_meta(
                job_url="https://www.liepin.com/job/123.shtml",
                resume_path=str(resume),
                profile_path=str(profile),
                headless=True,
                external_l3_validation_run_id="acceptance_external_l3",
                external_l3_validation_path=(
                    "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
                ),
                redaction_values=["123", "Verifier"],
            )

            recorder.add_step(
                "target_verify",
                "success",
                (
                    "url=https://www.liepin.com/job/123.shtml; "
                    f"resume={resume}; profile={profile}; "
                    "job_id=123; recruiter=Verifier"
                ),
            )
            recorder.finish("failed", error="job_id=123 recruiter=Verifier")

            payload = json.loads(recorder.log_json.read_text(encoding="utf-8"))
            yaml_text = recorder.log_yaml.read_text(encoding="utf-8")

        detail = payload["steps"][0]["detail"]
        self.assertEqual(payload["error"], "job_id=<redacted> recruiter=<redacted>")
        self.assertNotIn("https://www.liepin.com/job/123.shtml", detail)
        self.assertNotIn(str(resume), detail)
        self.assertNotIn(str(profile), detail)
        self.assertNotIn("123", detail)
        self.assertNotIn("Verifier", detail)
        self.assertIn("<redacted>", detail)
        self.assertNotIn("Verifier", yaml_text)

    def test_recorder_omits_external_l3_screenshot_references(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            resume = root / "resume.pdf"
            profile = root / "profile.yaml"
            resume.write_bytes(b"%PDF-1.4\n")
            profile.write_text("id: profile\n", encoding="utf-8")
            recorder = SubmissionRecorder(Path(tmp), platform="liepin", mode="submit")
            recorder.set_meta(
                job_url="https://www.liepin.com/job/123.shtml",
                resume_path=str(resume),
                profile_path=str(profile),
                headless=True,
                external_l3_validation_run_id="acceptance_external_l3",
                external_l3_validation_path=(
                    "outputs/acceptance/acceptance_external_l3/external-l3-validation.json"
                ),
            )
            screenshot = recorder.screenshot_path("target_verify")
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(b"raw png")

            recorder.add_step(
                "target_verify",
                "failed",
                "raw_browser_artifacts_persisted=false",
                screenshot=screenshot,
            )
            recorder.finish("failed", error="target_verify_failed")

            payload = json.loads(recorder.log_json.read_text(encoding="utf-8"))
            yaml_text = recorder.log_yaml.read_text(encoding="utf-8")

        self.assertTrue(payload["live_inputs_redacted"])
        self.assertEqual(payload["steps"][0]["screenshot"], "")
        self.assertIn('screenshot: ""', yaml_text)
        self.assertNotIn("screenshots/", yaml_text)


if __name__ == "__main__":
    unittest.main()


def test_external_observation_does_not_pass_app_submission_evidence():
    from tools.submission.storage import submission_required_steps_evidence
    required = ['idempotency','credential_check','target_check','resume_observed','authorization','api_submit','receipt']
    log = {'platform':'liepin', 'mode':'submit', 'transport':'liepin_api','status':'success',
           'input_artifacts':{'receipt_source':'website_history'},
           'steps':[{'name':name,'status':'success','detail':''} for name in required]}
    proof = submission_required_steps_evidence(log)
    assert proof['passed'] is False
    assert proof['not_required_reason'] == 'external_observation_not_app_verified'
