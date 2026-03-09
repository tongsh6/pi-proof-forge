import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.domain.events import RunEvent
from tools.infra.persistence.file_run_store import FileRunStore


class FileRunStoreTests(unittest.TestCase):
    def test_append_and_load_events(self) -> None:
        with TemporaryDirectory() as tmp:
            store = FileRunStore(base_dir=tmp)
            store.append_event(
                RunEvent(
                    run_id="run-1",
                    event_type="DISCOVER",
                    round_index=0,
                    payload={"count": 1},
                )
            )
            events = store.load_events("run-1")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "DISCOVER")

    def test_append_is_not_overwrite(self) -> None:
        with TemporaryDirectory() as tmp:
            store = FileRunStore(base_dir=tmp)
            store.append_event(
                RunEvent(
                    run_id="run-2",
                    event_type="DISCOVER",
                    round_index=0,
                    payload={},
                )
            )
            store.append_event(
                RunEvent(
                    run_id="run-2",
                    event_type="SCORE",
                    round_index=0,
                    payload={},
                )
            )
            events = store.load_events("run-2")
            self.assertEqual(len(events), 2)

    def test_run_log_and_round_snapshot_written(self) -> None:
        with TemporaryDirectory() as tmp:
            store = FileRunStore(base_dir=tmp)
            store.append_event(
                RunEvent(
                    run_id="run-3",
                    event_type="INIT",
                    round_index=0,
                    payload={},
                )
            )
            run_log = Path(tmp) / "run-3" / "run_log.json"
            round_events = Path(tmp) / "run-3" / "rounds" / "0" / "events.jsonl"
            self.assertTrue(run_log.exists())
            self.assertTrue(round_events.exists())


if __name__ == "__main__":
    _ = unittest.main()
