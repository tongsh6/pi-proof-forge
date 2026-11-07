import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.config.composer import Composer


_VALID_POLICY = """n_pass_required: 1
matching_threshold: 0.6
evaluation_threshold: 0.5
max_rounds: 3
gate_mode: strict
delivery_mode: auto
batch_review: false
excluded_companies:
  - exact:Acme Inc
excluded_legal_entities:
  - Acme Holdings Ltd
"""


class ComposerTests(unittest.TestCase):
    def test_from_policy_path_builds_composer(self) -> None:
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(_VALID_POLICY, encoding="utf-8")
            composer = Composer.from_policy_path(str(policy_path))
            self.assertEqual(composer.policy.delivery_mode, "auto")
            self.assertEqual(composer.policy.max_rounds, 3)

    def test_composer_builds_default_registries(self) -> None:
        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(_VALID_POLICY, encoding="utf-8")
            composer = Composer.from_policy_path(str(policy_path))

            evidence = composer.build_evidence_registry()
            matching = composer.build_matching_registry()
            generation = composer.build_generation_registry()
            evaluation = composer.build_evaluation_registry()
            discovery = composer.build_discovery_registry()

            self.assertIn("rule", evidence.list())
            self.assertIn("rule", matching.list())
            self.assertIn("template", generation.list())
            self.assertIn("rule", evaluation.list())
            self.assertIn("rule", discovery.list())

    def test_llm_mode_registers_controlled_rewrite_generation_strategy(self) -> None:
        """LLM 模式的生成策略是受控改写（模板基线 + 事实校验回退），不是自由改写。"""
        from tools.infra.llm.client import LLMClient

        class FakeClient(LLMClient):
            def __init__(self) -> None:  # noqa: D107 - 测试替身不调用父类
                pass

        with TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.yaml"
            policy_path.write_text(_VALID_POLICY, encoding="utf-8")
            composer = Composer.from_policy_path(str(policy_path))
            generation = composer.build_generation_registry(
                {"name": "候选人"}, {"target_role": "后端"}
            )
            composer.add_llm_strategies(
                FakeClient(),  # type: ignore[arg-type]
                "test-model",
                composer.build_evidence_registry(),
                composer.build_matching_registry(),
                generation,
                composer.build_evaluation_registry(),
                personal_profile={"name": "候选人"},
                job_context={"target_role": "后端"},
            )
            self.assertIn("llm_rewrite", generation.list())
            engine = generation.create("llm_rewrite")
            self.assertTrue(hasattr(engine, "generate"))
            self.assertFalse(hasattr(engine, "rewrite_content"))  # 没有自由改写入口


if __name__ == "__main__":
    _ = unittest.main()
