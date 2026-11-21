"""投递就绪检查（只读）：一键回答「现在能不能投、卡在哪」。

检查项：
1. 职业档案确认状态（新增证据后指纹会失效，必须用户在 App 重新确认）；
2. 入池证据卡数量与合规性；
3. 可原生投递的岗位（active + 官方线索审核 + 未被历史投递占用）；
4. 猎聘凭据文件是否就位（只报存在性，不读内容）；
5. 可选：本机 LLM 是否可用。

本命令不写任何文件、不访问平台、不改档案；只输出事实与下一步建议。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.request
from pathlib import Path
from typing import cast

from tools.infra.career_profile import inspect_career
from tools.infra.persistence.yaml_io import parse_simple_yaml


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check delivery readiness (read-only)")
    _ = parser.add_argument("--root", default=".")
    _ = parser.add_argument("--check-llm", action="store_true", help="附加本机 LLM 连通性检查")
    _ = parser.add_argument("--base-url", default="http://127.0.0.1:47831/v1")
    _ = parser.add_argument("--model", default="iq3_s")
    return parser.parse_args(list(argv) if argv is not None else None)


def _pool_cards(root: Path) -> tuple[int, int]:
    pool = empty_results = 0
    for path in sorted((root / "evidence_cards").glob("ec_*.yaml")):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scalars = doc["scalars"]
        if scalars.get("status") != "saved_eligible":
            continue
        if str(scalars.get("candidate_pool_eligible") or "").lower() != "true":
            continue
        pool += 1
        if not doc["lists"].get("results"):
            empty_results += 1
    return pool, empty_results


def _delivered_profiles(root: Path) -> set[str]:
    """从历史投递日志读取已投过的岗位画像 id（job_key 是平台稳定身份，不是画像 id）。"""
    delivered: set[str] = set()
    for log in (root / "outputs/submissions").rglob("submission_log.json"):
        try:
            payload = json.loads(log.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        artifacts = payload.get("input_artifacts") if isinstance(payload, dict) else None
        if not isinstance(artifacts, dict):
            continue
        if artifacts.get("job_profile_id"):
            delivered.add(str(artifacts["job_profile_id"]))
        company = str(artifacts.get("company") or "").strip()
        position = str(artifacts.get("position") or "").strip()
        if company and position:
            delivered.add(f"{company}|{position}")
    if delivered:
        return delivered
    # 回退：至少能按 attempts 的 job_key 数量提示历史投递规模。
    database = root / "outputs/submissions/delivery_attempts.sqlite3"
    if database.is_file():
        try:
            with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
                _ = connection.execute("select count(*) from attempts").fetchone()
        except sqlite3.Error:
            pass
    return delivered


def _profile_revision_state(root: Path) -> tuple[bool, int]:
    """返回（是否已确认且未失效，待补项数量）。"""
    path = root / "personal_profile.yaml"
    if not path.is_file():
        return False, -1
    fields = parse_simple_yaml(path.read_text(encoding="utf-8"))["scalars"]
    state = inspect_career(fields, root / "evidence_cards")
    missing = len(state.get("missing") or [])
    reviewed = bool(json.loads(fields.get("career_review_json") or "{}").get("revision"))
    current = str(state.get("revision") or "")
    recorded = str(json.loads(fields.get("career_review_json") or "{}").get("revision") or "")
    return (reviewed and current == recorded and missing == 0), missing


def _deliverable_profiles(root: Path) -> list[dict]:
    delivered = _delivered_profiles(root)
    rows: list[dict] = []
    for path in sorted((root / "job_profiles").glob("jp_*.yaml")):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scalars = doc["scalars"]
        if scalars.get("status") != "active":
            continue
        if scalars.get("review_decision") != "approved":
            continue
        lead = str(scalars.get("job_lead_id") or "")
        if not lead:
            continue
        url = str(scalars.get("source_url") or "")
        # 猎聘 /a/ 是猎头岗、/job/ 是官方岗：前者通常只能投平台默认简历，
        # 后者才可能绑定定制 PDF。不区分会让"可原生投递"的结论失真。
        headhunter = "/a/" in url
        rows.append(
            {
                "id": path.stem,
                "company": str(scalars.get("company") or ""),
                "role": str(scalars.get("target_role") or ""),
                "url": url,
                "delivery_mode": "platform_default" if headhunter else "generated_pdf",
                "delivered": path.stem in delivered
                or f"{scalars.get('company') or ''}|{scalars.get('target_role') or ''}" in delivered,
            }
        )
    return [row for row in rows if not row["delivered"]]


def _llm_ready(base_url: str, model: str) -> tuple[bool, str]:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(
            {"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 8}
        ).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            _ = response.read()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - 只读诊断需要报告任意失败
        return False, f"{type(exc).__name__}: {str(exc)[:80]}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(cast(str, args.root)).resolve()
    print("[delivery-ready] 投递就绪检查（只读）")

    confirmed, missing = _profile_revision_state(root)
    print(f"- 职业档案：{'已确认且未失效' if confirmed else '未确认或已失效'}"
          + (f"（待补 {missing} 项）" if missing > 0 else ""))
    pool, empty_results = _pool_cards(root)
    print(f"- 入池证据卡：{pool} 张" + (f"，其中 {empty_results} 张缺 results（不合规）" if empty_results else ""))
    profiles = _deliverable_profiles(root)
    native = [row for row in profiles if row["delivery_mode"] == "generated_pdf"]
    platform = [row for row in profiles if row["delivery_mode"] == "platform_default"]
    print(f"- 可投岗位：{len(profiles)} 个（原生 PDF {len(native)}｜平台默认简历 {len(platform)}）")
    for row in profiles[:10]:
        label = "平台默认简历" if row["delivery_mode"] == "platform_default" else "可原生 PDF"
        print(f"    · {row['company']} / {row['role']}（{row['id']}·{label}）")
    credential = Path.home() / "Library/Application Support/PiProofForge/credentials/liepin-token"
    print(f"- 猎聘凭据文件：{'存在' if credential.is_file() else '缺失'}")
    if cast(bool, args.check_llm):
        ok, detail = _llm_ready(cast(str, args.base_url), cast(str, args.model))
        print(f"- 本机 LLM：{'可用' if ok else '不可用'}（{detail}）")

    blockers = []
    if not confirmed:
        blockers.append("在 App 简历中心确认职业档案")
    if pool == 0:
        blockers.append("让至少一张证据卡入池")
    if empty_results:
        blockers.append(f"修复 {empty_results} 张缺 results 的入池卡")
    if not profiles:
        blockers.append("在 Jobs 页新增可投岗位（官方线索 + 审核通过）")
    if blockers:
        print("[delivery-ready] 尚未就绪：")
        for item in blockers:
            print(f"  - {item}")
        return 1
    print("[delivery-ready] 已就绪：可以在 App 内准备并投递。")
    return 0
