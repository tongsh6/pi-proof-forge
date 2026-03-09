from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class EngineRegistry(Generic[T]):
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], T]] = {}

    def register(self, strategy: str, factory: Callable[[], T]) -> None:
        self._factories[strategy] = factory

    def create(self, strategy: str) -> T:
        if strategy not in self._factories:
            raise KeyError(
                f"Unknown strategy: {strategy}. Available: {sorted(self._factories)}"
            )
        return self._factories[strategy]()

    def list(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories.keys()))
