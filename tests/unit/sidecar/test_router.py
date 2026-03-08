import unittest
from typing import Any

from tools.sidecar.router import Router


class RouterTests(unittest.TestCase):
    def test_register_and_dispatch(self) -> None:
        router = Router()

        def handler(params: dict[str, Any]) -> dict[str, Any]:
            return {"echo": params.get("value")}

        router.register("test.echo", handler)
        result = router.dispatch("test.echo", {"value": 42})
        self.assertEqual(result, {"echo": 42})

    def test_dispatch_unknown_method_raises(self) -> None:
        router = Router()
        with self.assertRaises(KeyError):
            router.dispatch("unknown.method", {})

    def test_register_multiple_methods(self) -> None:
        router = Router()
        router.register("a.method", lambda p: {"a": True})
        router.register("b.method", lambda p: {"b": True})
        self.assertEqual(router.dispatch("a.method", {}), {"a": True})
        self.assertEqual(router.dispatch("b.method", {}), {"b": True})

    def test_list_registered_methods(self) -> None:
        router = Router()
        router.register("system.ping", lambda p: {})
        router.register("evidence.list", lambda p: {})
        methods = router.list_methods()
        self.assertIn("system.ping", methods)
        self.assertIn("evidence.list", methods)


if __name__ == "__main__":
    unittest.main()
