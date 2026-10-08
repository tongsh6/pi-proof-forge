"""猎聘官方只读 HTTP 适配器；不保存凭据，不提供平台写入能力。"""

from __future__ import annotations

import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


_ORIGIN = "https://open-agent.liepin.com"
_TIMEOUT_SECONDS = 20
_MAX_RESPONSE_BYTES = 2_000_000
_ALLOWED_REQUESTS = {("GET", "/mcp/get-resume"), ("POST", "/mcp/search-job")}
_ERROR_MESSAGES = {
    "AUTH_REQUIRED": "请先配置猎聘 Token。",
    "AUTH_INVALID": "猎聘凭据无效或已失效，请重新配置。",
    "RATE_LIMITED": "猎聘请求受到限流，请稍后手动重试。",
    "NETWORK_ERROR": "无法连接猎聘官方服务，请检查网络后重试。",
    "INVALID_RESPONSE": "猎聘返回的数据不符合已核实的只读契约。",
    "API_ERROR": "猎聘官方接口未成功完成请求。",
    "INVALID_INPUT": "猎聘请求参数无效。",
}


class LiepinApiError(Exception):
    """供上层按稳定错误码处理；适配器仅使用固定的安全文案。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message if message is not None else _ERROR_MESSAGES[code]
        super().__init__(self.message)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # 同源跳转也拒绝，避免未核实端点收到凭据或发生请求语义变化。
        return None


class LiepinReadOnlyClient:
    def get_resume(self, token: str) -> str:
        data = self._request(token, "GET", "/mcp/get-resume", "errCode")
        resume = data.get("result")
        if not isinstance(resume, str) or not resume.strip():
            raise LiepinApiError("INVALID_RESPONSE")
        return resume

    def search_jobs(self, token: str, keyword: str, page: int = 0) -> list[dict]:
        if not isinstance(keyword, str) or not keyword.strip() or type(page) is not int or page < 0:
            raise LiepinApiError("INVALID_INPUT")
        # 官方固定源码 858a62b：关键词使用 jobName，首页 page=0。
        data = self._request(
            token, "POST", "/mcp/search-job", "code",
            {"jobName": keyword.strip(), "page": page},
        )
        jobs = data.get("list")
        if not isinstance(jobs, list) or any(not self._is_job(job) for job in jobs):
            raise LiepinApiError("INVALID_RESPONSE")
        return jobs

    @staticmethod
    def _is_job(job: object) -> bool:
        if not isinstance(job, dict):
            return False
        job_id = job.get("jobId")
        valid_id = (type(job_id) is int and job_id > 0) or (isinstance(job_id, str) and bool(job_id.strip()))
        return bool(valid_id) and all(
            isinstance(job.get(field), str) and bool(job[field].strip())
            for field in ("jobType", "jobName")
        )

    @staticmethod
    def _token(token: str) -> str:
        if token is None:
            raise LiepinApiError("AUTH_REQUIRED")
        if not isinstance(token, str) or "\r" in token or "\n" in token:
            raise LiepinApiError("INVALID_INPUT")
        token = token.strip()
        if not token:
            raise LiepinApiError("AUTH_REQUIRED")
        if any(ord(char) < 33 or ord(char) > 126 for char in token):
            raise LiepinApiError("INVALID_INPUT")
        return token

    @staticmethod
    def _http_error(status: int) -> str:
        if status in (401, 403):
            return "AUTH_INVALID"
        if status == 429:
            return "RATE_LIMITED"
        return "API_ERROR"

    def _request(self, token: str, method: str, path: str, code_key: str, payload: dict | None = None) -> dict:
        if (method, path) not in _ALLOWED_REQUESTS:
            raise LiepinApiError("INVALID_INPUT")
        headers = {"x-user-token": self._token(token), "Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(_ORIGIN + path, data=body, headers=headers, method=method)
        error_code = None
        content = b""
        try:
            with build_opener(_NoRedirect()).open(request, timeout=_TIMEOUT_SECONDS) as response:
                if not 200 <= response.status < 300:
                    error_code = self._http_error(response.status)
                else:
                    content = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            error_code = self._http_error(exc.code)
            exc.close()
        except (URLError, TimeoutError, OSError, HTTPException):
            error_code = "NETWORK_ERROR"
        # 在 except 之外创建安全异常，避免保留带 URL、响应或 header 的异常链。
        if error_code is not None:
            raise LiepinApiError(error_code)
        if len(content) > _MAX_RESPONSE_BYTES:
            raise LiepinApiError("INVALID_RESPONSE")
        parsed = None
        try:
            parsed = json.loads(content)
        except (ValueError, UnicodeError, RecursionError):
            pass
        if not isinstance(parsed, dict) or type(parsed.get(code_key)) is not int:
            raise LiepinApiError("INVALID_RESPONSE")
        # 官方未公开业务失败码字典；不根据响应正文猜测认证或限流状态。
        if parsed[code_key] != 0 or parsed.get("ok") is False:
            raise LiepinApiError("API_ERROR")
        data = parsed.get("data")
        if not isinstance(data, dict):
            raise LiepinApiError("INVALID_RESPONSE")
        return data
