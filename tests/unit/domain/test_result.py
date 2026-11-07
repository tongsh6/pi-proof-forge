import unittest

from tools.domain.result import Err, Ok


class ResultTypeTests(unittest.TestCase):
    def test_ok_instances_with_same_value_are_equal(self) -> None:
        self.assertEqual(Ok(value=1), Ok(value=1))

    def test_err_instances_with_same_error_are_equal(self) -> None:
        self.assertEqual(Err(error="x"), Err(error="x"))

    def test_ok_and_err_are_not_equal(self) -> None:
        self.assertNotEqual(Ok(value=1), Err(error=1))

    def test_repr_is_stable_and_readable(self) -> None:
        self.assertEqual(repr(Ok(value=1)), "Ok(value=1)")
        self.assertEqual(repr(Err(error="x")), "Err(error='x')")


if __name__ == "__main__":
    unittest.main()
