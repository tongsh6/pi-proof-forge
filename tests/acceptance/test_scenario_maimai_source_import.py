"""P0-022 脉脉来源导入（L1）：人工粘贴完整 JD + 脉脉链接 → 平台识别与人工导入标记 → 完整画像 → 手动投递记录 → 反馈关联。

规范：openspec/specs/pi-proof-forge-core.md「人工导入来源契约」。本脚本用合成 JD 验证契约；
`maimai_real_source_url_and_complete_jd_sample` 的深度验收仍需用户提供真实脉脉链接与完整 JD 在真实 Tauri 页面走通。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.acceptance.journey_contract import load_journey_contract
from tools.acceptance.journey_report import JourneyStepResult, build_journey_report, write_journey_report
from tools.sidecar.handlers.jobs import (
    handle_jobs_generate_profile_draft,
    handle_jobs_list_leads,
    handle_jobs_list_profiles,
    handle_jobs_save_profile_draft,
)
from tools.sidecar.handlers.submission import (
    handle_feedback_list,
    handle_submission_detail,
    handle_submission_list,
    handle_submission_record_manual,
    handle_submission_retry,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "acceptance" / "journey_contract.yaml"
MAIMAI_URL = "https://maimai.cn/job_detail?jid=987654321"
JD_TEXT = (
    "脉脉 · 示例科技招聘高级后端工程师（上海）。负责交易链路稳定性与容量治理，"
    "要求 5 年以上 Python 或 Java 经验，熟悉分布式系统与消息队列，有大促保障经验者优先。"
)


def _write_policy(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                'llm_provider: "lm_studio"',
                'llm_model: "local-model"',
                'llm_base_url: "http://127.0.0.1:1234/v1"',
                'llm_api_key_configured: "true"',
                'llm_api_key_placeholder: "lm-studio"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _llm_response(content: object) -> dict[str, object]:
    return {"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}


def test_maimai_manual_import_l1_acceptance_writes_report(tmp_path: Path) -> None:
    profiles_dir = tmp_path / "job_profiles"
    leads_dir = tmp_path / "job_leads"
    matching_dir = tmp_path / "matching_reports"
    submissions_dir = tmp_path / "outputs" / "submissions"
    policy_path = tmp_path / "policy.yaml"
    for directory in (profiles_dir, leads_dir, matching_dir):
        directory.mkdir()
    _write_policy(policy_path)
    parsed_payload = {
        "target_role": "高级后端工程师",
        "company": "示例科技",
        "source_url": MAIMAI_URL,
        "jd_summary": "负责交易链路稳定性与容量治理。",
        "must_have": ["Python 或 Java", "分布式系统"],
        "keywords": ["稳定性", "容量治理", "消息队列"],
        "nice_to_have": ["大促保障"],
        "business_domain": "互联网",
        "seniority_signal": ["5 年以上"],
        "tone": "technical",
    }
    review = {"decision": "approved", "reviewed_at": "2026-10-11T12:00:00Z"}

    with (
        patch("tools.sidecar.handlers.jobs._JOB_PROFILE_DIR", profiles_dir),
        patch("tools.sidecar.handlers.jobs._JOB_LEAD_DIR", leads_dir),
        patch("tools.sidecar.handlers.jobs._MATCHING_REPORT_DIR", matching_dir),
        patch("tools.sidecar.handlers.submission._SUBMISSIONS_DIR", submissions_dir),
        patch("tools.sidecar.handlers.settings._resolve_policy_path", return_value=policy_path),
        patch("tools.sidecar.handlers.jobs.LLMClient.post_json", return_value=_llm_response(parsed_payload)),
        patch(
            "tools.sidecar.handlers.jobs._check_source_url_accessible",
            side_effect=AssertionError("脉脉链接不得由 App 发起请求"),
        ) as url_check,
    ):
        # 1. 仅链接不算完整 JD
        link_only_rejected = False
        try:
            handle_jobs_save_profile_draft(
                {
                    "meta": {"correlation_id": "maimai_link_only"},
                    "draft": {**parsed_payload, "source_jd": MAIMAI_URL},
                    "review": review,
                    "save_mode": "complete",
                }
            )
        except ValueError:
            link_only_rejected = True

        # 2. 粘贴完整 JD + 脉脉链接 → 解析草稿 → 审核保存完整画像（不向脉脉发请求）
        generated = handle_jobs_generate_profile_draft(
            {"meta": {"correlation_id": "maimai_generate"}, "jd_text": JD_TEXT, "source_url": MAIMAI_URL}
        )
        complete = handle_jobs_save_profile_draft(
            {
                "meta": {"correlation_id": "maimai_complete"},
                "draft": generated["draft"],
                "review": review,
                "save_mode": "complete",
            }
        )
        profiles = handle_jobs_list_profiles(
            {
                "meta": {"correlation_id": "maimai_profiles"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"status": "active", "query": "", "tags": []},
            }
        )
        leads = handle_jobs_list_leads(
            {
                "meta": {"correlation_id": "maimai_leads"},
                "cursor": None,
                "page_size": 20,
                "sort": {"field": "updated_at", "order": "desc"},
                "filters": {"source": None, "status": None, "favorited": None, "query": ""},
            }
        )

        # 3. 用户在 App 外投递后回填手动记录，关联简历运行编号
        recorded = handle_submission_record_manual(
            {
                "meta": {"correlation_id": "maimai_manual_record"},
                "job_profile_id": complete["job_profile_id"],
                "delivered_at": "2026-10-11T15:00:00+08:00",
                "quick_run_id": "qr_maimai_demo",
                "note": "脉脉 App 内投递，附带定制 PDF",
            }
        )
        submissions = handle_submission_list({"meta": {"correlation_id": "maimai_submissions"}})
        detail = handle_submission_detail(
            {"meta": {"correlation_id": "maimai_detail"}, "submission_id": recorded["submission_id"]}
        )
        retry_rejected = False
        try:
            handle_submission_retry(
                {"meta": {"correlation_id": "maimai_retry"}, "submission_id": recorded["submission_id"], "strategy": "same_channel"}
            )
        except ValueError:
            retry_rejected = True
        feedback = handle_feedback_list(
            {"meta": {"correlation_id": "maimai_feedback"}, "source_run_id": recorded["submission_id"]}
        )

    profile_text = (profiles_dir / f"{complete['job_profile_id']}.yaml").read_text(encoding="utf-8")
    lead_text = (leads_dir / f"{complete['job_lead_id']}.yaml").read_text(encoding="utf-8")
    profile_item = profiles["items"][0]
    lead_item = leads["items"][0]
    submission_item = submissions["items"][0]

    assert link_only_rejected is True
    assert url_check.call_count == 0
    assert complete["status"] == "saved_complete" and complete["active_target_eligible"] is True
    assert complete["source_url_check"] == {
        "checked": False,
        "accessible": None,
        "status": "manual_platform_not_checked",
        "platform": "maimai",
    }
    assert 'platform: "maimai"' in profile_text and 'import_mode: "manual"' in profile_text
    assert "source_recorded_at: " in profile_text and 'source: "manual_jd"' in lead_text
    assert profile_item["platform"] == "maimai" and profile_item["import_mode"] == "manual"
    assert profile_item["source_recorded_at"]
    assert lead_item["platform"] == "maimai" and lead_item["import_mode"] == "manual"
    assert lead_item["jd_status"] == "complete_reviewed"
    assert submission_item["channel"] == "maimai" and submission_item["status"] == "manual_recorded"
    assert submission_item["retry_allowed"] is False and retry_rejected is True
    assert detail["submission"]["receipt_source"] == "manual_tracking"
    assert detail["submission"]["resume_version_id"] == "qr_maimai_demo"
    assert detail["submission"]["final_submit_attempted"] is False
    assert feedback["source_run_id"] == recorded["submission_id"]

    contract = load_journey_contract(CONTRACT_PATH)
    evidence = str(tmp_path)
    report = build_journey_report(
        contract,
        run_id="maimai_source_integration_l1",
        generated_at="2026-10-11T12:00:00Z",
        results={
            "maimai_real_source_url_and_complete_jd_sample": JourneyStepResult(
                status="pass",
                evidence=evidence,
                message="L1 合成样本：脉脉链接 + 完整 JD 保存为完整画像；真实样本的深度验收待用户提供链接与 JD。",
            ),
            "source_timestamp_and_manual_import_labeled": JourneyStepResult(
                status="pass",
                evidence=evidence,
                message="画像与线索记录 platform=maimai、import_mode=manual、source_recorded_at；列表项可读。",
            ),
            "review_matching_resume_version_and_manual_tracking": JourneyStepResult(
                status="pass",
                evidence=evidence,
                message="审核保存后画像可进入 Quick Run；手动投递记录关联简历运行编号并可作为反馈关联投递，不可重试。",
            ),
            "link_only_not_complete_jd": JourneyStepResult(
                status="pass",
                evidence=evidence,
                message="source_jd 仅为链接时完整保存被拒绝。",
            ),
            "source_coverage_separate_from_online_and_delivery_capability": JourneyStepResult(
                status="pass",
                evidence=evidence,
                message="来源链接未被请求（call_count=0），记录标明 manual_platform_not_checked 与 manual_tracking；不计自动投递。",
            ),
        },
    )
    json_path, markdown_path = write_journey_report(tmp_path, report)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["pass"] == 5
    assert "maimai_source_integration" in markdown_path.read_text(encoding="utf-8")
