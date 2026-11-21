"""RPC 错误码映射契约：类型化异常优先，兼容既有字符串码。"""
import pytest

from tools.errors.codes import (
    CONFLICT,
    INTERNAL_ERROR,
    NOT_FOUND,
    UNSUPPORTED_VERSION,
    VALIDATION_ERROR,
    ConflictError,
    NotFoundError,
    SidecarError,
    UnsupportedVersionError,
    ValidationError,
    error_code_of,
)


def test_typed_errors_map_to_their_codes():
    assert error_code_of(NotFoundError("missing")) == NOT_FOUND
    assert error_code_of(ConflictError("dup")) == CONFLICT
    assert error_code_of(UnsupportedVersionError("v")) == UNSUPPORTED_VERSION
    assert error_code_of(ValidationError("bad")) == VALIDATION_ERROR
    assert error_code_of(SidecarError("x", code=CONFLICT)) == CONFLICT


def test_legacy_key_error_and_value_error_keep_previous_semantics():
    assert error_code_of(KeyError("EVIDENCE_NOT_FOUND")) == NOT_FOUND
    assert error_code_of(KeyError("other")) == VALIDATION_ERROR
    assert error_code_of(ValueError("UNSUPPORTED_VERSION: 2")) == UNSUPPORTED_VERSION
    assert error_code_of(ValueError("some_code")) == VALIDATION_ERROR


def test_unexpected_exception_is_internal_unless_conflict_prefixed():
    assert error_code_of(RuntimeError("boom")) == INTERNAL_ERROR
    assert error_code_of(RuntimeError("CONFLICT: duplicated attempt")) == CONFLICT


def test_typed_error_is_not_swallowed_by_legacy_value_error_branch():
    with pytest.raises(SidecarError):
        raise NotFoundError("x")
