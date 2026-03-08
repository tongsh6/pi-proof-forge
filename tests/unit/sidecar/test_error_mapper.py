import unittest

from tools.sidecar.error_mapper import ErrorMapper, SidecarError


class ErrorMapperTests(unittest.TestCase):
    def test_maps_known_error_codes(self) -> None:
        known_codes = [
            "UNSUPPORTED_VERSION",
            "SIDECAR_UNAVAILABLE",
            "TIMEOUT",
            "VALIDATION_ERROR",
            "NOT_FOUND",
            "INTERNAL_ERROR",
        ]
        for code in known_codes:
            err = ErrorMapper.create(code, f"test {code}", "corr_001")
            self.assertEqual(err.code, code)
            self.assertEqual(err.details["correlation_id"], "corr_001")

    def test_retryable_flag_for_timeout(self) -> None:
        err = ErrorMapper.create("TIMEOUT", "request timeout", "corr_001")
        self.assertTrue(err.details["retryable"])

    def test_retryable_flag_for_validation_error(self) -> None:
        err = ErrorMapper.create("VALIDATION_ERROR", "invalid params", "corr_001")
        self.assertFalse(err.details["retryable"])

    def test_retryable_flag_for_sidecar_unavailable(self) -> None:
        err = ErrorMapper.create("SIDECAR_UNAVAILABLE", "not ready", "corr_001")
        self.assertTrue(err.details["retryable"])

    def test_not_found_is_not_retryable(self) -> None:
        err = ErrorMapper.create("NOT_FOUND", "missing", "corr_001")
        self.assertFalse(err.details["retryable"])

    def test_to_error_response(self) -> None:
        err = ErrorMapper.create("TIMEOUT", "timed out", "corr_001")
        resp = err.to_dict()
        self.assertEqual(resp["code"], "TIMEOUT")
        self.assertEqual(resp["message"], "timed out")
        self.assertEqual(resp["details"]["correlation_id"], "corr_001")
        self.assertTrue(resp["details"]["retryable"])

    def test_internal_error_is_maybe_retryable(self) -> None:
        err = ErrorMapper.create("INTERNAL_ERROR", "unknown", "corr_001")
        self.assertFalse(err.details["retryable"])


if __name__ == "__main__":
    unittest.main()
