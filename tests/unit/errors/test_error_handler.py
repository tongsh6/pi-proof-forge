import unittest

from tools.errors.exceptions import EvidenceValidationError
from tools.errors.handler import route_error


class ErrorHandlerTests(unittest.TestCase):
    def test_route_error_for_unrecoverable_exception(self) -> None:
        action = route_error(EvidenceValidationError("bad evidence"))
        self.assertEqual(action, "terminate_run")

    def test_route_error_for_unknown_exception(self) -> None:
        action = route_error(RuntimeError("boom"))
        self.assertEqual(action, "unknown_error")


if __name__ == "__main__":
    _ = unittest.main()
