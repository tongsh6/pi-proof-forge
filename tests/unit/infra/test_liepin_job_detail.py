"""公开 JD 解析契约；手写脱敏页面，仅替换最底层 HTTPS 传输。"""

from __future__ import annotations

import hashlib
import io
import json
import traceback
from datetime import datetime
from email.message import Message
from http.client import HTTPException
from urllib.error import URLError
from urllib.request import HTTPSHandler
from urllib.response import addinfourl

import pytest

from tools.infra import liepin_job_detail as detail


URL = "https://www.liepin.com/job/1900042.shtml"
RAW_ID = "42"
SENSITIVE = "private-response-do-not-log"
JD = (
    "岗位职责：\n"
    "1. 负责 Java & Python 服务的接口设计、功能开发与日常维护。\n"
    "2. 配合团队完成代码审查、测试验证和线上问题分析。\n"
    "职位要求：\n"
    "1. 熟悉服务端开发、关系数据库与常用网络协议。\n"
    "2. 能够独立分析业务需求，具备良好的协作与沟通能力。"
)


def page(*, description=JD, dom=None, identifier=RAW_ID, canonical=URL, extra="", title="测试岗位"):
    posting = {"@type": "JobPosting", "description": description, "url": canonical}
    if identifier is not None:
        posting["identifier"] = {"@type": "PropertyValue", "value": identifier}
    markup = "" if dom is None else f'<dd data-selector="job-intro-content">{dom}</dd>'
    return (
        f"<html><head><title>{title}</title>"
        '<script type="application/ld+json">'
        + json.dumps({"description": "不能当作完整 JD 的 SEO 摘要"}, ensure_ascii=False)
        + '</script><script type="application/ld+json">'
        + json.dumps(posting, ensure_ascii=False)
        + f"</script></head><body>{markup}{extra}</body></html>"
    ).encode()


@pytest.fixture
def transport(monkeypatch):
    requests, responses = [], []

    def respond(body=None, *, status=200, headers=None, error=None, response_url=None):
        responses.append((page() if body is None else body, status, headers or {}, error, response_url))

    def https_open(handler, request):
        requests.append(request)
        body, status, headers, error, response_url = responses.pop(0)
        if error:
            raise error
        message = Message()
        message["Content-Type"] = headers.get("Content-Type", "text/html;charset=UTF-8")
        for key, value in headers.items():
            if key != "Content-Type":
                message[key] = value
        response = addinfourl(io.BytesIO(body), message, response_url or request.full_url, status)
        response.msg = SENSITIVE
        return response

    monkeypatch.setattr(HTTPSHandler, "https_open", https_open)
    return respond, requests


def assert_error(call, code):
    with pytest.raises(detail.LiepinJobDetailError) as caught:
        call()
    error = caught.value
    assert error.code == code
    assert error.message == str(error)
    assert error.__context__ is None
    rendered = "".join(traceback.format_exception(error))
    assert SENSITIVE not in rendered
    assert SENSITIVE not in repr(vars(error))
    assert URL not in str(error)


def test_reads_only_matching_jobposting_preserving_text_and_provenance(transport):
    respond, requests = transport
    respond(page(dom=JD.replace("&", "&amp;").replace("\n", "<br>")))

    result = detail.fetch_liepin_job_detail(URL + "?mscid=public-source#detail", RAW_ID)

    assert result == {
        "jd_text": JD,
        "source_url": URL,
        "platform_job_id": RAW_ID,
        "fetched_at": result["fetched_at"],
        "source_jd_sha256": hashlib.sha256(JD.encode()).hexdigest(),
    }
    assert datetime.fromisoformat(result["fetched_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    assert len(requests) == 1
    req = requests[0]
    assert req.full_url == URL
    assert req.get_method() == "GET" and req.data is None
    assert 0 < req.timeout <= 20
    assert {name.lower() for name in dict(req.header_items())}.isdisjoint({"cookie", "authorization", "x-user-token"})


def test_jsonld_html_description_and_dom_have_same_plain_text(transport):
    respond, _ = transport
    markup = "".join(f"<p>{line.replace('&', '&amp;')}</p>" for line in JD.splitlines())
    respond(page(description=markup, dom=markup, identifier=42))
    assert detail.fetch_liepin_job_detail(URL, RAW_ID)["jd_text"] == JD


def test_dom_can_supply_body_when_identified_posting_has_no_description(transport):
    respond, _ = transport
    respond(page(description=None, dom=JD))
    assert detail.fetch_liepin_job_detail(URL, RAW_ID)["jd_text"] == JD


@pytest.mark.parametrize("url", [
    "http://www.liepin.com/job/1900042.shtml", "https://liepin.com/job/1900042.shtml",
    "https://www.liepin.com.evil.test/job/1900042.shtml", "https://user@www.liepin.com/job/1900042.shtml",
    "https://www.liepin.com:444/job/1900042.shtml", "https://www.liepin.com:bad/job/1900042.shtml",
    "https://www.liepin.com/job/not-an-id.shtml", "https://www.liepin.com/job/../1900042.shtml",
    "https://www.liepin.com/job/%31.shtml", "https://www.liepin.com/job/1900042.shtml/other",
    "https://www.liepin.com/job/1900042.shtml\n", " https://www.liepin.com/job/1900042.shtml", None,
])
def test_invalid_urls_do_not_reach_network(transport, url):
    _, requests = transport
    assert_error(lambda: detail.fetch_liepin_job_detail(url, RAW_ID), "INVALID_INPUT")
    assert not requests


@pytest.mark.parametrize("job_id", ["", " ", None, 42, True, "42\n", "42/other"])
def test_invalid_identity_does_not_reach_network(transport, job_id):
    _, requests = transport
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, job_id), "INVALID_INPUT")
    assert not requests


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_is_rejected_without_second_request(transport, status):
    respond, requests = transport
    respond(status=status, headers={"Location": "https://other.test/" + SENSITIVE})
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "JOB_DETAIL_UNAVAILABLE")
    assert len(requests) == 1


def test_unexpected_final_url_is_rejected(transport):
    respond, _ = transport
    respond(response_url="https://www.liepin.com/user/login")
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "JOB_DETAIL_UNAVAILABLE")


@pytest.mark.parametrize("error", [URLError(SENSITIVE), TimeoutError(SENSITIVE), OSError(SENSITIVE), HTTPException(SENSITIVE)])
def test_network_errors_are_sanitized_without_retry(transport, error):
    respond, requests = transport
    respond(error=error)
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "NETWORK_ERROR")
    assert len(requests) == 1


@pytest.mark.parametrize(("status", "code"), [(401, "JOB_DETAIL_UNAVAILABLE"), (403, "SECURITY_CHALLENGE"), (404, "JOB_DETAIL_UNAVAILABLE"), (410, "JOB_DETAIL_UNAVAILABLE"), (429, "SECURITY_CHALLENGE"), (500, "NETWORK_ERROR")])
def test_http_failure_is_explicitly_blocked(transport, status, code):
    respond, requests = transport
    respond(SENSITIVE.encode(), status=status)
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), code)
    assert len(requests) == 1


@pytest.mark.parametrize("body", [b"\xff", b"x" * 2_000_001, b'<script type="application/ld+json">{broken</script>'])
def test_invalid_or_oversized_response_is_rejected(transport, body):
    respond, _ = transport
    respond(body)
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "INVALID_RESPONSE")


def test_non_html_content_type_is_rejected(transport):
    respond, _ = transport
    respond(headers={"Content-Type": "application/json"})
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "INVALID_RESPONSE")


@pytest.mark.parametrize("identifier", ["43", 43])
def test_raw_platform_identity_mismatch_is_rejected(transport, identifier):
    respond, _ = transport
    respond(page(identifier=identifier))
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "JOB_ID_MISMATCH")


def test_missing_raw_identity_is_not_guessed_from_display_url(transport):
    respond, _ = transport
    respond(page(identifier=None, dom=JD))
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, "1900042"), "JOB_DETAIL_UNAVAILABLE")


@pytest.mark.parametrize("identifier", [True, {}, "not-an-id"])
def test_malformed_structured_identity_is_rejected(transport, identifier):
    respond, _ = transport
    respond(page(identifier=identifier))
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "INVALID_RESPONSE")


@pytest.mark.parametrize("canonical", ["https://www.liepin.com/job/1900043.shtml", "https://other.test/job/1900042.shtml"])
def test_canonical_source_cannot_claim_another_page(transport, canonical):
    respond, _ = transport
    respond(page(canonical=canonical))
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "JOB_ID_MISMATCH")


def test_conflicting_visible_and_structured_jd_is_rejected(transport):
    respond, _ = transport
    respond(page(dom=JD.replace("Java", "JavaScript")))
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "INVALID_RESPONSE")


@pytest.mark.parametrize("description", ["高级研发工程师，待遇面议", "岗位职责：开发。\n职位要求：本科。", JD.split("职位要求")[0], JD + "\n登录后查看完整职位描述"])
def test_summary_or_truncated_description_never_becomes_full_jd(transport, description):
    respond, _ = transport
    respond(page(description=description))
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "JOB_DETAIL_UNAVAILABLE")


@pytest.mark.parametrize(("body", "code"), [
    (page(title="安全验证", extra="请完成滑动验证"), "SECURITY_CHALLENGE"),
    (b"<html><body>captcha</body></html>", "SECURITY_CHALLENGE"),
    (page(title="登录猎聘", extra="手机号登录"), "JOB_DETAIL_UNAVAILABLE"),
    (page(extra="该职位已停止招聘"), "JOB_DETAIL_UNAVAILABLE"),
    (b"<html><body>No posting</body></html>", "JOB_DETAIL_UNAVAILABLE"),
])
def test_challenge_login_or_expired_page_remains_blocked(transport, body, code):
    respond, _ = transport
    respond(body)
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), code)


def test_malformed_html_without_posting_has_safe_error(transport):
    respond, _ = transport
    respond(("<![" + SENSITIVE + "]>").encode())
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "JOB_DETAIL_UNAVAILABLE")


def test_login_gate_outside_stale_structured_jd_remains_blocked(transport):
    respond, _ = transport
    respond(page(extra="请先登录后查看完整职位描述"))
    assert_error(lambda: detail.fetch_liepin_job_detail(URL, RAW_ID), "JOB_DETAIL_UNAVAILABLE")


@pytest.mark.parametrize('heading',['职位描述：','职位描述:'])
def test_verified_description_heading_is_a_duties_section(transport,heading):
    respond,_=transport
    body=JD.replace('岗位职责：',heading)
    respond(page(description=body,dom=body.replace('\n','<br>')))
    assert detail.fetch_liepin_job_detail(URL,RAW_ID)['jd_text']==body


@pytest.mark.parametrize('body',[
    JD.replace('岗位职责：','公司介绍：'),
    JD.replace('岗位职责：','职位描述摘要：'),
    JD.replace('岗位职责：','职位描述：').split('职位要求')[0],
])
def test_description_alias_does_not_relax_required_sections(transport,body):
    respond,_=transport;respond(page(description=body))
    assert_error(lambda:detail.fetch_liepin_job_detail(URL,RAW_ID),'JOB_DETAIL_UNAVAILABLE')
