"""复用本地 Lead/Profile，验证官方来源的审核与正文绑定。"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlsplit

from tools.infra.persistence.yaml_io import ParsedDoc, parse_simple_yaml


def same_official_source_url(left: str, right: str) -> bool:
    """跟踪参数不改变职位身份；主机、协议与职位路径必须一致。"""
    paths = []
    for value in (left, right):
        try:
            parsed = urlsplit(value)
            if (any(char.isspace() for char in value) or "\\" in value
                    or parsed.scheme != "https" or parsed.hostname != "www.liepin.com"
                    or parsed.username is not None or parsed.password is not None
                    or parsed.port not in (None, 443)
                    or not re.fullmatch(r"/(?:job|a)/[0-9]+\.shtml", parsed.path)):
                return False
            paths.append(parsed.path)
        except (TypeError, ValueError):
            return False
    return paths[0] == paths[1]


def reviewed_official_profile(lead: dict[str, str], profile_dir: Path) -> ParsedDoc | None:
    profile_id = lead.get("job_profile_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", profile_id):
        return None
    if lead.get("jd_status") != "complete_reviewed":
        return None
    try:
        doc = parse_simple_yaml((profile_dir / f"{profile_id}.yaml").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    fields = doc["scalars"]
    text = fields.get("source_jd", "").strip()
    if (not text or re.fullmatch(r"https?://\S+", text)
            or fields.get("status") != "active" or fields.get("review_decision") != "approved"
            or not fields.get("reviewed_at") or not fields.get("jd_summary")
            or not doc["lists"].get("must_have") or not doc["lists"].get("keywords")):
        return None
    digest = hashlib.sha256(text.encode()).hexdigest()
    if not (digest == fields.get("source_jd_sha256") == lead.get("source_jd_sha256")
            and hashlib.sha256(lead.get("source_jd", "").strip().encode()).hexdigest() == digest):
        return None
    if fields.get("job_lead_id") != lead.get("id") or not same_official_source_url(fields.get("source_url", ""), lead.get("url", "")):
        return None
    for key in ("platform", "platform_job_id", "platform_job_type"):
        if not lead.get(key) or fields.get(key) != lead[key]:
            return None
    return doc
