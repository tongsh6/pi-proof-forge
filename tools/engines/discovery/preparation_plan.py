"""只读每日准备选择器；输出待新语义验证的工作，不输出投递授权。

调用方提供当前画像列表及所有历史/未决尝试身份。此层不读取文件、不调用
模型、不更新队列；已有评分只用于准备顺序，不证明岗位仍在线或简历可发送。
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from tools.engines.matching.fit_precheck import RANK_BY_STATE

_PREPARABLE_STATES = frozenset({"recommended", "consider", "promising"})


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""




def build_preparation_plan(
    profiles: Iterable[Mapping[str, Any]],
    maximum: int = 3,
    attempted_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """稳定选出最多 1–3 个准备候选，保留未入选理由且不修改输入。

    attempted_keys 包含 success/failed/unknown/in_flight 的所有占位；
    profile.preparation_key 必须与这些占位共用原执行器的身份口径。
    是否解除占位属于原投递执行器，本选择器不能根据失败状态自行重试。
    """
    if type(maximum) is not int or not 1 <= maximum <= 3:
        raise ValueError("invalid_preparation_maximum")
    attempted = set(attempted_keys)
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []

    def fit_state(profile: Mapping[str, Any]) -> str:
        precheck = profile.get("fit_precheck")
        return _text(precheck.get("state")) if isinstance(precheck, Mapping) else ""

    # 同分保持输入顺序，不依赖不可信的传入 rank/score，避免排序抖动。
    ordered = sorted(profiles, key=lambda p: RANK_BY_STATE.get(fit_state(p), 99))
    for profile in ordered:
        native = profile.get("native_pdf_delivery")
        native = native if isinstance(native, Mapping) else {}
        channel = ("generated_pdf" if native.get("supported") is True else
                   "platform_default" if native.get("reason") == "platform_default_only" else "")
        row = {key: _text(profile.get(key)) for key in
               ("job_profile_id", "company", "title", "source_url")}
        row["channel"] = channel
        preparation = profile.get("preparation")
        if isinstance(preparation, Mapping):
            row["preparation"] = dict(preparation)
        # 身份由 adapter 复用执行器 _job_key 提供，不能重建另一套 hash/URL 口径。
        identity = _text(profile.get("preparation_key"))
        if profile.get("status") != "active":
            reason = "profile_review_required"
            if isinstance(preparation, Mapping):
                if preparation.get("state") == "fresh":
                    reason = ("preparation_direction_deferred" if preparation.get("reason") == "preparation_direction_deferred"
                              else "preparation_saved_unapproved")
                elif preparation.get("state") in {"stale", "invalid"}:
                    reason = "preparation_" + str(preparation["state"])
        elif not _text(profile.get("source_jd")):
            reason = "jd_missing"
        elif not channel:
            reason = _text(native.get("reason")) or "channel_unavailable"
        elif not identity:
            reason = "job_identity_missing"
        elif identity in attempted:
            reason = "already_attempted"
        elif fit_state(profile) not in _PREPARABLE_STATES:
            reason = "fit_not_promising"
        elif identity in seen:
            reason = "duplicate_job"
        else:
            seen.add(identity)
            reason = "semantic_review_required" if len(selected) < maximum else "preparation_limit"
        row["reason"] = reason
        (selected if reason == "semantic_review_required" else deferred).append(row)

    return {"maximum": maximum, "selected": selected, "deferred": deferred,
            "shortfall": maximum - len(selected), "send_ready": False}
