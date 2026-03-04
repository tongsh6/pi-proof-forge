from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LiepinSubmissionConfig:
    job_url: str
    resume_path: str
    profile_path: str
    headless: bool
    dry_run: bool


def run_liepin_submission(config: LiepinSubmissionConfig) -> int:
    if config.dry_run:
        print("[DRY-RUN] Liepin submission plan")
        print(f"[DRY-RUN] job_url={config.job_url}")
        print(f"[DRY-RUN] resume={config.resume_path}")
        print(f"[DRY-RUN] profile={config.profile_path}")
        print(f"[DRY-RUN] headless={config.headless}")
        print("[DRY-RUN] step1: validate login session")
        print("[DRY-RUN] step2: open job page")
        print("[DRY-RUN] step3: upload resume")
        print("[DRY-RUN] step4: fill profile fields")
        print("[DRY-RUN] step5: submit application")
        return 0

    print("[INFO] Real Liepin submission is not enabled in this scaffold yet.")
    print("[INFO] Use --dry-run to verify parameters and execution steps.")
    return 2
