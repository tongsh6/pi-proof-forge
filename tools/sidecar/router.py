from __future__ import annotations

from typing import Any, Callable

Handler = Callable[[dict[str, Any]], dict[str, Any]]


class Router:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method not in self._handlers:
            raise KeyError(f"Unknown method: {method}")
        return self._handlers[method](params)

    def list_methods(self) -> list[str]:
        return list(self._handlers.keys())
