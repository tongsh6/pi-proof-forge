# tools/test_liepin_direct.py
import sys
from pathlib import Path
from tools.submission.liepin import run_liepin_submission, LiepinSubmissionConfig

def main():
    config = LiepinSubmissionConfig(
        job_url="https://www.liepin.com/job/1982028827.shtml",
        resume_path="outputs/resume_mr-2026-001_A.md", # 确保存在该文件或任意 md
        profile_path="profiles/candidate_profile.yaml",
        headless=False,  # 允许我们观察
        dry_run=False,
        submit=False,    # 仅 check-mode
        output_dir="outputs/submissions/direct_test",
        session_dir="outputs/submissions",
        timeout_ms=30000,
        browser_channel="chrome"
    )
    
    # 检查简历文件是否存在，不存在则创建一个空的
    resume_file = Path(config.resume_path)
    if not resume_file.exists():
        resume_file.parent.mkdir(parents=True, exist_ok=True)
        resume_file.write_text("# Test Resume\n- Skill 1\n- Skill 2")

    print(f"[*] 启动直接投递测试 (check-mode)")
    print(f"[*] URL: {config.job_url}")
    
    exit_code = run_liepin_submission(config)
    print(f"[*] 测试结束，退出码: {exit_code}")

if __name__ == "__main__":
    main()
