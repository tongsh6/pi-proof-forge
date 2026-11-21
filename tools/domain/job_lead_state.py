"""岗位线索的状态判定（domain 纯逻辑，不依赖 handler 与文件系统）。"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

COMPLETE_JD_STATES = frozenset({"full_unreviewed", "complete_unreviewed", "complete_reviewed", "complete"})


def lead_has_complete_jd(scalars: dict[str, str]) -> bool:
    """线索是否已有可用 JD 正文。

    判定依据是"有没有 JD 正文"，不是"是否来自官方搜索"——线索补完 JD 后
    （jd_status=complete_unreviewed）应当能生成要求项完整的画像草稿。
    """
    body = str(scalars.get("source_jd") or "").strip()
    return bool(body) and not re.fullmatch(r"https?://\S+", body) and str(
        scalars.get("jd_status") or ""
    ) in COMPLETE_JD_STATES


def canonical_liepin_detail_url(value: object) -> str | None:
    if not isinstance(value, str) or any(char.isspace() or ord(char) < 32 for char in value):
        return None
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https" or parts.hostname != "www.liepin.com"
            or parts.username is not None or parts.password is not None
            or parts.netloc.lower() not in {"www.liepin.com", "www.liepin.com:443"}
            or parts.port not in (None, 443)
            # 企业岗位在 /job/<显示ID>.shtml，猎头岗位（jobType=1）在 /a/<ID>.shtml；两者页面结构一致。
            or not re.fullmatch(r"/(?:job|a)/[0-9]+\.shtml", parts.path)
        ):
            return None
        # 跟踪 query 和 fragment 不参与岗位定位，也不向外发送。
        return "https://www.liepin.com" + parts.path
    except ValueError:
        return None


JD_CAPTURE_KEY = "jd_capture_json"
_CAPTURE_FIELDS = {"source_url", "platform_job_id", "platform_job_type", "source_jd_sha256", "fetched_at", "invalidated"}


def current_jd_capture(lead):
    """Verify the stored public-detail receipt, not current recruitment or approval."""
    if (lead.get("source") != "liepin_official" or lead.get("platform") != "liepin"
            or lead.get("jd_origin") != "public_page" or not lead_has_complete_jd(lead)):
        return None
    try:
        value = json.loads(lead.get(JD_CAPTURE_KEY) or "null")
        if (not isinstance(value, dict) or value.keys() != _CAPTURE_FIELDS
                or value["invalidated"] is not False or any(
                    not isinstance(value[key], str) or not value[key] for key in _CAPTURE_FIELDS - {"invalidated"})):
            return None
        url = canonical_liepin_detail_url(lead.get("url"))
        if (not url or value["source_url"] != url
                or not re.fullmatch(r"[0-9]+", value["platform_job_id"])
                or value["platform_job_type"] not in ("1", "2")
                or value["platform_job_type"] != lead.get("platform_job_type")
                or (value["platform_job_type"] == "1" and urlsplit(url).path != f'/a/{value["platform_job_id"]}.shtml')
                or (value["platform_job_type"] == "2" and not urlsplit(url).path.startswith("/job/"))
                or value["platform_job_id"] != lead.get("platform_job_id")
                or hashlib.sha256(lead["source_jd"].encode()).hexdigest() != value["source_jd_sha256"]
                or lead.get("source_jd_sha256") != value["source_jd_sha256"]
                or datetime.fromisoformat(value["fetched_at"]).tzinfo is None):
            return None
        return value
    except (TypeError, ValueError, KeyError, AttributeError):
        return None


def invalidate_jd_capture(raw):
    try:
        value = json.loads(raw)
        if isinstance(value, dict) and value.keys() == _CAPTURE_FIELDS and value["invalidated"] is False:
            return json.dumps({**value, "invalidated":True}, ensure_ascii=False)
    except (TypeError, ValueError):
        pass
    return raw


def retained_jd_capture(previous, current):
    """Keeping a historical body never rebinds it to a different listing path."""
    raw = previous.get(JD_CAPTURE_KEY)
    if not raw:
        return raw
    try:
        value = json.loads(raw)
        if (isinstance(value, dict) and value.keys() == _CAPTURE_FIELDS
                and value["invalidated"] is False
                and (value["source_url"] != canonical_liepin_detail_url(current.get("url"))
                     or value["platform_job_id"] != current.get("platform_job_id")
                     or value["platform_job_type"] != current.get("platform_job_type"))):
            return json.dumps({**value, "invalidated":True}, ensure_ascii=False)
    except (TypeError, ValueError):
        pass
    return raw
