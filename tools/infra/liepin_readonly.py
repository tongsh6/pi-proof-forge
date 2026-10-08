"""猎聘只读凭据：本机权限文件持久化，状态回读不包含凭据。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_MESSAGES = {
    "OK": "只读请求成功。",
    "AUTH_REQUIRED": "请先在系统设置中配置猎聘官方凭据。",
    "AUTH_INVALID": "猎聘凭据已失效，请重新配置。",
    "RATE_LIMITED": "猎聘请求限流，请稍后手动重试。",
    "NETWORK_ERROR": "猎聘服务暂时无法连接，请稍后手动重试。",
    "INVALID_RESPONSE": "猎聘返回的数据不符合已验证的只读契约。",
    "API_ERROR": "猎聘未确认本次只读业务请求成功。",
    "INVALID_INPUT": "请检查输入格式。",
    "INTERNAL_ERROR": "只读请求未完成，请重试或重新配置凭据。",
    "STORAGE_ERROR": "岗位结果保存失败，请检查本地存储后重试。",
    "CREDENTIAL_STORAGE_ERROR": "本机凭据文件读取、保存或删除失败，请检查路径与权限后重试。",
}


class LiepinReadOnlySession:
    def __init__(self, *, store=None) -> None:
        if store is None:
            from tools.infra.liepin_token_file import LiepinTokenFile
            store = LiepinTokenFile()
        self._store = store
        self.unload()

    def unload(self) -> None:
        """退出只释放进程内存，不删除用户保存的凭据。"""
        self._token = ""
        self._saved = False
        self._loaded = False
        self._state = "unconfigured"
        self._code = "AUTH_REQUIRED"
        self._last_checked_at = ""
        self._last_error = ""

    @staticmethod
    def _valid_token(token: object) -> bool:
        return (isinstance(token, str) and bool(token.strip()) and len(token) <= 8192
                and not any(ord(char) < 32 or ord(char) == 127 for char in token))

    def _storage_error(self) -> None:
        self._state = "error"
        self._code = "CREDENTIAL_STORAGE_ERROR"
        self._last_error = _MESSAGES[self._code]

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            token = self._store.load()
            if token is not None and not self._valid_token(token):
                self._saved = True
                self._storage_error()
                return
        except Exception:
            # 固定文案；不回显操作系统异常或文件内容。
            self._storage_error()
            return
        self._loaded = True
        self._token = token.strip() if token is not None else ""
        self._saved = bool(self._token)
        self._state = "unverified" if self._token else "unconfigured"
        self._code = "OK" if self._token else "AUTH_REQUIRED"
        self._last_error = ""

    def clear(self) -> dict[str, Any]:
        self._ensure_loaded()
        try:
            self._store.delete()
        except Exception:
            self._storage_error()
            return self._snapshot()
        self.unload()
        self._loaded = True
        return self._snapshot()

    def configure(self, token: object) -> dict[str, Any]:
        self._ensure_loaded()
        if not self._valid_token(token):
            self._state = "error"
            self._code = "INVALID_INPUT"
            self._last_error = _MESSAGES[self._code]
            return self._snapshot()
        try:
            self._store.save(token.strip())
        except Exception:
            self._storage_error()
            return self._snapshot()
        self._token = token.strip()
        self._loaded = self._saved = True
        self._state = "unverified"
        self._code = "OK"
        self._last_error = ""
        self._last_checked_at = ""
        return self._snapshot()

    def snapshot(self) -> dict[str, Any]:
        self._ensure_loaded()
        return self._snapshot()

    def _snapshot(self) -> dict[str, Any]:
        return {
            "configured": bool(self._token), "state": self._state,
            "code": self._code, "last_checked_at": self._last_checked_at,
            "last_error": self._last_error, "scope": "read_only", "storage": "local_file",
            "storage_path": str(self._store.path), "saved": self._saved,
        }

    def result(self, code: str, **fields: Any) -> dict[str, Any]:
        safe_code = code if code in _MESSAGES else "INTERNAL_ERROR"
        return {"status": "pass" if safe_code == "OK" else "blocked",
                "code": safe_code, "message": _MESSAGES[safe_code],
                "auth": self.snapshot(), **fields}

    def failure(self, code: str) -> dict[str, Any]:
        self._code = code if code in _MESSAGES else "INTERNAL_ERROR"
        self._state = ({"AUTH_INVALID": "invalid", "RATE_LIMITED": "rate_limited"}
                       .get(self._code, "error")) if self._token else "unconfigured"
        self._last_error = _MESSAGES[self._code]
        return self.result(self._code)

    def read_resume(self) -> dict[str, Any]:
        result = self._invoke("resume")
        text = result.pop("data", "")
        return {**result, "resume_text": text if result["status"] == "pass" else ""}

    def search(self, keyword: str, page: int) -> dict[str, Any]:
        return self._invoke("search", keyword=keyword, page=page)

    def _invoke(self, operation: str, **params: Any) -> dict[str, Any]:
        self._ensure_loaded()
        if not self._token:
            if self._code == "CREDENTIAL_STORAGE_ERROR":
                return {"status": "blocked", "code": self._code,
                        "message": _MESSAGES[self._code], "auth": self._snapshot()}
            return self.result("AUTH_REQUIRED")
        from tools.infra.liepin_api import LiepinApiError, LiepinReadOnlyClient
        self._last_checked_at = datetime.now(timezone.utc).isoformat()
        try:
            client = LiepinReadOnlyClient()
            if operation == "resume":
                data = client.get_resume(self._token)
            else:
                data = client.search_jobs(self._token, **params)
        except LiepinApiError as exc:
            return self.failure(exc.code)
        except Exception:
            # 未知异常也不回显第三方正文、请求头或凭据。
            return self.failure("INTERNAL_ERROR")
        self._state, self._code, self._last_error = "valid", "OK", ""
        return self.result("OK", data=data)


liepin_readonly = LiepinReadOnlySession()
