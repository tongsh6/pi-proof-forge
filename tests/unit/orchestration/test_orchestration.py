import unittest
from importlib import import_module


def _state_machine_class():
    module = import_module("tools.orchestration.state_machine")
    return module.StateMachine


def _linear_pipeline_class():
    module = import_module("tools.orchestration.pipeline")
    return module.LinearPipeline


def _stage_result_class():
    module = import_module("tools.orchestration.stage")
    return module.StageResult


class StateMachineTests(unittest.TestCase):
    def test_init_to_discover(self) -> None:
        sm = _state_machine_class()()
        self.assertEqual(sm.transition("INIT", "start"), "DISCOVER")

    def test_gate_pass_to_review(self) -> None:
        sm = _state_machine_class()()
        self.assertEqual(sm.transition("GATE", "pass"), "REVIEW")

    def test_invalid_transition_raises(self) -> None:
        sm = _state_machine_class()()
        with self.assertRaises(ValueError):
            sm.transition("DONE", "next")


class PipelineTests(unittest.TestCase):
    def test_linear_pipeline_runs_stages(self) -> None:
        StageResult = _stage_result_class()
        executed: list[str] = []

        class StageA:
            name = "A"

            def execute(self, context: dict[str, object]) -> object:
                executed.append("A")
                return StageResult(success=True, data={"a": 1})

        class StageB:
            name = "B"

            def execute(self, context: dict[str, object]) -> object:
                executed.append("B")
                return StageResult(success=True, data={"b": 2})

        pipeline = _linear_pipeline_class()([StageA(), StageB()])
        result = pipeline.run({})
        self.assertTrue(result.success)
        self.assertEqual(executed, ["A", "B"])


if __name__ == "__main__":
    _ = unittest.main()
