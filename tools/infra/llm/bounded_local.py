"""Local-only bounded HTTP adapter for advisory preparation."""
from __future__ import annotations

import time
from urllib import request
from urllib.error import URLError

from tools.infra.llm.client import LLMClient

SPLASH = "http://127.0.0.1:8000/v1"


class LocalProviderTimeout(ValueError):
    """The bounded local transport timed out or is latched after a timeout."""


class LocalAttemptBudget(ValueError):
    """The bounded local transport refused to start another request."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("semantic_redirect_blocked")


class _TimeoutAwareResponse:
    """Preserve response lifetime while making body-read timeout terminal for this client."""
    def __init__(self, response, client):
        self._response = response
        self._client = client

    def read(self, *args, **kwargs):
        try:
            return self._response.read(*args, **kwargs)
        except TimeoutError:
            self._client.provider_timeout = True
            raise LocalProviderTimeout("semantic_provider_timeout") from None

    def close(self):
        return self._response.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __getattr__(self, name):
        return getattr(self._response, name)


class BoundedLocalClient(LLMClient):
    """Counts actual HTTP attempts, without the parent's transient-error retries."""
    def __init__(self, *, model, api_key):
        super().__init__(SPLASH, api_key, timeout=20, provider="openai_compatible")
        self.model_calls = 0
        self.budget_exhausted = False
        self.provider_timeout = False
        # Request-start deadline, not a hard wall-clock cancellation of response reads.
        self.deadline = time.monotonic() + 90
        self._opener = request.build_opener(request.ProxyHandler({}), _NoRedirect())

    def _open_with_retry(self, req):
        if req.full_url != self.chat_completions_url:
            raise ValueError("local_splash_required")
        remaining = self.deadline - time.monotonic()
        if self.provider_timeout:
            raise LocalProviderTimeout("semantic_provider_timeout")
        if self.model_calls >= 4 or remaining <= 0:
            self.budget_exhausted = True
            raise LocalAttemptBudget("semantic_budget_exhausted")
        self.model_calls += 1
        try:
            return _TimeoutAwareResponse(self._opener.open(req, timeout=min(20, remaining)), self)
        except (TimeoutError, URLError) as exc:
            if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
                self.provider_timeout = True
                raise LocalProviderTimeout("semantic_provider_timeout") from None
            raise

