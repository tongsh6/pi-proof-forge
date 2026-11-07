import unittest

from tools.domain.events import RunEvent
from tools.domain.run_state import RunState


class RunStateTests(unittest.TestCase):
    def test_initial_state(self) -> None:
        state = RunState.initial("run-001")
        self.assertEqual(state.run_id, "run-001")
        self.assertEqual(state.current_status, "INIT")
        self.assertEqual(state.round_index, 0)

    def test_replay_empty_events_keeps_init(self) -> None:
        state = RunState.replay("run-001", [])
        self.assertEqual(state.current_status, "INIT")

    def test_replay_last_event_wins(self) -> None:
        events = [
            RunEvent(run_id="r1", event_type="DISCOVER", round_index=0, payload={}),
            RunEvent(run_id="r1", event_type="SCORE", round_index=0, payload={}),
            RunEvent(run_id="r1", event_type="GATE_PASS", round_index=1, payload={}),
        ]
        state = RunState.replay("r1", events)
        self.assertEqual(state.current_status, "GATE_PASS")
        self.assertEqual(state.round_index, 1)

    def test_run_state_is_frozen(self) -> None:
        state = RunState.initial("r1")
        with self.assertRaises(AttributeError):
            setattr(state, "current_status", "DONE")


if __name__ == "__main__":
    _ = unittest.main()
