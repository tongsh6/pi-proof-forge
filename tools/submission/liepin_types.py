"""猎聘投递的类型与选择器常量（供主流程与页内交互子模块共用）。"""
from __future__ import annotations

from dataclasses import dataclass


UPLOAD_PANEL_TRIGGERS = [
    "button:has-text('上传简历')",
    "a:has-text('上传简历')",
    "button:has-text('上传附件')",
    "a:has-text('上传附件')",
    "button:has-text('更新简历')",
    "a:has-text('更新简历')",
    "button:has-text('重新上传')",
    "a:has-text('重新上传')",
]

APPLY_DIALOG_TRIGGERS = [
    "button:has-text('投递简历')",
    "a:has-text('投递简历')",
    "button:has-text('立即沟通')",
    "a:has-text('立即沟通')",
    "button:has-text('聊一聊')",
    "a:has-text('聊一聊')",
    "button:has-text('立即申请')",
    "a:has-text('立即申请')",
    "button:has-text('申请职位')",
    "a:has-text('申请职位')",
]

MAIN_CHAT_SELECTOR = (
    "a[data-tlg-elem-id='c_pc_job_detail_chat_btn'],"
    "a[data-tlg-elem-id='c_pc_job_detail_recruiter_chat_btn']"
)
RECOMMENDED_CHAT_SELECTOR = "a[data-tlg-elem-id='c_pc_job_detail_like_chat_btn']"


@dataclass(frozen=True)
class TargetVerification:
    ok: bool
    reason: str = ""
    url_job_id: str = ""
    dom_jobid: str = ""
    params_jobid: str = ""
    recruiter_name: str = ""
    recruiter_id: str = ""
    matched_count: int = 0


@dataclass
class LiepinSubmissionConfig:
    job_url: str
    resume_path: str
    profile_path: str
    headless: bool
    dry_run: bool
    submit: bool
    output_dir: str
    session_dir: str
    timeout_ms: int
    browser_channel: str = "chrome"
    rate_limit_max_per_batch: int = 5
    rate_limit_cooldown_seconds: int = 900
    rate_limit_daily_limit: int = 30
    confirm_submit_job_id: str = ""
    confirm_submit_recruiter: str = ""
    external_l3_validation_run_id: str = ""
    external_l3_validation_path: str = ""
    session_profile_path: str = ""
