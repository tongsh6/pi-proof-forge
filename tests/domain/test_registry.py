import unittest
from importlib import import_module


def _registry_class():
    module = import_module("tools.engines.registry")
    return module.EngineRegistry


class EngineRegistryTests(unittest.TestCase):
    def test_register_and_create(self) -> None:
        registry = _registry_class()()
        registry.register("rule", lambda: "rule-engine")
        self.assertEqual(registry.create("rule"), "rule-engine")

    def test_create_raises_for_unknown_strategy(self) -> None:
        registry = _registry_class()()
        with self.assertRaises(KeyError):
            registry.create("llm")

    def test_list_returns_registered_strategies(self) -> None:
        registry = _registry_class()()
        registry.register("b", lambda: "B")
        registry.register("a", lambda: "A")
        self.assertEqual(registry.list(), ("a", "b"))


if __name__ == "__main__":
    _ = unittest.main()
