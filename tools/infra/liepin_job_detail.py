"""读取猎聘公开职位正文；不使用账号凭据，不跟随跳转或绕过验证。"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


from tools.domain.job_lead_state import canonical_liepin_detail_url

_MAX_RESPONSE_BYTES = 2_000_000
_TIMEOUT_SECONDS = 20
_MESSAGES = {
    "INVALID_INPUT": "猎聘职位详情地址或岗位标识无效。",
    "NETWORK_ERROR": "暂时无法读取猎聘公开职位页，请稍后手动重试。",
    "JOB_DETAIL_UNAVAILABLE": "猎聘职位正文暂不可用，请人工补齐完整 JD 并审核。",
    "JOB_ID_MISMATCH": "猎聘详情页与所选岗位身份不一致，已停止导入。",
    "INVALID_RESPONSE": "猎聘详情页不符合已核实的正文结构，已停止导入。",
    "SECURITY_CHALLENGE": "猎聘要求安全验证或限制访问，已停止自动读取。",
}
DETAIL_UNAVAILABLE_REASONS = frozenset({
    "source_reports_unavailable", "source_page_not_found", "access_required", "no_verified_detail",
})
_BLOCK_TAGS = {"br", "p", "div", "li", "ul", "ol", "section", "dd", "h1", "h2", "h3"}


class LiepinJobDetailError(Exception):
    """只暴露固定错误码和安全文案，不携带 URL、响应或底层异常。"""

    def __init__(self, code: str, *, detail_reason: str | None = None) -> None:
        self.code = code
        self.detail_reason = (detail_reason if code == "JOB_DETAIL_UNAVAILABLE"
                              and detail_reason in DETAIL_UNAVAILABLE_REASONS else None)
        self.message = _MESSAGES[code]
        super().__init__(self.message)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    return "\n".join(line.strip() for line in value.splitlines() if line.strip())


class _BodyParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden = True
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = False
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def _description_text(value: str) -> str:
    if re.search(r"</?(?:p|br|div|li|ul|ol|section|span|strong|em|b|i)\b", value, re.I):
        parser = _BodyParser()
        parser.feed(value)
        return _normalize_text("".join(parser.parts))
    return _normalize_text(html.unescape(value))


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ld_scripts: list[str] = []
        self.dom_bodies: list[str] = []
        self.title: list[str] = []
        self.visible: list[str] = []
        self._script: list[str] | None = None
        self._dom: list[str] | None = None
        self._hidden = False
        self._in_title = False
        self._notice_block: tuple[str, list[str]] | None = None
        self.ambiguous_notice = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style"}:
            self._hidden = True
            if tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
                self._script = []
        if tag == "title":
            self._in_title = True
        if tag == "dd" and attributes.get("data-selector") == "job-intro-content":
            self._dom = []
        if self._dom is not None and tag in _BLOCK_TAGS:
            self._dom.append("\n")
        if not self._hidden and self._dom is None and tag in {"p", "div"}:
            # Exact standalone generic block only; no site-specific selector or status claim.
            self._notice_block = (tag, [])

    def handle_endtag(self, tag):
        if self._notice_block is not None and tag == self._notice_block[0]:
            if _PAGE_UNAVAILABLE_NOTICE.fullmatch("".join(self._notice_block[1]).strip()):
                self.ambiguous_notice = True
            self._notice_block = None
        if tag == "script" and self._script is not None:
            self.ld_scripts.append("".join(self._script))
            self._script = None
        if tag in {"script", "style"}:
            self._hidden = False
        if tag == "title":
            self._in_title = False
        if self._dom is not None and tag in _BLOCK_TAGS:
            self._dom.append("\n")
        if tag == "dd" and self._dom is not None:
            self.dom_bodies.append(_normalize_text("".join(self._dom)))
            self._dom = None

    def handle_data(self, data):
        if self._script is not None:
            self._script.append(data)
        elif not self._hidden:
            if self._in_title:
                self.title.append(data)
                return
            if self._dom is not None:
                self._dom.append(data)
            else:
                self.visible.append(data)
                if self._notice_block is not None:
                    self._notice_block[1].append(data)


def _postings(scripts: list[str]) -> list[dict]:
    postings, malformed = [], False
    for script in scripts:
        try:
            pending = [json.loads(script)]
        except (ValueError, RecursionError):
            malformed = True
            continue
        while pending:
            node = pending.pop()
            if isinstance(node, list):
                pending.extend(node)
            elif isinstance(node, dict):
                if node.get("@type") == "JobPosting":
                    postings.append(node)
                elif "@graph" in node:
                    pending.append(node["@graph"])
    if malformed and not postings:
        raise LiepinJobDetailError("INVALID_RESPONSE")
    return postings


def _posting_raw_id(posting: dict) -> str | None:
    identifier = posting.get("identifier")
    if not isinstance(identifier, dict) or "value" not in identifier:
        return None
    raw_id = identifier["value"]
    if type(raw_id) not in (str, int) or not re.fullmatch(r"[0-9]+", str(raw_id)):
        raise LiepinJobDetailError("INVALID_RESPONSE")
    return str(raw_id)


def _requested_posting(postings: list[dict], url: str, expected_id: str) -> dict:
    # A URL-less single posting keeps the previously supported exact raw-ID check.
    if len(postings) == 1 and "url" not in postings[0]:
        selected = postings[0]
    else:
        on_page = [item for item in postings if canonical_liepin_detail_url(item.get("url")) == url]
        # Only an item explicitly pointing at the requested page competes for its body.
        if len(on_page) > 1:
            raise LiepinJobDetailError("INVALID_RESPONSE")
        if not on_page:
            for item in postings:
                try:
                    raw_id = _posting_raw_id(item)
                except LiepinJobDetailError:
                    continue  # Unrelated unreadable metadata is not a root contradiction.
                if raw_id == expected_id and "url" in item:
                    raise LiepinJobDetailError("JOB_ID_MISMATCH")
            raise LiepinJobDetailError("JOB_DETAIL_UNAVAILABLE", detail_reason="no_verified_detail")
        selected = on_page[0]
        endpoint = urlsplit(url).path.split("/")[1]
        for item in postings:
            other_url = canonical_liepin_detail_url(item.get("url"))
            if other_url and other_url != url and urlsplit(other_url).path.split("/")[1] == endpoint:
                try:
                    other_id = _posting_raw_id(item)
                except LiepinJobDetailError:
                    continue
                if other_id == expected_id:
                    raise LiepinJobDetailError("INVALID_RESPONSE")
    raw_id = _posting_raw_id(selected)
    if raw_id is None:
        raise LiepinJobDetailError("JOB_DETAIL_UNAVAILABLE", detail_reason="no_verified_detail")
    if raw_id != expected_id:
        raise LiepinJobDetailError("JOB_ID_MISMATCH")
    return selected


_PAGE_UNAVAILABLE_NOTICE = re.compile(
    r"(?:该)?职位已(?:经)?(?:下线|下架|关闭|过期|停止招聘)|职位不存在|页面不存在"
)


_SUBSTANTIVE_BODY_CHARS = 200


def _complete_body(text: str) -> bool:
    if any(word in text for word in ("登录后查看", "展开全文", "展开全部", "查看完整职位描述", "查看更多")):
        return False
    # 2026-10-12 修订：真实 JD 常用“工作内容 / 我们期待你 / Job Responsibilities”等自定标题，
    # 无截断提示且压缩后正文足量即视为完整；短正文仍须同时具备职责与要求两类实质章节。
    if len(re.sub(r"\s", "", text)) >= _SUBSTANTIVE_BODY_CHARS:
        return True
    headings = list(re.finditer(r"(?m)^(?:(?P<duties>(?:岗位|工作|职位)?职责|职位描述(?=[：:\s]|$))|(?:任职|职位|岗位|工作)要求)[：:]?", text))
    kinds = {"职责" if match.group("duties") else "要求" for match in headings}
    if kinds != {"职责", "要求"} or len(re.sub(r"\s", "", text)) < 80:
        return False
    # 两类章节各需实质正文；只出现标题或岗位标签不能升级为完整 JD。
    return all(
        len(re.sub(r"\s", "", text[match.end():headings[index + 1].start() if index + 1 < len(headings) else len(text)])) >= 20
        for index, match in enumerate(headings)
    )


def _fetch_html(source_url: str) -> str:
    request = Request(source_url, headers={"Accept": "text/html"}, method="GET")
    failure, reason, content, charset = None, None, b"", "utf-8"
    try:
        with build_opener(_NoRedirect()).open(request, timeout=_TIMEOUT_SECONDS) as response:
            if response.geturl() != source_url:
                failure = "JOB_DETAIL_UNAVAILABLE"
            elif response.status != 200 or response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                failure = "INVALID_RESPONSE"
            else:
                charset = response.headers.get_content_charset() or "utf-8"
                content = response.read(_MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # 猎聘对 IP/UA 频次触发时 302 到 safe.liepin.com 的人机验证分发页；如实报告验证挑战，不跟随、不绕过。
        location = str(exc.headers.get("Location") or "") if exc.headers is not None else ""
        if 300 <= exc.code < 400 and (urlsplit(location).hostname == "safe.liepin.com" or "captcha" in location.lower()):
            failure = "SECURITY_CHALLENGE"
        else:
            failure = "SECURITY_CHALLENGE" if exc.code in (403, 429) else "NETWORK_ERROR" if exc.code >= 500 else "JOB_DETAIL_UNAVAILABLE"
        if exc.code in (404, 410):
            reason = "source_page_not_found"
        elif exc.code == 401:
            reason = "access_required"
        exc.close()
    except (URLError, TimeoutError, OSError, HTTPException):
        failure = "NETWORK_ERROR"
    # 离开 except 后创建异常，避免泄露带 URL/正文的底层异常链。
    if failure:
        raise LiepinJobDetailError(failure, detail_reason=reason)
    if len(content) > _MAX_RESPONSE_BYTES:
        raise LiepinJobDetailError("INVALID_RESPONSE")
    decoded = None
    try:
        decoded = content.decode(charset)
    except (UnicodeError, LookupError):
        pass
    if decoded is None:
        raise LiepinJobDetailError("INVALID_RESPONSE")
    return decoded


def fetch_liepin_job_detail(url: str, expected_job_id: str) -> dict:
    """仅返回身份核实且具备职责/要求正文的公开 JD，失败时保持阻断。"""
    source_url = canonical_liepin_detail_url(url)
    if source_url is None or not isinstance(expected_job_id, str) or not re.fullmatch(r"[0-9]+", expected_job_id):
        raise LiepinJobDetailError("INVALID_INPUT")
    parser = _PageParser()
    parser.feed(_fetch_html(source_url))
    title, visible = "".join(parser.title).strip(), " ".join(parser.visible).strip()
    page_text = f"{title} {visible}"
    if re.search(r"安全验证|人机验证|滑动验证|请完成.{0,8}验证|请输入验证码|访问过于频繁|访问行为异常|captcha", page_text, re.I):
        raise LiepinJobDetailError("SECURITY_CHALLENGE")
    if "登录" in title or re.search(r"登录后(?:查看|继续)", visible):
        raise LiepinJobDetailError("JOB_DETAIL_UNAVAILABLE", detail_reason="access_required")
    # Whole-page notices keep their existing diagnosis. A phrase embedded in
    # another card, JD prose, or adjacent content cannot determine the root status.
    if _PAGE_UNAVAILABLE_NOTICE.fullmatch(title):
        raise LiepinJobDetailError("JOB_DETAIL_UNAVAILABLE", detail_reason="source_reports_unavailable")
    postings = _postings(parser.ld_scripts)
    posting = _requested_posting(postings, source_url, expected_job_id)
    if len(postings) == 1 and not parser.dom_bodies and _PAGE_UNAVAILABLE_NOTICE.fullmatch(visible):
        raise LiepinJobDetailError("JOB_DETAIL_UNAVAILABLE", detail_reason="source_reports_unavailable")
    if parser.ambiguous_notice:
        raise LiepinJobDetailError("JOB_DETAIL_UNAVAILABLE", detail_reason="no_verified_detail")
    if len(postings) == 1 and len(parser.dom_bodies) > 1:
        raise LiepinJobDetailError("INVALID_RESPONSE")
    description = posting.get("description")
    if description is not None and not isinstance(description, str):
        raise LiepinJobDetailError("INVALID_RESPONSE")
    structured_body = _description_text(description) if description else ""
    # On multi-role pages the legacy DOM selector does not bind a body to one role.
    dom_body = parser.dom_bodies[0] if len(postings) == 1 and parser.dom_bodies else ""
    if structured_body and dom_body and re.sub(r"\s", "", structured_body) != re.sub(r"\s", "", dom_body):
        raise LiepinJobDetailError("INVALID_RESPONSE")
    body = dom_body or structured_body
    if not _complete_body(body):
        raise LiepinJobDetailError("JOB_DETAIL_UNAVAILABLE", detail_reason="no_verified_detail")
    return {
        "jd_text": body,
        "source_url": source_url,
        "platform_job_id": expected_job_id,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_jd_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
