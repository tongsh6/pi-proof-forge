"""猎聘官方只读契约；仅替换最底层 HTTPS 传输，不使用真实凭据。"""

from __future__ import annotations

import io
import json
import traceback
from email.message import Message
from http.client import HTTPException
from urllib.error import URLError
from urllib.request import HTTPSHandler
from urllib.response import addinfourl

import pytest

from tools.infra import liepin_api as api


SECRET = "unit-test-token-do-not-log"
ORIGIN = "https://open-agent.liepin.com"


@pytest.fixture
def transport(monkeypatch):
    requests = []
    responses = []

    def respond(payload=None, *, status=200, raw=None, headers=None, error=None):
        body = raw if raw is not None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        responses.append((body, status, headers or {}, error))

    def https_open(handler, request):
        requests.append(request)
        body, status, response_headers, error = responses.pop(0)
        if error is not None:
            raise error
        message = Message()
        message["Content-Type"] = "application/json"
        for name, value in response_headers.items():
            message[name] = value
        response = addinfourl(io.BytesIO(body), message, request.full_url, status)
        response.msg = SECRET
        return response

    monkeypatch.setattr(HTTPSHandler, "https_open", https_open)
    return respond, requests


def assert_error(call, code):
    with pytest.raises(api.LiepinApiError) as caught:
        call()
    error = caught.value
    assert error.code == code
    rendered = "".join(traceback.format_exception(error))
    assert SECRET not in rendered
    assert SECRET not in repr(error)
    assert SECRET not in repr(vars(error))
    assert str(error) == error.message
    return error


def test_get_resume_uses_official_get_and_preserves_text(transport):
    respond, requests = transport
    text = "基本信息\n测试用户\n工作经历\n工程研发"
    respond({"errCode": 0, "data": {"result": text}})
    client = api.LiepinReadOnlyClient()

    assert client.get_resume("  " + SECRET + "  ") == text
    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == ORIGIN + "/mcp/get-resume"
    assert request.get_method() == "GET"
    assert request.data is None
    assert request.get_header("X-user-token") == SECRET
    assert request.get_header("Accept") == "application/json"
    assert 0 < request.timeout <= 30
    assert SECRET not in repr(client)
    assert SECRET not in repr(vars(client))


def test_search_uses_job_name_zero_based_page_and_keeps_raw_fields(transport):
    respond, requests = transport
    jobs = [
        {"jobId": 42, "jobType": "1", "jobName": "架构师", "company": "测试企业", "jobDetailUrl": "https://www.liepin.com/job/42.shtml"},
        {"jobId": "00043", "jobType": "2", "jobName": "技术负责人", "extra": {"value": "preserved"}},
    ]
    respond({"code": 0, "data": {"list": jobs}})
    client = api.LiepinReadOnlyClient()

    assert client.search_jobs(SECRET, " 架构师 ", page=2) == jobs
    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == ORIGIN + "/mcp/search-job"
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"jobName": "架构师", "page": 2}
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-user-token") == SECRET


def test_search_empty_results_are_success_and_default_page_is_zero(transport):
    respond, requests = transport
    respond({"code": 0, "data": {"list": []}})

    assert api.LiepinReadOnlyClient().search_jobs(SECRET, "Python") == []
    assert json.loads(requests[0].data)["page"] == 0


@pytest.mark.parametrize(("token", "code"), [
    ("", "AUTH_REQUIRED"), ("  ", "AUTH_REQUIRED"), (None, "AUTH_REQUIRED"),
    (SECRET + "\r\nInjected: value", "INVALID_INPUT"),
    (SECRET + "\n", "INVALID_INPUT"), ("令牌", "INVALID_INPUT"),
    ("\n", "INVALID_INPUT"), ("\r ", "INVALID_INPUT"),
])
def test_invalid_token_fails_before_network(transport, token, code):
    _, requests = transport
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.get_resume(token), code)
    assert requests == []


@pytest.mark.parametrize(("keyword", "page"), [("", 0), ("  ", 0), (None, 0), ("Python", -1), ("Python", True), ("Python", 1.5), ("Python", "0")])
def test_invalid_search_fails_before_network(transport, keyword, page):
    _, requests = transport
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.search_jobs(SECRET, keyword, page), "INVALID_INPUT")
    assert requests == []


@pytest.mark.parametrize(("status", "code"), [(401, "AUTH_INVALID"), (403, "AUTH_INVALID"), (429, "RATE_LIMITED"), (400, "API_ERROR"), (500, "API_ERROR"), (503, "API_ERROR")])
def test_http_errors_are_safe_and_never_retried(transport, status, code):
    respond, requests = transport
    respond(raw=SECRET.encode(), status=status, headers={"X-Secret": SECRET})
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.get_resume(SECRET), code)
    assert len(requests) == 1


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_never_forward_token(transport, status):
    respond, requests = transport
    respond(status=status, headers={"Location": "https://other.example/" + SECRET})
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.get_resume(SECRET), "API_ERROR")
    assert len(requests) == 1
    assert requests[0].full_url == ORIGIN + "/mcp/get-resume"


@pytest.mark.parametrize("error", [URLError(SECRET), TimeoutError(SECRET), OSError(SECRET), HTTPException(SECRET)])
def test_network_failures_are_safe_and_never_retried(transport, error):
    respond, requests = transport
    respond(error=error)
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.get_resume(SECRET), "NETWORK_ERROR")
    assert len(requests) == 1


@pytest.mark.parametrize("raw", [b"not-json", b"", b"\xff", b"[]", b"null", b"true", b"{" + SECRET.encode()])
def test_invalid_json_and_root_shape_are_rejected(transport, raw):
    respond, _ = transport
    respond(raw=raw)
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.get_resume(SECRET), "INVALID_RESPONSE")


@pytest.mark.parametrize("payload", [
    {}, {"code": 0, "data": {"result": "resume"}},
    {"errCode": False, "data": {"result": "resume"}},
    {"errCode": "0", "data": {"result": "resume"}},
    {"errCode": 0}, {"errCode": 0, "data": []},
    {"errCode": 0, "data": {}}, {"errCode": 0, "data": {"result": {}}},
    {"errCode": 0, "data": {"result": " "}},
])
def test_zero_business_code_does_not_bypass_resume_shape(transport, payload):
    respond, _ = transport
    respond(payload)
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.get_resume(SECRET), "INVALID_RESPONSE")


@pytest.mark.parametrize("payload", [
    {"errCode": 0, "data": {"list": []}}, {"code": 0},
    {"code": 0, "data": {"list": {}}}, {"code": 0, "data": {"list": ["error"]}},
    {"code": 0, "data": {"list": [{"error": SECRET}]}},
    {"code": 0, "data": {"list": [{"jobId": True, "jobType": "2", "jobName": "开发"}]}},
    {"code": 0, "data": {"list": [{"jobId": 1, "jobType": "", "jobName": "开发"}]}},
    {"code": 0, "data": {"list": [{"jobId": 1, "jobType": "2", "jobName": ""}]}},
])
def test_zero_business_code_does_not_turn_invalid_records_into_jobs(transport, payload):
    respond, _ = transport
    respond(payload)
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.search_jobs(SECRET, "开发"), "INVALID_RESPONSE")


@pytest.mark.parametrize("method", ["resume", "search"])
def test_nonzero_business_error_never_returns_payload_or_server_message(transport, method):
    respond, requests = transport
    key = "errCode" if method == "resume" else "code"
    respond({key: 991001, "message": SECRET, "data": {"result": SECRET, "list": []}})
    client = api.LiepinReadOnlyClient()
    call = lambda: client.get_resume(SECRET) if method == "resume" else client.search_jobs(SECRET, "开发")

    assert_error(call, "API_ERROR")
    assert len(requests) == 1


@pytest.mark.parametrize("method", ["resume", "search"])
def test_explicit_failure_flag_cannot_be_hidden_by_zero_business_code(transport, method):
    respond, _ = transport
    key = "errCode" if method == "resume" else "code"
    respond({key: 0, "ok": False, "message": SECRET, "data": {"result": "resume", "list": []}})
    client = api.LiepinReadOnlyClient()
    call = lambda: client.get_resume(SECRET) if method == "resume" else client.search_jobs(SECRET, "开发")

    assert_error(call, "API_ERROR")


def test_response_size_is_bounded(transport):
    respond, _ = transport
    respond({"errCode": 0, "data": {"result": "x" * 2_000_001}})
    client = api.LiepinReadOnlyClient()

    assert_error(lambda: client.get_resume(SECRET), "INVALID_RESPONSE")
