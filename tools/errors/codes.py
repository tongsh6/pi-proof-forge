"""Sidecar 错误码的类型化来源。

现状：handler 里大量 `raise ValueError("some_code")`，server 层靠字符串匹配
判断 NOT_FOUND / UNSUPPORTED_VERSION / CONFLICT，错误语义编码在消息文本里，
无法在类型上区分「事实门禁」与「参数校验」。

本模块提供类型化错误基类与稳定映射，供 handler 逐步迁移；`error_code_of`
同时识别新异常与既有字符串码，保证迁移期间行为不变。
"""
from __future__ import annotations

from tools.errors.exceptions import (  # noqa: F401 - 兼容既有导入路径
    EvidenceValidationError,
    FabricationGuardError,
    PiProofError,
    PolicyError,
)

NOT_FOUND = "NOT_FOUND"
CONFLICT = "CONFLICT"
UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
VALIDATION_ERROR = "VALIDATION_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"


class SidecarError(Exception):
    """带稳定错误码的业务异常；`code` 直接映射到 RPC 错误响应。"""

    code = INTERNAL_ERROR
    retryable = False

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message or self.code)
        if code:
            self.code = code


class NotFoundError(SidecarError):
    code = NOT_FOUND


class ConflictError(SidecarError):
    code = CONFLICT


class UnsupportedVersionError(SidecarError):
    code = UNSUPPORTED_VERSION


class ValidationError(SidecarError):
    code = VALIDATION_ERROR


def error_code_of(exc: BaseException) -> str:
    """把异常映射为 RPC 错误码；未识别的按兼容规则回退到 VALIDATION_ERROR。"""
    if isinstance(exc, SidecarError):
        return exc.code
    if isinstance(exc, KeyError):
        return NOT_FOUND if "NOT_FOUND" in str(exc) else VALIDATION_ERROR
    if isinstance(exc, ValueError):
        text = str(exc)
        if "UNSUPPORTED_VERSION" in text:
            return UNSUPPORTED_VERSION
        return VALIDATION_ERROR
    text = str(exc)
    if text.startswith("CONFLICT:"):
        return CONFLICT
    return INTERNAL_ERROR
